import json
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlencode

from access_control import AllowedPeers
from ds2_server import configuration
from generate_server_certificates import generate

BASE = Path(__file__).resolve().parents[1]


def dns_exact(sock, size):
    data = b''
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise OSError('Short DNS response')
        data += part
    return data


class AccessTests(unittest.TestCase):
    def test_explicit_peers_only(self):
        peers = AllowedPeers(['192.0.2.10/32', '198.51.100.0/24'])
        self.assertIn('192.0.2.10', peers)
        self.assertIn('198.51.100.42', peers)
        self.assertNotIn('192.0.2.11', peers)
        self.assertNotIn('203.0.113.4', peers)
        self.assertNotIn('not an ip', peers)

    def test_service_rejects_public_resolver_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            path.write_text(json.dumps({'public_ip':'192.0.2.1','allowed_clients':['0.0.0.0/0']}))
            with self.assertRaises(ValueError):
                configuration(path)


class ServiceIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        generate(self.root/'pki',['thqc-darksiders2-ps3-na.thqconnect.com'],'ds2.gds.thqconnect.com')
        def port():
            with socket.socket() as s:
                s.bind(('127.0.0.1',0))
                return s.getsockname()[1]
        self.https_port, self.dns_port, self.extra_dns_port = port(), port(), port()
        self.config = self.root/'config.json'
        self.config.write_text(json.dumps({'listen':'127.0.0.1','public_ip':'127.0.0.1',
            'allowed_clients':['127.0.0.1/32'],'dns_upstream':'127.0.0.53',
            'dns_port':self.dns_port,'dns_ports':[self.dns_port,self.extra_dns_port],
            'https_ports':[self.https_port],
            'cloud_cert':'pki/cloud-fullchain.pem','cloud_key':'pki/cloud.key',
            'state_dir':str(self.root/'state'),'capture_raw':False}))
        self.proc = None
        self.addCleanup(self.stop)
        self.start()

    def start(self):
        self.proc = subprocess.Popen([sys.executable,str(BASE/'ds2_server.py'),'--config',str(self.config)],
                                      cwd=BASE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        for _ in range(100):
            if self.proc.poll() is not None:
                self.fail(self.proc.communicate()[0].decode())
            try:
                with socket.create_connection(('127.0.0.1',self.https_port),timeout=.1):
                    pass
                return
            except OSError:
                time.sleep(.05)
        self.fail('Server failed to start')

    def stop(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
            output = self.proc.communicate(timeout=8)[0]
            if self.proc.returncode != 0:
                self.fail(output.decode())
            self.proc = None

    def https(self,path,method='GET',body=b''):
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname=False
        ctx.verify_mode=ssl.CERT_NONE  # Transport/API test, not PS3 certificate validation.
        ctx.maximum_version=ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers('AES256-SHA256:@SECLEVEL=0')
        with socket.create_connection(('127.0.0.1',self.https_port),timeout=3) as tcp:
            with ctx.wrap_socket(tcp,server_hostname='thqc-darksiders2-ps3-na.thqconnect.com') as tls:
                request=(f'{method} {path} HTTP/1.1\r\nHost: thqc-darksiders2-ps3-na.thqconnect.com\r\n'
                         f'Content-Type: application/x-www-form-urlencoded\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()+body
                tls.sendall(request)
                data=b''
                while True:
                    chunk=tls.recv(65536)
                    if not chunk:break
                    data+=chunk
        head,payload=data.split(b'\r\n\r\n',1)
        self.assertIn(b' 200 ',head.split(b'\r\n')[0])
        return json.loads(payload)

    def query(self,operation,key='',value='',method='GET'):
        params={'profileNames':'/psn/recipient','ops':operation,'docKeys':'TomeGift',
                'keys':key,'values':value,'version':'1','platform':'PS3_PSN','title':'Darksiders2',
                'auth':'TEST-AUTH-DO-NOT-LOG'}
        form=urlencode(params)
        if method=='POST':return self.https('/thqconnect/cloud/execute','POST',form.encode())
        return self.https('/thqconnect/cloud/execute?'+form)

    def test_delivery_restart_claim_dns_and_private_logs(self):
        self.assertTrue(self.https('/health')['ok'])
        self.query('MAP_SET','gift-1','opaque-real-item-data',method='POST')
        self.stop()
        self.start()
        from test_cloud_api import received_values
        self.assertEqual(received_values(self.query('MAP_GET')[1][0][1]),{'gift-1':'opaque-real-item-data'})
        self.query('MAP_REMOVE','gift-1')
        self.assertEqual(json.loads(self.query('MAP_GET')[1][0][1]),{})
        labels='thqc-darksiders2-ps3-na.thqconnect.com'.split('.')
        packet=struct.pack('>6H',123,0x100,1,0,0,0)+b''.join(bytes([len(s)])+s.encode() for s in labels)+b'\0'+struct.pack('>HH',1,1)
        for port in (self.dns_port,self.extra_dns_port):
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
                udp.settimeout(2)
                udp.sendto(packet,('127.0.0.1',port))
                answer=udp.recv(4096)
                self.assertEqual(struct.unpack_from('>H',answer,6)[0],1)
                self.assertEqual(answer[-4:],socket.inet_aton('127.0.0.1'))
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
                udp.bind(('127.0.0.2',0));udp.settimeout(2)
                udp.sendto(packet,('127.0.0.1',port))
                self.assertEqual(udp.recv(4096)[3]&15,5)
            with socket.create_connection(('127.0.0.1',port),timeout=2) as tcp:
                tcp.sendall(struct.pack('>H',len(packet))+packet)
                size=struct.unpack('>H',dns_exact(tcp,2))[0]
                self.assertEqual(dns_exact(tcp,size)[-4:],socket.inet_aton('127.0.0.1'))
        self.stop()
        logs=(self.root/'state/logs/server.jsonl').read_text()
        self.assertNotIn('TEST-AUTH-DO-NOT-LOG',logs)
        self.assertNotIn('opaque-real-item-data',logs)
        self.assertEqual(list((self.root/'state/logs').glob('*.body')),[])


if __name__=='__main__':
    unittest.main()
