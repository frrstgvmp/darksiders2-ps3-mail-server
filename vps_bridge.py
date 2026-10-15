#!/usr/bin/env python3
"""Local DNS + byte-preserving TCP relay to a private VPS; PSN routing stays external."""
import argparse
import asyncio
import datetime
import ipaddress
import json
import os
from pathlib import Path
import signal

from access_control import AllowedPeers
import dns_probe
from lab_server import GAME_HOSTS


def event(**fields):
    print(json.dumps({'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), **fields}), flush=True)


class Relay:
    def __init__(self, target, allowed, events=event, maximum=32):
        self.target = target
        self.allowed = allowed
        self.events = events
        self.maximum = maximum
        self.tasks = set()

    async def handle(self, reader, writer, port):
        peer = writer.get_extra_info('peername')[0]
        if peer not in self.allowed or len(self.tasks) >= self.maximum:
            writer.close()
            await writer.wait_closed()
            return
        task = asyncio.current_task()
        self.tasks.add(task)
        remote = None
        pumps = []
        try:
            upstream_reader, remote = await asyncio.wait_for(asyncio.open_connection(self.target, port), 10)
            self.events(event='bridge_connected', client=peer, port=port, target=self.target)

            async def pipe(source, destination):
                while True:
                    data = await asyncio.wait_for(source.read(65536), 90)
                    if not data:
                        if destination.can_write_eof():
                            destination.write_eof()
                            await destination.drain()
                        return
                    destination.write(data)
                    await asyncio.wait_for(destination.drain(), 30)

            pumps = [asyncio.create_task(pipe(reader, remote)),
                     asyncio.create_task(pipe(upstream_reader, writer))]
            done, pending = await asyncio.wait(pumps, return_when=asyncio.FIRST_EXCEPTION)
            for complete in done:
                complete.result()
            await asyncio.gather(*pending)
        except (OSError, TimeoutError) as exc:
            self.events(event='bridge_failed', client=peer, port=port, error_type=type(exc).__name__)
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            for stream in [writer, remote]:
                if stream is not None:
                    stream.close()
                    try:
                        await asyncio.wait_for(stream.wait_closed(), 3)
                    except (OSError, TimeoutError):
                        pass
            self.tasks.discard(task)

    async def close(self):
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)


async def serve(args):
    relay = Relay(args.server, AllowedPeers([args.client + '/32', args.listen + '/32', '127.0.0.1/32']))
    listeners = []
    tasks = []
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        # Bind relays before dns_probe drops sudo privileges after binding DNS.
        for port in [443, 8443]:
            listeners.append(await asyncio.start_server(
                lambda reader, writer, port=port: relay.handle(reader, writer, port), args.listen, port))
        args.redirect_ip = args.listen
        args.redirect_host = GAME_HOSTS
        args.upstream_port = 53
        args.event_sink = event
        tasks = [asyncio.create_task(dns_probe.run(args)), asyncio.create_task(stop.wait())]
        event(event='bridge_ready', listen=args.listen, dns_port=args.port, tcp_ports=[443, 8443],
              target=args.server, tls='forwarded unchanged; no decryption', client=args.client)
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if not task.cancelled():
                task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for listener in listeners:
            listener.close()
            await listener.wait_closed()
        await relay.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True, help='Private VPS IPv4')
    parser.add_argument('--listen', default='192.168.0.219')
    parser.add_argument('--client', default='192.168.0.178')
    parser.add_argument('--upstream', default='127.0.0.53')
    parser.add_argument('--port', type=int, default=53, help='Local DNS port')
    parser.add_argument('--log', type=Path, default=Path(__file__).parent/'research/vps-bridge-dns.jsonl')
    args = parser.parse_args()
    for field in ('server', 'listen', 'client', 'upstream'):
        setattr(args, field, str(ipaddress.IPv4Address(getattr(args, field))))
    if args.server == args.listen:
        parser.error('VPS must differ from local listener')
    if args.listen == args.upstream and args.port == 53:
        parser.error('DNS upstream must not point back to listener')
    os.umask(0o077)
    try:
        asyncio.run(serve(args))
    except PermissionError:
        parser.exit(1, 'Ports 53 and 443 need sudo. Stop the previous local DNS receiver first.\n')
    except OSError as exc:
        parser.exit(1, f'Bridge setup failed: {exc}\n')


if __name__ == '__main__':
    main()
