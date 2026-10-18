import asyncio
import base64
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import time
import http.client
import ssl
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from cloud_api import CloudStore
from dns_probe import Probe, UDP
from psn_auth import AuthError, Principal, TicketVerifier
from service_limits import RateLimit
import test_service as _service_support

NOW=1792000000
SERVICE='UP1005-BLUS30829_00'


def make_ticket(key,name='alice',account=1,expires=NOW+3600,service=SERVICE,now=NOW,signature_size=56):
    def field(kind,value):return struct.pack('!HH',kind,len(value))+value
    def text(value,size):return value.encode().ljust(size,b'\0')
    body=b''.join([field(8,b'test-serial'.ljust(20,b'\0')),field(1,(256).to_bytes(4,'big')),
        field(7,((now-60)*1000).to_bytes(8,'big')),field(7,(expires*1000).to_bytes(8,'big')),
        field(2,account.to_bytes(8,'big')),field(4,text(name,32)),field(8,b'us\0\0'),
        field(4,b'b7\0\0'),field(8,text(service,24))])
    footer=field(8,bytes.fromhex('01020304'))+struct.pack('!HH',8,signature_size)
    size=4+len(body)+4+len(footer)+signature_size
    prefix=bytes.fromhex('31000000')+struct.pack('!I',size)+struct.pack('!HH',0x3000,len(body))+body+struct.pack('!HH',0x3002,len(footer)+signature_size)+footer
    signature=key.sign(prefix,ec.ECDSA(hashes.SHA1()))
    return prefix+signature.ljust(signature_size,b'\0')


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.key=ec.generate_private_key(ec.SECP192R1())
        point=self.key.public_key().public_numbers()
        self.config={'curve':'secp192r1','hash':'SHA-1','identifier':'01020304',
                     'x':hex(point.x)[2:],'y':hex(point.y)[2:],'service_ids':[SERVICE]}
        self.now=NOW
        self.verifier=TicketVerifier(key_config=self.config,clock=lambda:self.now)

    def test_signature_name_tampering_and_foreign_signer(self):
        ticket=make_ticket(self.key)
        self.assertEqual(self.verifier.verify_bytes(ticket).profile,'/psn/alice')
        tampered=ticket.replace(b'alice',b'bobby')
        with self.assertRaises(AuthError):self.verifier.verify_bytes(tampered)
        with self.assertRaises(AuthError):self.verifier.verify_bytes(make_ticket(ec.generate_private_key(ec.SECP192R1())))
        with self.assertRaises(AuthError):self.verifier.verify_bytes(make_ticket(self.key,service='UP0000-OTHER0001_00'))

    def test_expiry_is_rechecked_after_cache_hit(self):
        ticket=base64.b64encode(make_ticket(self.key,expires=NOW+1)).decode()
        path='/thqconnect/cloud/execute?'+urlencode({'auth':ticket})
        self.assertEqual(self.verifier.authenticate('GET',path,b'').profile,'/psn/alice')
        self.now=NOW+2
        with self.assertRaises(AuthError):self.verifier.authenticate('GET',path,b'')

    def test_duplicate_ticket_or_trailing_data_rejected(self):
        ticket=make_ticket(self.key)
        with self.assertRaises(AuthError):self.verifier.verify_bytes(ticket+b'\0')
        encoded=base64.b64encode(ticket).decode()
        with self.assertRaises(AuthError):self.verifier.authenticate('POST','/?'+urlencode({'auth':encoded}),urlencode({'auth':encoded}).encode())

    def test_short_der_signature_with_zero_padding_still_requires_valid_signature(self):
        # Synthetic authority only: fixed-width fields may contain >2 zeros.
        for _ in range(100):
            ticket=make_ticket(self.key,signature_size=58)
            if ticket[-3:]==b'\0\0\0':
                break
        else:
            self.fail('Could not generate a short synthetic DER signature')
        self.assertEqual(self.verifier.verify_bytes(ticket).profile,'/psn/alice')
        with self.assertRaises(AuthError):self.verifier.verify_bytes(ticket[:-1]+b'\1')
        with self.assertRaises(AuthError):self.verifier.verify_bytes(ticket.replace(b'alice',b'bobby'))


