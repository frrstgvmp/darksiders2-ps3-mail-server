"""Container initialization, service startup, health checks and SQLite backups."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import ssl
import tempfile
import threading
import urllib.request
import uuid

from backup_database import backup
from ds2_server import configuration
from generate_server_certificates import generate

APP = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('DS2_CONFIG_DIR', '/config'))
DATA = Path(os.environ.get('DS2_DATA_DIR', '/data'))


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def settings():
    args = configuration(CONFIG / 'config.json')
    if args.state_dir != DATA.resolve():
        raise ValueError('Container config state_dir must be ' + str(DATA))
    return args


def initialize():
    public = ipaddress.IPv4Address(os.environ['PUBLIC_IP'])
    upstream = ipaddress.IPv4Address(os.environ.get('DNS_UPSTREAM', '1.1.1.1'))
    if public.is_unspecified or public.is_multicast or int(public) == 0xffffffff:
        raise ValueError('PUBLIC_IP must be the address reachable by players')
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = CONFIG / 'config.json'
    if config_path.exists():
        current = json.loads(config_path.read_text())
        if current['public_ip'] != str(public):
            raise ValueError('PUBLIC_IP differs from existing config/config.json; update both explicitly')
    pki = CONFIG / 'pki'
    if not pki.exists():
        temporary = CONFIG / ('.pki-' + uuid.uuid4().hex)
        try:
            generate(temporary, ['thqc-darksiders2-ps3-na.thqconnect.com'], 'ds2.gds.thqconnect.com')
            temporary.rename(pki)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if not config_path.exists():
        config = json.loads((APP / 'config.example.json').read_text())
        config.update(listen='0.0.0.0', public_ip=str(public), dns_upstream=str(upstream),
                      state_dir=str(DATA), capture_raw=False, public_mode=True,
                      verify_psn_tickets=True)
        atomic_json(config_path, config)
    args = settings()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.set_ciphers('AES256-SHA256:@SECLEVEL=0')
    context.load_cert_chain(args.cert, args.key)
    news = CONFIG / 'news.json'
    if not news.exists():
        atomic_json(news, json.loads((APP / 'assets/news.example.json').read_text()))
    print('Configuration ready. Existing keys, settings, news and mail are preserved.', flush=True)
    print('A newly generated experimental TLS chain requires a console compatibility check.', flush=True)


def health():
    args = settings()
    port = 8443 if 8443 in args.https_port else args.https_port[0]
    host = '127.0.0.1' if args.listen == '0.0.0.0' else args.listen
    context = ssl._create_unverified_context()
    context.set_ciphers('DEFAULT:@SECLEVEL=0')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=context))
    with opener.open(f'https://{host}:{port}/health', timeout=8) as response:
        if response.status != 200 or json.load(response).get('ok') is not True:
            raise ValueError('Service health check failed')


def backup_loop():
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    while not stopping.is_set():
        delay = 60
        if (DATA / 'cloud.sqlite3').is_file():
            try:
                print(backup(DATA / 'cloud.sqlite3', DATA / 'backups'), flush=True)
                delay = 86400
            except (OSError, ValueError, sqlite3.Error) as exc:
                print('Database backup failed: ' + type(exc).__name__, flush=True)
        stopping.wait(delay)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'serve', 'check', 'health', 'backup', 'backup-loop'), default='serve', nargs='?')
    command = parser.parse_args().command
    try:
        if command == 'init':
            initialize()
        elif command == 'health':
            health()
        elif command == 'backup':
            print(backup(DATA / 'cloud.sqlite3', DATA / 'backups'))
        elif command == 'backup-loop':
            backup_loop()
        else:
            settings()
            args = ['/usr/bin/python3', str(APP / 'ds2_server.py'), '--config', str(CONFIG / 'config.json')]
            if command == 'check':
                args.append('--check')
            os.execv(args[0], args)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f'Setup failed: {exc}\n')


if __name__ == '__main__':
    main()
