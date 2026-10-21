"""Verify the end-user Compose setup, DNS, authentication and persistent state."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import ssl
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def run(*command, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, check=False, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    if result.returncode:
        print(result.stdout, flush=True)
        result.check_returncode()
    return result.stdout.strip()


def main():
    with tempfile.TemporaryDirectory(prefix='ds2-compose-') as temporary:
        directory = Path(temporary)
        for name in ('Dockerfile', 'VERSION', 'compose.yaml', 'setup.sh'):
            shutil.copy2(ROOT / name, directory / name)
        if (ROOT / 'image-amd64.tar.gz').exists():
            shutil.copy2(ROOT / 'image-amd64.tar.gz', directory / 'image-amd64.tar.gz')
        env = dict(os.environ, COMPOSE_PROJECT_NAME='ds2-release-check')

        def compose(*args):
            return run('docker', 'compose', *args, cwd=directory, env=env)

        context = ssl._create_unverified_context()
        context.set_ciphers('DEFAULT:@SECLEVEL=0')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                            urllib.request.HTTPSHandler(context=context))

        def get(path):
            return opener.open('https://127.0.0.1:8443' + path, timeout=5)

        def healthy():
            for _ in range(60):
                try:
                    with get('/health') as response:
                        if response.status == 200 and json.load(response)['ok']:
                            return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(1)
            raise AssertionError('Container did not become healthy')

        try:
            print(run('./setup.sh', '127.0.0.1', cwd=directory, env=env), flush=True)
            healthy()
            uid = compose('exec', '-T', 'server', 'id', '-u')
            assert uid != '0', uid
            for language, title in (
                ('English', 'Network mail and gifts are available.'),
                ('Russian', 'Сетевая почта и подарки доступны.'),
            ):
                with get('/thqconnect/news/getNews?version=1&platform=PS3_PSN&title=Darksiders2&language=' + language) as response:
                    assert json.load(response)[1][0][:2] == ['COMMUNITY SERVER', title]
            try:
                get('/thqconnect/cloud/execute?auth=docker-auth-redaction-check')
                raise AssertionError('Unauthenticated mailbox access accepted')
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
            assert 'docker-auth-redaction-check' not in compose('logs', '--no-color', 'server')

            host = 'thqc-darksiders2-ps3-na.thqconnect.com'
            query = (struct.pack('!HHHHHH', 0x500, 0x100, 1, 0, 0, 0)
                     + b''.join(bytes([len(label)]) + label.encode() for label in host.split('.'))
                     + b'\0\0\1\0\1')
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(5)
                sock.sendto(query, ('127.0.0.1', 53))
                reply = sock.recv(4096)
                assert reply[:2] == query[:2] and reply[-4:] == socket.inet_aton('127.0.0.1')
            with socket.create_connection(('127.0.0.1', 53), timeout=5) as sock:
                sock.sendall(struct.pack('!H', len(query)) + query)
                def exact(size):
                    data = b''
                    while len(data) < size:
                        chunk = sock.recv(size - len(data))
                        if not chunk:
                            raise OSError('Short DNS TCP response')
                        data += chunk
                    return data
                reply = exact(struct.unpack('!H', exact(2))[0])
                assert reply[:2] == query[:2] and reply[-4:] == socket.inet_aton('127.0.0.1')

            config_files = [p for p in (directory / 'config').rglob('*') if p.is_file()]
            hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in config_files}
            print(compose('run', '--rm', '--no-deps', 'init'), flush=True)
            assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in hashes.items())
            database = directory / 'data/cloud.sqlite3'
            with sqlite3.connect(database) as connection:
                connection.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                                   ('/psn/docker-check', 'GameToWeb', '{"marker":"persist"}', 0, 0, '/psn/docker-check'))
            print(compose('exec', '-T', 'server', 'python3', '/app/docker_entrypoint.py', 'backup'), flush=True)
            snapshots = list((directory / 'data/backups').glob('cloud-*.sqlite3'))
            assert snapshots
            assert any(sqlite3.connect(p).execute("SELECT data FROM documents WHERE profile='/psn/docker-check'").fetchone() == ('{"marker":"persist"}',) for p in snapshots)
            old_id = compose('ps', '-q', 'server')
            compose('up', '-d', '--force-recreate', 'server', 'backup')
            healthy()
            assert compose('ps', '-q', 'server') != old_id
            with sqlite3.connect(database) as connection:
                assert connection.execute("SELECT data FROM documents WHERE profile='/psn/docker-check'").fetchone() == ('{"marker":"persist"}',)
            assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in hashes.items())
            print('PASS: non-root setup, HTTPS, localized news, auth rejection/redaction, DNS UDP/TCP, repeat init, backup and recreation persistence.', flush=True)
        except BaseException:
            print(compose('ps', '-a'), flush=True)
            for service in ('server', 'backup'):
                container = compose('ps', '-a', '-q', service)
                if container:
                    print(run('docker', 'inspect', '--format', '{{json .State}}', container, cwd=directory, env=env), flush=True)
            print(compose('logs', '--no-color', '--tail', '100'), flush=True)
            raise
        finally:
            compose('down', '--remove-orphans')


if __name__ == '__main__':
    main()