class ProtectedMailTests(unittest.TestCase):
    document = 'TomeGift'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=CloudStore(Path(self.temp.name)/'cloud.sqlite3')
        self.alice=Principal('/psn/alice','101',0)
        self.bob=Principal('/psn/bob','102',0)
        self.gift=base64.b64encode(b'BOD\xfd'+bytes(range(60))).decode()

    def request(self,actor,profile,op,key='',value=''):
        query=urlencode({'profileNames':profile,'ops':op,'docKeys':self.document,'keys':key,
                         'values':value,'version':'1','platform':'PS3_PSN','title':'Darksiders2'})
        return json.loads(self.store.reply('GET','/thqconnect/cloud/execute?'+query,b'',actor=actor))

    def test_sender_cannot_read_or_remove_recipient_gifts(self):
        self.request(self.bob,'/psn/bob','MAP_SET','existing',self.gift)
        other=base64.b64encode(b'BOD\xfd'+b'x'*60).decode()
        result=self.request(self.alice,'/psn/bob','MAP_SET','new',other)
        self.assertEqual(json.loads(result[1][0][1]),{'new':other})
        for op,key in [('MAP_GET',''),('GET',''),('MAP_REMOVE','existing'),('REMOVE','')]:
            with self.assertRaises(ValueError):self.request(self.alice,'/psn/bob',op,key)
        self.assertEqual(len(json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1])),2)
        self.request(self.bob,'/psn/bob','MAP_REMOVE','new')
        self.assertEqual(len(json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1])),1)

    def test_overwrite_and_account_takeover_are_denied(self):
        self.request(self.alice,'/psn/bob','MAP_SET','gift',self.gift)
        self.request(self.alice,'/psn/bob','MAP_SET','gift',self.gift)
        with self.assertRaises(ValueError):self.request(self.alice,'/psn/bob','MAP_SET','gift',base64.b64encode(b'BOD\xfd'+b'z'*60).decode())
        self.request(self.bob,'/psn/bob','MAP_GET')
        with self.assertRaises(ValueError):self.request(Principal('/psn/bob','999',0),'/psn/bob','MAP_GET')

    def test_mailbox_quota_rollback_preserves_existing_gifts(self):
        mapping={str(i):self.gift for i in range(128)}
        with sqlite3.connect(self.store.path) as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?)',('/psn/bob',self.document,json.dumps(mapping),0,0,''))
        with self.assertRaises(ValueError):self.request(self.alice,'/psn/bob','MAP_SET','extra',self.gift)
        self.assertEqual(len(json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1])),128)

    def test_map_entry_wire_metadata_survives_initialization_and_retry(self):
        carol=Principal('/psn/carol','103',0)
        with patch('cloud_api.time.time',return_value=1700000000):
            self.request(self.alice,'/psn/bob','MAP_SET','first',self.gift)
        with patch('cloud_api.time.time',return_value=1700000010):
            self.request(carol,'/psn/bob','MAP_SET','second',self.gift)
            self.request(self.alice,'/psn/bob','MAP_SET','first',self.gift)
            self.request(self.bob,'/psn/bob','SET')
        entries=json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1])
        self.assertEqual(entries,[
            ['first',[self.gift,'/psn/alice',1700000000]],
            ['second',[self.gift,'/psn/carol',1700000010]]])
        with sqlite3.connect(self.store.path) as db:
            stored=json.loads(db.execute('SELECT data FROM documents WHERE name=?',(self.document,)).fetchone()[0])
        self.assertEqual(stored,{'first':self.gift,'second':self.gift})

    def test_gift_envelope_and_whole_mailbox_replacement_are_checked(self):
        self.request(self.alice,'/psn/bob','MAP_SET','gift',self.gift)
        for value in ('invalid-base64',base64.b64encode(b'not-a-gift'*8).decode()):
            with self.assertRaises(ValueError):
                self.request(self.alice,'/psn/bob','MAP_SET','bad',value)
        with self.assertRaises(ValueError):
            self.request(self.bob,'/psn/bob','SET',value='{}')
        entries=json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1])
        self.assertEqual(entries[0][0],'gift')
        self.assertEqual(len(entries),1)


