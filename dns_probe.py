#!/usr/bin/env python3
"""DNS forwarder with optional exact-host game redirects and bounded public access."""
import argparse
import asyncio
import datetime
import json
import os
import socket
import struct
from collections import Counter
from pathlib import Path
from access_control import AllowedPeers

# These are reserved/meta operations rather than ordinary record lookups.
# Public forwarding serves all Internet names; it does not offer transfers,
# transaction authentication, or ANY/MAILA/MAILB queries.
PUBLIC_BLOCKED_TYPES = frozenset((0, 41, 249, 250, 251, 252, 253, 254, 255))


def question(packet):
    if len(packet) < 12:
        raise ValueError("Short DNS header")
    flags, count = struct.unpack_from(">HH", packet, 2)
    if flags & 0x8000 or flags & 0x7800 or count != 1:
        raise ValueError("Expected one standard DNS question")
    offset, labels = 12, []
    while True:
        if offset >= len(packet):
            raise ValueError("Incomplete name")
        size = packet[offset]
        offset += 1
        if not size:
            break
        if size > 63 or offset + size > len(packet):
            raise ValueError("Invalid label")
        labels.append(packet[offset:offset + size].decode("ascii"))
        offset += size
        if offset - 12 > 254:
            raise ValueError("Name too long")
    if offset + 4 > len(packet):
        raise ValueError("Incomplete question")
    kind, klass = struct.unpack_from(">HH", packet, offset)
    return ".".join(labels).lower(), kind, klass


def error_response(packet, rcode):
    if len(packet) < 12:
        return None
    flags = 0x8080 | (struct.unpack_from(">H", packet, 2)[0] & 0x0100) | rcode
    return packet[:2] + struct.pack(">5H", flags, 0, 0, 0, 0)


def redirect_response(packet, name, kind, address):
    end = 12 + sum(len(label) + 1 for label in name.split(".")) + 1 + 4
    flags = 0x8080 | (struct.unpack_from(">H", packet, 2)[0] & 0x0100)
    count = 1 if kind == 1 else 0
    answer = (packet[:2] + struct.pack(">5H", flags, 1, count, 0, 0)
              + packet[12:end])
    if kind == 1:
        answer += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 5, 4) + socket.inet_aton(address)
    return answer


def exact(sock, size):
    result = bytearray()
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise OSError("Upstream TCP connection closed")
        result.extend(chunk)
    return bytes(result)


