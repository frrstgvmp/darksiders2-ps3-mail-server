#!/usr/bin/env python3
"""Local DNS/HTTPS collector with optional experimental THQ cloud storage."""
import argparse
import asyncio
import datetime
import hashlib
import http.server
import json
import os
import socket
import sqlite3
import ssl
import threading
import uuid
import warnings
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import dns_probe
from cloud_api import CloudStore, empty_inbox_reply
from access_control import AllowedPeers
from psn_auth import AuthError

BASE = Path(__file__).parent / "research/lab-server"
GAME_HOSTS = ["ds2.gds.thqconnect.com", "thqc-darksiders2-ps3-na.thqconnect.com"]
IANA_CIPHER_NAMES = {
    0x0004: "TLS_RSA_WITH_RC4_128_MD5",
    0x0005: "TLS_RSA_WITH_RC4_128_SHA",
    0x000a: "TLS_RSA_WITH_3DES_EDE_CBC_SHA",
    0x00ff: "TLS_EMPTY_RENEGOTIATION_INFO_SCSV",
}


def redact_path(path, private=False):
    """Keep protocol parameters, but never log a reusable authentication ticket."""
    parts = urlsplit(path)
    sensitive = {"auth", "token", "access_token", "session", "password", "email"}
    if private:
        sensitive.update({'profilenames', 'keys', 'values'})
    query = [(key, "[REDACTED]" if key.lower() in sensitive else value)
             for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                      urlencode(query), parts.fragment))


def tls_message(events, cipher_names, sock, direction, version, content_type, msg_type, data):
    """Record cipher offers and alerts, without tickets or application data."""
    if direction != "read":
        return
    peer = sock.getpeername()[0]
    port = sock.getsockname()[1]
    if int(content_type) == 21 and len(data) == 2:
        events.write(event="tls_client_alert", client=peer, port=port,
                     level=data[0], description=data[1])
    if int(content_type) != 22 or int(msg_type) != 1 or len(data) < 41:
        return
    offset = 39 + data[38]  # handshake header, version, random, session-id length
    if offset + 2 > len(data):
        return
    length = int.from_bytes(data[offset:offset + 2], "big")
    offset += 2
    if length % 2 or offset + length > len(data):
        return
    ids = [int.from_bytes(data[i:i + 2], "big")
           for i in range(offset, offset + length, 2)]
    events.write(event="tls_client_hello", client=peer, port=port,
                 legacy_version=data[4:6].hex(),
                 cipher_ids=[f"{value:04x}" for value in ids],
                 cipher_names=[cipher_names.get(value, "unknown") for value in ids])