class JapaneseProtectedMailTests(ProtectedMailTests):
    document = 'TomeGiftJP'

    def test_regional_mailboxes_are_separate_and_japanese_batch_preserves_gifts(self):
        self.request(self.alice,'/psn/bob','MAP_SET','jp-gift',self.gift)
        query=urlencode({'profileNames':'/psn/bob,/psn/bob,/psn/bob',
            'ops':'MAP_GET,SET,SET','docKeys':'TomeGiftJP,TomeGiftJP,GameToWeb',
            'keys':',,','values':',,','policy':'0,1,1',
            'worldPerms':'-1,2,2','friendPerms':'-1,0,0',
            'version':'1','platform':'PS3_PSN','title':'Darksiders2'})
        reply=json.loads(self.store.reply('GET','/thqconnect/cloud/execute?'+query,b'',actor=self.bob))
        self.assertEqual(json.loads(reply[1][0][1])[0][:1],['jp-gift'])
        self.store=CloudStore(self.store.path)
        self.assertEqual(len(json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1])),1)
        self.document='TomeGift'
        self.assertEqual(json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1]),{})
        self.document='TomeGiftJP'
        self.request(self.bob,'/psn/bob','MAP_REMOVE','jp-gift')
        self.assertEqual(json.loads(self.request(self.bob,'/psn/bob','MAP_GET')[1][0][1]),{})


class PublicDnsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.args=SimpleNamespace(public_mode=True,listen='127.0.0.1',client=None,allowed_clients=[],
            redirect_ip='203.0.113.10',redirect_host=['thqc-darksiders2-ps3-na.thqconnect.com'],
            upstream='127.0.0.53',upstream_port=53,event_sink=lambda **kwargs:None)
        self.probe=Probe(self.args)

    @staticmethod
    def question(name,kind=1,klass=1):
        return struct.pack('!6H',17,256,1,0,0,0)+b''.join(bytes([len(x)])+x.encode() for x in name.split('.'))+b'\0'+struct.pack('!HH',kind,klass)

    async def test_game_redirect_and_ipv6_nodata_do_not_use_upstream(self):
        peer='198.51.100.222'
        with patch('dns_probe.forward',side_effect=AssertionError('Redirect must stay local')):
            reply=await self.probe.answer(self.question('thqc-darksiders2-ps3-na.thqconnect.com'),peer)
            self.assertEqual(reply[-4:],bytes([203,0,113,10]))
            reply=await self.probe.answer(self.question('thqc-darksiders2-ps3-na.thqconnect.com',28),peer)
            self.assertEqual(struct.unpack_from('!HH',reply,4),(1,0))
            self.assertEqual(reply[3]&15,0)

    async def test_general_address_reverse_and_other_record_queries_forward_unchanged(self):
        # Include Windows nslookup's reverse lookup and names outside PSN zones.
        for name,kind in [('example.org',1),('example.org',28),
                          ('202.178.232.193.in-addr.arpa',12),
                          ('example.org',16),('_service._tcp.example.org',33),
                          ('www.playstation.com',1)]:
            packet=self.question(name,kind)
            expected=packet[:2]+struct.pack('!5H',0x8183,1,0,0,0)+packet[12:]
            with self.subTest(name=name,kind=kind), patch('dns_probe.forward',return_value=expected) as forward:
                self.assertEqual(await self.probe.answer(packet,'198.51.100.222'),expected)
                forward.assert_called_once_with(packet,self.args.upstream,self.args.upstream_port)

    async def test_meta_queries_non_in_class_and_rate_excess_do_not_forward(self):
        with patch('dns_probe.forward',side_effect=AssertionError('Query must be refused locally')):
            for kind in (0,41,249,250,251,252,253,254,255):
                self.assertEqual((await self.probe.answer(self.question('example.org',kind),'198.51.100.222'))[3]&15,5)
            self.assertEqual((await self.probe.answer(self.question('example.org',1,3),'198.51.100.222'))[3]&15,5)
            self.probe.rate=RateLimit(1,1,10,10)
            await self.probe.answer(self.question('example.org',255),'198.51.100.222')
            self.assertIsNone(await self.probe.answer(self.question('example.org'),'198.51.100.222'))

    async def test_udp_forwarding_and_truncated_reply_tcp_retry(self):
        loop=asyncio.get_running_loop()
        queries=[]
        def response(packet):
            kind=struct.unpack_from('!H',packet,len(packet)-4)[0]
            payload=(b'\xe5'+b'x'*229)*3 if kind==16 else bytes([192,0,2,25])
            return (packet[:2]+struct.pack('!5H',0x8180,1,1,0,0)+packet[12:]
                    +b'\xc0\x0c'+struct.pack('!HHIH',kind,1,60,len(payload))+payload)
        class Upstream(asyncio.DatagramProtocol):
            def connection_made(self,transport):self.transport=transport
            def datagram_received(self,packet,address):
                queries.append(packet)
                self.transport.sendto(response(packet),address)
        class Client(asyncio.DatagramProtocol):
            def __init__(self):self.received=asyncio.Queue()
            def datagram_received(self,packet,address):self.received.put_nowait(packet)
        upstream,_=await loop.create_datagram_endpoint(Upstream,local_addr=('127.0.0.1',0))
        self.args.upstream='127.0.0.1'
        self.args.upstream_port=upstream.get_extra_info('sockname')[1]
        tcp=await asyncio.start_server(self.probe.tcp,'127.0.0.1',0)
        address=tcp.sockets[0].getsockname()
        udp,protocol=await loop.create_datagram_endpoint(lambda:UDP(self.probe),local_addr=address)
        client,received=await loop.create_datagram_endpoint(Client,local_addr=('127.0.0.1',0))
        writer=None
        try:
            packet=self.question('example.org')
            client.sendto(packet,address)
            self.assertEqual(await asyncio.wait_for(received.received.get(),2),response(packet))
            large=self.question('example.org',16)
            client.sendto(large,address)
            truncated=await asyncio.wait_for(received.received.get(),2)
            self.assertLessEqual(len(truncated),512)
            self.assertTrue(truncated[2]&2)
            self.assertEqual(struct.unpack_from('!HH',truncated,4),(1,0))
            reader,writer=await asyncio.open_connection(*address)
            writer.write(struct.pack('!H',len(large))+large)
            await writer.drain()
            size=struct.unpack('!H',await asyncio.wait_for(reader.readexactly(2),2))[0]
            self.assertEqual(await asyncio.wait_for(reader.readexactly(size),2),response(large))
            self.assertEqual(queries,[packet,large,large])
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
            client.close();udp.close();upstream.close()
            tcp.close()
            await tcp.wait_closed()
            for task in list(protocol.tasks):task.cancel()
            await asyncio.gather(*list(protocol.tasks),return_exceptions=True)


class LimitTests(unittest.TestCase):
    def test_rate_refill_and_memory_bound(self):
        now=[0.0]
        limit=RateLimit(1,2,10,20,max_peers=2,clock=lambda:now[0])
        self.assertTrue(limit.allow('a'));self.assertTrue(limit.allow('a'));self.assertFalse(limit.allow('a'))
        now[0]=1;self.assertTrue(limit.allow('a'))
        limit.allow('b');limit.allow('c');self.assertLessEqual(len(limit.peers),2)



