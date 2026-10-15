# Installation

Requirements: Debian 13, Python 3.10+, `python3-cryptography`, systemd, public
IPv4. Ports: UDP/TCP 53, TCP 443/8443. Optional additional DNS: UDP/TCP 1053.

## Prepare

From the release source directory on the preparation machine:

```bash
sudo apt-get install python3-cryptography
python3 generate_server_certificates.py --out _private/pki
python3 deployment/export_vps_bundle.py \
  --out _private/vps-ready \
  --public-ip 203.0.113.10 \
  --public \
  --cert _private/pki/cloud-fullchain.pem \
  --key _private/pki/cloud.key
```

Replace the example IPv4. The generator produces private keys and an
experimental chain, not a publicly trusted certificate. Newly generated
material requires an OFW client check. The reported OFW result used the
operator's deployed chain; operational private keys are not distributed.

For provider NAT, add `--bind-ip INTERFACE_IPV4`. For restricted access,
replace `--public` with repeated `--client PLAYER_PUBLIC_IP/32`.
To migrate existing mail add `--database /path/to/cloud.sqlite3`; the exporter
uses SQLite backup. The bundle contains private data and must not be published.

## Install on VPS

```bash
scp -r _private/vps-ready root@203.0.113.10:/root/ds2-private
ssh root@203.0.113.10
cd /root/ds2-private
sh deployment/install.sh
```

The installer creates `ds2-server`, installs code/config/TLS files and enables
the service and backup timer. Existing config/database are retained; proposed
config is written to `config.json.new`. Code and TLS files are replaced during
reinstall. Back up the current deployment before upgrading.

Open the required ports in host/provider firewalls. The installer does not
modify firewall policy. Check port conflicts with `ss -lntup`.

## Configuration and paths

[Public config](../deployment/config.public.example.json) ·
[Restricted config](../deployment/config.example.json)

`public_mode:true` requires signed tickets and ignores the IP allowlist.
Restricted mode requires `allowed_clients`; retain `verify_psn_tickets:true`.
Use `capture_raw:false`. Public mode rejects raw capture.
Certificate paths are relative to the config file. GDS API is unsupported.

| Path | Contents |
| --- | --- |
| `/opt/darksiders2-server` | Code and public verification material |
| `/etc/darksiders2-server/config.json` | Runtime configuration |
| `/etc/darksiders2-server/pki` | TLS chain and private key |
| `/var/lib/darksiders2-server/cloud.sqlite3` | Mail and account/profile associations |
| `/var/lib/darksiders2-server/logs` | Rotating metadata logs |
| `/var/lib/darksiders2-server/backups` | SQLite snapshots, latest 14 retained |

## Verify

```bash
python3 /opt/darksiders2-server/ds2_server.py --config /etc/darksiders2-server/config.json --check
systemctl status darksiders2-server --no-pager
journalctl -u darksiders2-server -n 50 --no-pager
curl --insecure https://203.0.113.10:8443/health
systemctl list-timers darksiders2-backup.timer
```

Health confirms service availability; `--insecure` does not verify game TLS
acceptance. The fixed `ofw_verified:false` field is not a compatibility check.
Verify actual mailbox access with the [player procedure](PLAYER-GUIDE.md).
Both players must use the same server. Preserve any working PSN VPN route.
No game executable replacement or console CA installation is part of setup.

## Diagnostics

| Result | Check |
| --- | --- |
| No DNS event | Console DNS, firewall, routing; allowlist in restricted mode |
| DNS succeeds, no TCP | TCP 8443, gateway, VPN and hostname handling |
| TLS alert 46 | Certificate rejected; record chain and exact OFW/game version |
| HTTP 403 | Ticket format/signature, expiry, service, PSN session and server clock |
| HTTP 503 | Unsupported operation/document, denied access, quota or malformed batch |

Do not disable public authentication for diagnostics. GDS, news and THQ/SSO
errors are separate from mailbox API errors.

For an existing PC VPN gateway, `vps_bridge.py` can relay TLS unchanged.
`configure_vps_direct.py --mode plan` describes a narrow route for the existing
`ps3-vpn.service` setup; it is not a general VPN installer. Inspect its plan
before applying it. Standard connections need neither helper.

## Backup and restore

```bash
systemctl start darksiders2-backup.service
journalctl -u darksiders2-backup.service -n 20 --no-pager
```

For restore, stop the service, retain a consistent current snapshot, install
the selected database with owner `ds2-server:ds2-server` and mode `0600`, then
start the service. Do not overwrite an active SQLite database.
To stop hosting, restore normal console DNS and run:

```bash
systemctl disable --now darksiders2-server darksiders2-backup.timer
```

Logs redact sensitive parameters but retain source IPs and endpoint names.
SQLite/backups contain player data. File logs rotate at 5 MiB, four files total;
systemd journal retention is separate. [Access limits](PUBLIC-SERVER.md).
