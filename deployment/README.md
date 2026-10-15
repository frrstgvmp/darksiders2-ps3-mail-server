# Deployment

**English** · [Русский](README.ru.md)

Target: Debian 13, Python 3.10+, systemd, public IPv4.
Dependency: `python3-cryptography`.

[Installation](../docs/INSTALL.md) covers private bundle creation, required
ports, systemd, upgrades, backups and diagnostics.

- `install.sh`: install a prepared private bundle as root.
- `export_vps_bundle.py`: assemble code, private TLS files and optional DB snapshot.
- `export_public_source.py`: export the explicit public source allowlist.
- `config.public.example.json`: public IPv4 access with mandatory PSN authentication.
- `config.example.json`: restricted IP access with PSN authentication.

Private bundles and public source archives are separate outputs. Only the
public source archive is suitable for GitHub.
