#!/usr/bin/env python3
"""Export an explicit source allowlist; never copy operational keys or databases."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

BASE = Path(__file__).resolve().parents[1]
FILES = (
    'VERSION', 'README.md', 'README.ru.md', 'LICENSE', 'NOTICE', 'SECURITY.md', 'CONTRIBUTING.md', '.gitignore',
    'ds2_server.py', 'cloud_api.py', 'dns_probe.py', 'lab_server.py', 'access_control.py',
    'psn_auth.py', 'service_limits.py', 'assets/psn-darksiders2-key.json',
    'generate_server_certificates.py', 'backup_database.py', 'vps_bridge.py', 'configure_vps_direct.py', 'assets/thq-connect-root.pem',
    'deployment/README.md', 'deployment/config.example.json', 'deployment/install.sh',
    'deployment/config.public.example.json',
    'deployment/export_vps_bundle.py', 'deployment/export_public_source.py',
    'deployment/darksiders2-server.service', 'deployment/darksiders2-backup.service',
    'deployment/darksiders2-backup.timer', 'tests/test_cloud_api.py', 'tests/test_service.py', 'tests/test_bridge.py', 'tests/test_direct_route.py',
    'docs/INSTALL.md', 'docs/PROTOCOL.md', 'docs/STATUS.md', 'docs/PUBLISHING.md',
    'docs/COMPATIBILITY.md', 'docs/COMPATIBILITY.ru.md',
    'docs/PLAYER-GUIDE.md', 'docs/RELEASE-v0.4.6.md', 'docs/RELEASE-v0.4.6.ru.md',
    'tests/test_public.py', 'docs/PUBLIC-SERVER.md', 'docs/PLAYER-GUIDE.ru.md',
    'docs/HOW-IT-WORKS.ru.md',
    'docs/INSTALL.ru.md', 'docs/PROTOCOL.ru.md', 'docs/PUBLIC-SERVER.ru.md',
    'docs/PUBLISHING.ru.md', 'docs/STATUS.ru.md', 'deployment/README.ru.md',
    'CONTRIBUTING.ru.md', 'SECURITY.ru.md', 'NOTICE.ru.md', 'LICENSE.ru.md',
)


def export(out):
    out = out.resolve()
    archive = out.with_name(out.name + '.tar.gz')
    manifest = out.with_name(out.name + '.manifest.json')
    if any(path.exists() for path in (out, archive, manifest)):
        raise ValueError('Output directory, archive and manifest must not already exist')
    records = []
    # Verify all input before creating any output. The only PEM is a public certificate.
    for filename in FILES:
        source = BASE / filename
        if source.is_symlink() or not source.is_file():
            raise ValueError(f'Missing regular source file: {filename}')
        data = source.read_bytes()
        private_markers = [b'-----BEGIN ' + label + b'-----' for label in
                           (b'PRIVATE KEY', b'RSA PRIVATE KEY', b'EC PRIVATE KEY', b'OPENSSH PRIVATE KEY', b'ENCRYPTED PRIVATE KEY')]
        if any(marker in data for marker in private_markers):
            raise ValueError(f'Private key found in source: {filename}')
        records.append({'path': filename, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    out.mkdir(parents=True, mode=0o755)
    try:
        for filename in FILES:
            target = out / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BASE / filename, target)
            target.chmod(0o755 if filename.endswith('.sh') else 0o644)
        with tarfile.open(archive, 'w:gz') as tar:
            for filename in FILES:
                tar.add(out / filename, arcname=out.name + '/' + filename, recursive=False)
        report = {'source_directory': out.name, 'archive': archive.name,
                  'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'files': records, 'version': (BASE / 'VERSION').read_text().strip(),
                  'ofw_verified': False,
                  'notice': 'Public source only; no deployment secrets or player database.'}
        manifest.write_text(json.dumps(report, indent=2) + '\n')
    except BaseException:
        shutil.rmtree(out)
        archive.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = export(args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Export failed: {exc}\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'files'}, indent=2))


if __name__ == '__main__':
    main()