def forward(packet, upstream, port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.connect((upstream, port))
        sock.send(packet)
        answer = sock.recv(65535)
    if len(answer) < 12 or answer[:2] != packet[:2] or not answer[2] & 0x80:
        raise OSError("Invalid upstream response")
    if answer[2] & 2:  # Truncation: fetch the full reply over TCP.
        with socket.create_connection((upstream, port), timeout=3) as sock:
            sock.sendall(struct.pack(">H", len(packet)) + packet)
            answer = exact(sock, struct.unpack(">H", exact(sock, 2))[0])
        if len(answer) < 12 or answer[:2] != packet[:2] or not answer[2] & 0x80:
            raise OSError("Invalid upstream TCP response")
    return answer


class Probe:
    def __init__(self, args):
        self.args = args
        self.allowed = AllowedPeers.from_args(args)
        self.log = None
        self.public_mode = getattr(args,'public_mode',False)
        self.rate = getattr(args,'dns_rate',None)
        self.tcp_peers = Counter()

    def event(self, **values):
        sink = getattr(self.args, 'event_sink', None)
        if sink is not None:
            sink(**values)
            return
        row = {"time": datetime.datetime.now(datetime.timezone.utc).isoformat(), **values}
        line = json.dumps(row, ensure_ascii=False)
        self.log.write(line + "\n")
        self.log.flush()
        print(line, flush=True)

    async def answer(self, packet, peer):
        if peer not in self.allowed:
            return error_response(packet, 5)
        if self.rate and not self.rate.allow(peer):
            return None
        try:
            name, kind, klass = question(packet)
        except (ValueError, UnicodeError):
            return error_response(packet, 1)
        if self.public_mode:
            if klass != 1 or kind in PUBLIC_BLOCKED_TYPES:
                return error_response(packet,5)
        redirect_ip = getattr(self.args, "redirect_ip", None)
        redirect_hosts = getattr(self.args, "redirect_host", ())
        if redirect_ip and name in redirect_hosts and klass == 1 and kind in (1, 28):
            reply = redirect_response(packet, name, kind, redirect_ip)
            self.event(client=peer, name=name, qtype=kind, qclass=klass,
                       rcode=0, answers=int(kind == 1), thq=True, redirect=redirect_ip)
            return reply
        try:
            reply = await asyncio.to_thread(forward, packet, self.args.upstream,
                                            self.args.upstream_port)
            rcode = reply[3] & 15
            ancount = struct.unpack_from(">H", reply, 6)[0]
            self.event(client=peer, name=name, qtype=kind, qclass=klass,
                       rcode=rcode, answers=ancount,
                       thq=name == "thqconnect.com" or name.endswith(".thqconnect.com"))
            return reply
        except OSError as exc:
            self.event(client=peer, name=name, qtype=kind, upstream_error=str(exc))
            return error_response(packet, 2)

    async def tcp(self, reader, writer):
        peer = writer.get_extra_info("peername")[0]
        if self.public_mode and (sum(self.tcp_peers.values()) >= 32 or self.tcp_peers[peer] >= 4):
            writer.close()
            await writer.wait_closed()
            return
        self.tcp_peers[peer] += 1
        try:
            for _ in range(32):
                prefix = await asyncio.wait_for(reader.readexactly(2), 10)
                size = struct.unpack(">H", prefix)[0]
                if not 12 <= size <= 4096:
                    break
                packet = await asyncio.wait_for(reader.readexactly(size), 10)
                reply = await self.answer(packet, peer)
                if reply:
                    writer.write(struct.pack(">H", len(reply)) + reply)
                    await writer.drain()
        except (asyncio.IncompleteReadError, TimeoutError, OSError):
            pass
        finally:
            self.tcp_peers[peer] -= 1
            if not self.tcp_peers[peer]:
                del self.tcp_peers[peer]
            writer.close()
            await writer.wait_closed()


class UDP(asyncio.DatagramProtocol):
    def __init__(self, probe):
        self.probe = probe
        self.tasks = set()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, packet, address):
        if len(self.tasks) >= 64:
            return
        async def respond():
            reply = await self.probe.answer(packet, address[0])
            if reply and self.probe.public_mode and len(reply)>512:
                # Legacy-size UDP response with TC; client can retry over TCP.
                flags = struct.unpack_from('>H',reply,2)[0] | 0x0200
                qend = 12
                while qend<len(packet) and packet[qend]:
                    qend += 1+packet[qend]
                qend += 5
                reply = reply[:2]+struct.pack('>5H',flags,1,0,0,0)+packet[12:qend]
            if reply:
                self.transport.sendto(reply, address)
        task = asyncio.create_task(respond())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


async def run(args):
    probe = Probe(args)
    loop = asyncio.get_running_loop()
    tcp = await asyncio.start_server(probe.tcp, args.listen, args.port)
    try:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDP(probe), local_addr=(args.listen, args.port))
    except BaseException:
        tcp.close()
        await tcp.wait_closed()
        raise
    # Bind privileged ports first, then run and write logs as the invoking user.
    if os.getuid() == 0 and "SUDO_UID" in os.environ:
        os.setgroups([])
        os.setgid(int(os.environ["SUDO_GID"]))
        os.setuid(int(os.environ["SUDO_UID"]))
    try:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as probe.log:
            probe.event(event="ready", listen=args.listen, port=args.port,
                        client=args.client, upstream=args.upstream,
                        mode="selected-host redirects" if getattr(args, "redirect_ip", None)
                             else "forward unchanged")
            async with tcp:
                await tcp.serve_forever()
    finally:
        transport.close()
        for task in protocol.tasks:
            task.cancel()
        tcp.close()
        await tcp.wait_closed()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="192.168.0.219")
    parser.add_argument("--client", default="192.168.0.178")
    parser.add_argument("--port", type=int, default=53)
    parser.add_argument("--upstream", default="127.0.0.53")
    parser.add_argument("--upstream-port", type=int, default=53)
    parser.add_argument("--redirect-ip", help="Optional local lab-server IPv4 address")
    parser.add_argument("--redirect-host", action="append", default=[],
                        help="Exact hostname to redirect; all other queries are forwarded")
    parser.add_argument("--log", type=Path, default=Path(__file__).parent / "research/dns-probe.jsonl")
    args = parser.parse_args()
    if args.listen == args.upstream and args.port == args.upstream_port:
        parser.error("The upstream must not point back to this listener")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except PermissionError:
        parser.exit(1, "Port 53 requires administrator access. Run this script with sudo.\n")


if __name__ == "__main__":
    main()