class Events:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(directory / "https.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        if os.getuid() == 0 and "SUDO_UID" in os.environ:
            os.fchown(fd, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
        self.file = os.fdopen(fd, "a")
        self.lock = threading.Lock()

    def write(self, **values):
        line = json.dumps({"time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           **values}, ensure_ascii=False)
        with self.lock:
            self.file.write(line + "\n")
            self.file.flush()
            print(line, flush=True)


class Collector(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, args, events, context, port, cloud_store, handler_cls=None):
        self.allowed = AllowedPeers.from_args(args)
        self.events = events
        self.context = context
        self.empty_inbox = args.empty_inbox
        self.cloud_store = cloud_store
        self.capture_raw = getattr(args, 'capture_raw', True)
        self.authenticator = getattr(args, 'authenticator', None)
        self.public_mode = getattr(args, 'public_mode', False)
        self.capacity = getattr(args, 'connection_slots', threading.BoundedSemaphore(32))
        self.connection_rate = getattr(args, 'connection_rate', None)
        self.peer_counts = getattr(args, 'connection_peers', Counter())
        self.peer_lock = getattr(args, 'connection_peer_lock', threading.Lock())
        super().__init__((args.listen, port), handler_cls or Handler)

    def get_request(self):
        raw, address = self.socket.accept()
        if address[0] not in self.allowed or (self.connection_rate and not self.connection_rate.allow(address[0])):
            raw.close()
            raise OSError("Client not allowed")
        raw.settimeout(10)
        self.events.write(event="tcp_connected", client=address[0],
                          port=self.server_address[1])
        return raw, address

    def process_request(self, request, address):
        with self.peer_lock:
            if self.peer_counts[address[0]] >= 8 or not self.capacity.acquire(blocking=False):
                request.close()
                return
            self.peer_counts[address[0]] += 1
        try:
            super().process_request(request, address)
        except BaseException:
            self.release_peer(address)
            raise

    def release_peer(self, address):
        with self.peer_lock:
            self.peer_counts[address[0]] -= 1
            if not self.peer_counts[address[0]]:
                del self.peer_counts[address[0]]
        self.capacity.release()

    def process_request_thread(self, raw, address):
        tls = None
        try:
            tls = self.context.wrap_socket(raw, server_side=True)
            self.events.write(event="tls_connected", client=address[0],
                              port=self.server_address[1],
                              version=tls.version(), cipher=tls.cipher()[0])
            self.finish_request(tls, address)
        except OSError as exc:
            self.events.write(event="tls_failed", client=address[0],
                              port=self.server_address[1], error=str(exc))
        except Exception as exc:
            self.events.write(event='request_failed', client=address[0], error_type=type(exc).__name__)
        finally:
            try:
                self.shutdown_request(tls if tls is not None else raw)
            finally:
                self.release_peer(address)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DS2Research/0.1"

    def log_message(self, *_):
        pass

    def collect(self):
        self.close_connection = True
        if self.headers.get("Transfer-Encoding"):
            self.send_error(501, "Chunked requests are not supported by this diagnostic collector")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if not 0 <= length <= (64 if self.server.public_mode else 512) * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        if len(body) != length:
            return
        name = uuid.uuid4().hex + ".body"
        if self.server.capture_raw:
            fd = os.open(self.server.events.directory / name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(body)
        self.server.events.write(event="http_request", client=self.client_address[0],
                                  port=self.server.server_address[1],
                                  method=self.command, path=redact_path(self.path, private=not self.server.capture_raw),
                                  host=self.headers.get("Host"),
                                  content_type=self.headers.get("Content-Type"),
                                  bytes=len(body), body_file=name if self.server.capture_raw else None,
                                  body_sha256=hashlib.sha256(body).hexdigest())
        response = (empty_inbox_reply(self.command, self.path)
                    if self.server.empty_inbox else None)
        rejection_status = None
        if self.server.cloud_store is not None:
            is_form = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() == "application/x-www-form-urlencoded"
            if self.command == "GET" or is_form:
                try:
                    actor = (self.server.authenticator.authenticate(self.command,self.path,body)
                             if self.server.authenticator is not None else None)
                    response = self.server.cloud_store.reply(self.command, self.path, body, actor=actor)
                except AuthError as exc:
                    self.server.events.write(event='auth_rejected', client=self.client_address[0],
                                             reason=str(exc))
                    response = None
                    rejection_status = 403
                except (OSError, ValueError, sqlite3.Error) as exc:
                    self.server.events.write(event="cloud_store_failed",
                                             error_type=type(exc).__name__)
                    response = None
        if response is None:
            status, content_type = rejection_status or 503, "text/plain"
            response = (b'Invalid or expired PSN ticket.\n' if rejection_status else
                        b'Unsupported or denied cloud request.\n')
        else:
            status, content_type = 200, "application/json"
        response_name = name.removesuffix(".body") + ".response"
        if self.server.capture_raw:
            fd = os.open(self.server.events.directory / response_name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(response)
        self.server.events.write(event="http_response", client=self.client_address[0],
                                  port=self.server.server_address[1], status=status,
                                  bytes=len(response), response_file=response_name if self.server.capture_raw else None,
                                  response_sha256=hashlib.sha256(response).hexdigest())
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(response)

    do_GET = collect
    do_POST = collect
    do_PUT = collect


def make_tls_context(cert, key, events):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # PS3 needs legacy TLS; silence only this intentional deprecated setting.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        context.minimum_version = ssl.TLSVersion.TLSv1
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers("ALL:@SECLEVEL=0")
    context.load_cert_chain(str(cert), str(key))
    cipher_names = {cipher["id"] & 0xffff: cipher["name"]
                    for cipher in context.get_ciphers()}
    cipher_names.update(IANA_CIPHER_NAMES)
    # CPython's documented debugging hook; records handshake metadata only.
    if hasattr(context, "_msg_callback"):
        context._msg_callback = lambda *values: tls_message(events, cipher_names, *values)
    return context


async def run(args):
    events = Events(args.capture_dir)
    listeners = []
    threads = []
    try:
        if args.matching_cn:
            fixtures = BASE / "matching-cn"
            context = make_tls_context(fixtures / "gds.pem", fixtures / "key.pem", events)
            thq_context = make_tls_context(fixtures / "thq.pem", fixtures / "key.pem", events)

            def select_certificate(sock, name, ctx):
                # GDS sends no SNI: use its exact CN as the default certificate.
                # THQ Connect sends its host name and receives its own exact CN.
                selected = GAME_HOSTS[1] if name == GAME_HOSTS[1] else GAME_HOSTS[0]
                if name == GAME_HOSTS[1]:
                    sock.context = thq_context
                events.write(event="tls_sni", hostname=name,
                             certificate_common_name=selected)
            context.set_servername_callback(select_certificate)
        else:
            context = make_tls_context(args.cert, args.key, events)
            context.set_servername_callback(
                lambda sock, name, ctx: events.write(event="tls_sni", hostname=name))
        cloud_store = CloudStore(args.database) if args.cloud else None
        # Bind all HTTPS listeners before starting threads. dns_probe.run drops
        # to SUDO_UID after binding DNS; no system configuration is changed.
        for port in dict.fromkeys(args.https_port or [443, 8443]):
            listeners.append(Collector(args, events, context, port, cloud_store))
        for https in listeners:
            thread = threading.Thread(target=https.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
            events.write(event="https_ready", listen=args.listen,
                         port=https.server_address[1],
                         certificate_profile="matching-cn" if args.matching_cn else "baseline",
                         game_api="experimental persistent cloud maps" if args.cloud else
                         "experimental empty TomeGift MAP_GET" if args.empty_inbox else "not implemented")
        await dns_probe.run(args)
    finally:
        for https in listeners[:len(threads)]:
            https.shutdown()
        for https in listeners:
            https.server_close()
        for thread in threads:
            thread.join()
        events.file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="192.168.0.219")
    parser.add_argument("--client", default="192.168.0.178")
    parser.add_argument("--port", type=int, default=53)
    parser.add_argument("--https-port", type=int, action="append",
                        help="HTTPS port; repeat for multiple listeners (default: 443 and 8443)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--empty-inbox", action="store_true",
                        help="Try the inferred version=1 empty TomeGift MAP_GET response")
    modes.add_argument("--cloud", action="store_true",
                       help="Persist single MAP_SET operations and serve full MAP_GET maps")
    parser.add_argument("--database", type=Path, default=BASE / "cloud.sqlite3")
    parser.add_argument("--upstream", default="127.0.0.53")
    parser.add_argument("--upstream-port", type=int, default=53)
    parser.add_argument("--capture-dir", type=Path, default=BASE)
    parser.add_argument("--cert", type=Path, default=BASE / "cert.pem")
    parser.add_argument("--key", type=Path, default=BASE / "key.pem")
    parser.add_argument("--matching-cn", action="store_true",
                        help="Test separate exact-CN self-signed certificates for GDS and THQ")
    args = parser.parse_args()
    args.redirect_ip = args.listen
    args.redirect_host = GAME_HOSTS
    args.log = args.capture_dir / "dns.jsonl"
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except PermissionError:
        parser.exit(1, "Ports 53 and 443 require administrator access. Run with sudo.\n")


if __name__ == "__main__":
    main()
