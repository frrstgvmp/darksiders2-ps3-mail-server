#!/usr/bin/env python3
"""Darksiders II DNS/HTTPS mail service with public or private access, configured by JSON."""
import argparse
import asyncio
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sqlite3
import ssl
import threading
from collections import Counter
from types import SimpleNamespace

from cloud_api import CloudStore
from psn_auth import TicketVerifier
from service_limits import RateLimit
import dns_probe
from lab_server import Collector, Handler, GAME_HOSTS, make_tls_context


class ServiceEvents:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.Lock()
        self.handler = RotatingFileHandler(directory / 'server.jsonl', maxBytes=5 * 1024 * 1024,
                                           backupCount=3, encoding='utf-8')
        self.handler.setFormatter(logging.Formatter('%(message)s'))

    def write(self, **values):
        import datetime
        line = json.dumps({'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), **values}, ensure_ascii=False)
        with self.lock:
            self.handler.emit(logging.makeLogRecord({'msg': line, 'levelno': logging.INFO, 'levelname': 'INFO'}))
            print(line, flush=True)

    def close(self):
        self.handler.close()


class ServiceHandler(Handler):
    server_version = 'Darksiders2Mail/0.4'

    def do_GET(self):
        if self.path == '/health':
            with sqlite3.connect(self.server.cloud_store.path) as connection:
                connection.execute('SELECT 1').fetchone()
            response = b'{"ok":true,"service":"darksiders2-mail","ofw_verified":false}\n'
            self.close_connection = True
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(response)
        else:
            self.collect()


def configuration(path, state_override=None):
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError('Config must be a JSON object')
    def absolute(value):
        p = Path(value).expanduser()
        return (path.parent / p).resolve() if not p.is_absolute() else p.resolve()
    public = str(ipaddress.IPv4Address(data['public_ip']))
    listen = str(ipaddress.IPv4Address(data.get('listen', public)))
    clients = data.get('allowed_clients')
    public_mode = data.get('public_mode', False)
    if type(public_mode) is not bool:
        raise ValueError('public_mode must be boolean')
    if clients is None and public_mode:
        clients = []
    if not isinstance(clients, list) or (not clients and not public_mode):
        raise ValueError('allowed_clients must explicitly list the testers public IPs/CIDRs')
    networks = [ipaddress.ip_network(value, strict=False) for value in clients]
    if any(network.version != 4 or network.prefixlen < 24 for network in networks):
        raise ValueError('Use explicit IPv4 addresses (/32 preferred); broad network access is not supported')
    hosts = data.get('redirect_hosts', GAME_HOSTS)
    if not isinstance(hosts, list) or not hosts or any(not isinstance(h, str) or not h.endswith('.thqconnect.com') for h in hosts):
        raise ValueError('redirect_hosts must be exact THQ Connect hostnames')
    ports = data.get('https_ports', [443, 8443])
    if not isinstance(ports, list) or not ports or any(type(port) is not int or not 1 <= port <= 65535 for port in ports):
        raise ValueError('Invalid HTTPS ports')
    dns_port = data.get('dns_port', 53)
    if type(dns_port) is not int or not 1 <= dns_port <= 65535:
        raise ValueError('Invalid DNS port')
    dns_ports = data.get('dns_ports', [dns_port])
    if not isinstance(dns_ports, list) or not dns_ports or any(type(port) is not int or not 1 <= port <= 65535 for port in dns_ports):
        raise ValueError('Invalid DNS ports')
    state = Path(state_override).resolve() if state_override else absolute(data.get('state_dir', '/var/lib/darksiders2-server'))
    if public_mode and data.get('capture_raw',False):
        raise ValueError('Public mode requires raw captures to be disabled')
    if type(data.get('verify_psn_tickets',False)) is not bool:
        raise ValueError('verify_psn_tickets must be boolean')
    verify_tickets = public_mode or data.get('verify_psn_tickets',False)
    default_key = Path(__file__).resolve().parent / 'assets/psn-darksiders2-key.json'
    auth_key = (absolute(data['psn_key']) if data.get('psn_key') else default_key) if verify_tickets else None
    return SimpleNamespace(listen=listen, client=None, allowed_clients=[str(n) for n in networks],
                           redirect_ip=public, redirect_host=hosts, port=dns_port,
                           dns_ports=list(dict.fromkeys(dns_ports)),
                           upstream=str(ipaddress.IPv4Address(data.get('dns_upstream', '1.1.1.1'))),
                           upstream_port=53, log=state / 'logs/dns.jsonl',
                           cert=absolute(data['cloud_cert']), key=absolute(data['cloud_key']),
                           gds_cert=absolute(data['gds_cert']) if data.get('gds_cert') else None,
                           gds_key=absolute(data['gds_key']) if data.get('gds_key') else None,
                           https_port=list(dict.fromkeys(ports)), database=state / 'cloud.sqlite3',
                           capture_dir=state / 'logs', capture_raw=bool(data.get('capture_raw', False)),
                           empty_inbox=False, state_dir=state, public_mode=public_mode,
                           psn_key=auth_key)


async def serve(args):
    os.umask(0o077)
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    events = ServiceEvents(args.capture_dir)
    args.event_sink = events.write
    args.authenticator = TicketVerifier(args.psn_key) if args.psn_key else None
    args.connection_slots = threading.BoundedSemaphore(32)
    args.connection_peers = Counter()
    args.connection_peer_lock = threading.Lock()
    args.connection_rate = RateLimit(5,20,40,80) if args.public_mode else None
    args.dns_rate = RateLimit(20,60,300,600) if args.public_mode else None
    listeners, threads = [], []
    dns_tasks = []
    waiter = None
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        context = make_tls_context(args.cert, args.key, events)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers('AES256-SHA256:AES128-SHA256:AES256-SHA:AES128-SHA:@SECLEVEL=0')
        if args.public_mode:
            context._msg_callback = None
        context.set_servername_callback(lambda sock, name, ctx: events.write(event='tls_sni', hostname=name))
        gds_context = None
        if args.gds_cert and args.gds_key:
            gds_context = make_tls_context(args.gds_cert, args.gds_key, events)
            gds_context.minimum_version = ssl.TLSVersion.TLSv1_2
            gds_context.set_ciphers('AES256-SHA256:AES128-SHA256:AES256-SHA:AES128-SHA:@SECLEVEL=0')
            gds_context.set_servername_callback(lambda sock, name, ctx: events.write(event='tls_sni', hostname=name))
        store = CloudStore(args.database)
        for port in args.https_port:
            ctx = gds_context if port == 443 and gds_context else context
            listener = Collector(args, events, ctx, port, store, handler_cls=ServiceHandler)
            listeners.append(listener)
        for listener in listeners:
            thread = threading.Thread(target=listener.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
            events.write(event='https_ready', listen=args.listen, port=listener.server_address[1],
                         game_api='persistent cloud documents/maps', raw_capture=args.capture_raw)
        events.write(event='service_ready', database=str(args.database), allowed_clients=args.allowed_clients,
                     public_mode=args.public_mode, psn_tickets_verified=bool(args.authenticator), ofw_verified=False)
        for port in args.dns_ports:
            dns_args = SimpleNamespace(**(vars(args) | {'port': port, 'log': args.capture_dir / f'dns-{port}.jsonl'}))
            dns_tasks.append(asyncio.create_task(dns_probe.run(dns_args)))
        waiter = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([*dns_tasks, waiter], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    finally:
        for task in [*dns_tasks, waiter]:
            if task:
                task.cancel()
        await asyncio.gather(*(task for task in [*dns_tasks, waiter] if task), return_exceptions=True)
        for listener in listeners[:len(threads)]:
            await asyncio.to_thread(listener.shutdown)
        for listener in listeners:
            listener.server_close()
        for thread in threads:
            thread.join()
        events.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--check', action='store_true')
    opts = parser.parse_args()
    try:
        args = configuration(opts.config.resolve(), opts.state_dir)
        if args.psn_key:
            TicketVerifier(args.psn_key)
        for cert, key in [(args.cert, args.key), (args.gds_cert, args.gds_key)]:
            if cert is None and key is None:
                continue
            if cert is None or key is None:
                raise ValueError('Each certificate requires a matching private key')
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.set_ciphers('AES256-SHA256:@SECLEVEL=0')
            context.load_cert_chain(cert, key)
        if args.listen == args.upstream and args.upstream_port in args.dns_ports:
            raise ValueError('DNS upstream points back to the listener')
        if opts.check:
            print('Configuration and TLS keys/chains loaded; no listeners started')
        else:
            asyncio.run(serve(args))
    except (KeyError, ValueError, OSError) as exc:
        parser.exit(1, f'Server setup failed: {exc}\n')


if __name__ == '__main__':
    main()