class PublicServiceIntegration(_service_support.ServiceIntegration):
    def setUp(self):
        super().setUp()
        self.stop()
        self.signer=ec.generate_private_key(ec.SECP192R1())
        numbers=self.signer.public_key().public_numbers()
        key_path=self.root/'ticket-key.json'
        key_path.write_text(json.dumps({'curve':'secp192r1','hash':'SHA-1','identifier':'01020304',
             'x':hex(numbers.x)[2:],'y':hex(numbers.y)[2:],'service_ids':[SERVICE]}))
        config=json.loads(self.config.read_text());config.update(public_mode=True,allowed_clients=[],psn_key=str(key_path))
        self.config.write_text(json.dumps(config))
        self.start()

    def request_as(self,name,profile,op,key='',value='',authenticated=True,document='TomeGift'):
        now=int(time.time())
        ticket=base64.b64encode(make_ticket(self.signer,name=name,account=1 if name=='alice' else 2,
                              expires=now+3600,now=now)).decode()
        query={'profileNames':profile,'ops':op,'docKeys':document,'keys':key,'values':value,
               'version':'1','platform':'PS3_PSN','title':'Darksiders2'}
        if authenticated:query['auth']=ticket
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
        conn=http.client.HTTPSConnection('127.0.0.1',self.https_port,timeout=3,context=context)
        conn.request('GET','/thqconnect/cloud/execute?'+urlencode(query))
        response=conn.getresponse();body=response.read();conn.close()
        return response.status,body

    def test_japanese_mailbox_authenticated_delivery_and_claim(self):
        gift=base64.b64encode(b'BOD\xfd'+b'japanese-test-envelope'*3).decode()
        def call(name,profile,op,**kw):
            return self.request_as(name,profile,op,document='TomeGiftJP',**kw)
        self.assertEqual(call('bob','/psn/bob','MAP_GET',authenticated=False)[0],403)
        self.assertEqual(call('alice','/psn/bob','MAP_SET',key='jp-gift',value=gift)[0],200)
        self.assertNotEqual(call('alice','/psn/bob','MAP_GET')[0],200)
        status,body=call('bob','/psn/bob','MAP_GET')
        self.assertEqual(status,200)
        entry=json.loads(json.loads(body)[1][0][1])[0]
        self.assertEqual(entry[:1],['jp-gift'])
        self.assertEqual(entry[1][:2],[gift,'/psn/alice'])
        self.assertEqual(call('bob','/psn/bob','MAP_REMOVE',key='jp-gift')[0],200)
        self.assertEqual(json.loads(json.loads(call('bob','/psn/bob','MAP_GET')[1])[1][0][1]),{})

    def test_delivery_restart_claim_dns_and_private_logs(self):
        # A slow unauthenticated TLS client cannot block the accept loop.
        stalled=[]
        import socket
        try:
            for _ in range(6):stalled.append(socket.create_connection(('127.0.0.1',self.https_port),timeout=2))
            self.assertTrue(self.https('/health')['ok'])
        finally:
            for sock in stalled:sock.close()
        self.assertEqual(self.request_as('alice','/psn/alice','MAP_GET',authenticated=False)[0],403)
        gift=base64.b64encode(b'BOD\xfd'+b'validated-test-envelope'*3).decode()
        status,body=self.request_as('alice','/psn/bob','MAP_SET','public-gift',gift)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(json.loads(body)[1][0][1]),{'public-gift':gift})
        self.assertNotEqual(self.request_as('alice','/psn/bob','MAP_GET')[0],200)
        self.stop();self.start()
        status,body=self.request_as('bob','/psn/bob','MAP_GET')
        self.assertEqual(status,200)
        entries=json.loads(json.loads(body)[1][0][1])
        self.assertEqual(entries[0][0],'public-gift')
        self.assertEqual(entries[0][1][0],gift)
        self.assertEqual(entries[0][1][1],'/psn/alice')
        self.assertEqual(self.request_as('bob','/psn/bob','MAP_REMOVE','public-gift')[0],200)
        from dns_probe import question
        packet=struct.pack('!6H',72,256,1,0,0,0)+b'\x07example\x03org\0'+struct.pack('!HH',255,1)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.2',0));sock.settimeout(2)
            sock.sendto(packet,('127.0.0.1',self.dns_port))
            self.assertEqual(sock.recv(4096)[3]&15,5)
        self.stop()
        log=(self.root/'state/logs/server.jsonl').read_text()
        self.assertNotIn(gift,log)
        self.assertEqual(list((self.root/'state/logs').glob('*.body')),[])

if __name__=='__main__':unittest.main()
