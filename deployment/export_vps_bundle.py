#!/usr/bin/env python3
"""Prepare a private deployment directory with known-working TLS material and a consistent DB snapshot."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import sqlite3
import ssl

BASE = Path(__file__).resolve().parents[1]
FILES = ['ds2_server.py', 'cloud_api.py', 'dns_probe.py', 'lab_server.py', 'access_control.py',
         'generate_server_certificates.py', 'backup_database.py', 'psn_auth.py', 'service_limits.py', 'news_api.py',
         'assets/news.example.json',
         'assets/thq-connect-root.pem', 'assets/psn-darksiders2-key.json',
         'deployment/install.sh', 'deployment/darksiders2-server.service',
         'deployment/darksiders2-backup.service', 'deployment/darksiders2-backup.timer']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--public-ip', required=True)
    parser.add_argument('--bind-ip', help='Local VPS interface IPv4; defaults to public-ip. Set separately for provider NAT.')
    parser.add_argument('--client', action='append', default=[], help='Private-mode tester public IPv4 address/CIDR; repeat')
    parser.add_argument('--public', action='store_true', help='Public DNS/game mode with mandatory signed PSN tickets')
    parser.add_argument('--cert', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--database', type=Path)
    args = parser.parse_args()
    public = str(ipaddress.IPv4Address(args.public_ip))
    if not args.public and not args.client:
        parser.error('Private mode requires --client; use --public for authenticated public access')
    networks = [ipaddress.ip_network(value, strict=False) for value in args.client]
    if any(n.version != 4 or n.prefixlen < 24 for n in networks):
        parser.error('Use explicit tester IPv4 addresses; /32 preferred')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.set_ciphers('AES256-SHA256:@SECLEVEL=0')
    context.load_cert_chain(args.cert, args.key)
    os.umask(0o077)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for filename in FILES:
        target = out / filename
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(BASE / filename, target)
        target.chmod(0o600)
    (out / 'deployment/install.sh').chmod(0o700)
    (out / 'pki').mkdir(mode=0o700)
    shutil.copyfile(args.cert, out / 'pki/cloud-fullchain.pem')
    shutil.copyfile(args.key, out / 'pki/cloud.key')
    for path in (out / 'pki').iterdir():
        path.chmod(0o600)
    config = json.loads((BASE / 'deployment/config.example.json').read_text())
    config['public_ip'] = public
    config['listen'] = str(ipaddress.IPv4Address(args.bind_ip or public))
    config['allowed_clients'] = [str(n) for n in networks]
    config['public_mode'] = args.public
    (out / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    database_copied = False
    if args.database:
        uri = args.database.resolve().as_uri() + '?mode=ro'
        (out / 'state').mkdir(mode=0o700)
        with sqlite3.connect(uri, uri=True) as source, sqlite3.connect(out / 'state/cloud.sqlite3') as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database snapshot integrity check failed')
        (out / 'state/cloud.sqlite3').chmod(0o600)
        database_copied = True
    report = {'private_bundle': str(out), 'public_ip': public, 'allowed_clients': config['allowed_clients'],
              'cloud_chain_sha256': hashlib.sha256(args.cert.read_bytes()).hexdigest(),
              'database_snapshot_included': database_copied,
              'notice': 'Contains private TLS key and possibly game data; not the public source archive.'}
    (out / 'bundle.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
