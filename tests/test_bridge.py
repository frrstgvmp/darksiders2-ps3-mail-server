import asyncio
import unittest

from access_control import AllowedPeers
from vps_bridge import Relay


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bytes_and_half_close_survive_relay(self):
        received = []
        async def upstream(reader, writer):
            payload = await reader.read()
            received.append(payload)
            writer.write(b'reply:' + payload)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        async with await asyncio.start_server(upstream, '127.0.0.1', 0) as backend:
            port = backend.sockets[0].getsockname()[1]
            relay = Relay('127.0.0.1', AllowedPeers(['127.0.0.1/32']), events=lambda **kwargs: None)
            async with await asyncio.start_server(lambda r,w:relay.handle(r,w,port), '127.0.0.1', 0) as frontend:
                reader, writer = await asyncio.open_connection('127.0.0.1', frontend.sockets[0].getsockname()[1])
                payload = bytes(range(256)) * 1024
                writer.write(payload); await writer.drain(); writer.write_eof()
                self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'reply:' + payload)
                writer.close(); await writer.wait_closed()
                self.assertEqual(received, [payload])
            await relay.close()

    async def test_unlisted_peer_gets_no_upstream_connection(self):
        connections = []
        async def upstream(reader, writer):
            connections.append(True); writer.close(); await writer.wait_closed()
        async with await asyncio.start_server(upstream, '127.0.0.1', 0) as backend:
            relay = Relay('127.0.0.1', AllowedPeers(['127.0.0.2/32']), events=lambda **kwargs: None)
            async with await asyncio.start_server(lambda r,w:relay.handle(r,w,backend.sockets[0].getsockname()[1]), '127.0.0.1', 0) as frontend:
                reader, writer = await asyncio.open_connection('127.0.0.1', frontend.sockets[0].getsockname()[1])
                self.assertEqual(await asyncio.wait_for(reader.read(), 2), b'')
                self.assertEqual(connections, [])
                writer.close(); await writer.wait_closed()
            await relay.close()
