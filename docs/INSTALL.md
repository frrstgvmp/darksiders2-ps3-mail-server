# Installation

Debian 13, Python 3.10+, systemd and a public IPv4 address are required.
Open UDP/TCP 53 and TCP 443/8443 in the host and provider firewalls.
Check port conflicts with `ss -lntup`.

## Prepare

Run from the source directory. Replace `203.0.113.10` with the server's public IPv4.

```bash
sudo apt-get install python3 python3-cryptography
python3 generate_server_certificates.py --out _private/pki
python3 deployment/export_vps_bundle.py \
  --out _private/server \
  --public-ip 203.0.113.10 \
  --public \
  --cert _private/pki/cloud-fullchain.pem \
  --key _private/pki/cloud.key
```

The generated chain is experimental, not publicly trusted. Verify a new chain
with an original console client before advertising the server.
Use existing certificate/key paths when migrating a working deployment.

For provider NAT, add `--bind-ip INTERFACE_IPV4`. For restricted access, replace
`--public` with `--client PLAYER_PUBLIC_IP/32`; repeat for additional clients.
Add `--database /path/to/cloud.sqlite3` to include a consistent database snapshot.
The prepared directory contains private keys and must not be published.

## Install

If preparing directly on the VPS:

```bash
sudo sh _private/server/deployment/install.sh
```

If preparing elsewhere, transfer the private directory first:

```bash
scp -r _private/server root@203.0.113.10:/root/ds2-server
ssh root@203.0.113.10
sh /root/ds2-server/deployment/install.sh
```

The installer creates the service account, installs the server and enables
systemd startup and daily database backups. It does not change firewall rules.

## Paths

| Path | Contents |
| --- | --- |
| `/opt/darksiders2-server` | Application and public verification material |
| `/etc/darksiders2-server/config.json` | Configuration |
| `/etc/darksiders2-server/pki` | TLS chain and private key |
| `/etc/darksiders2-server/news.json` | Community news |
| `/var/lib/darksiders2-server/cloud.sqlite3` | Mail and profile ownership |
| `/var/lib/darksiders2-server/logs` | Rotating metadata logs |
| `/var/lib/darksiders2-server/backups` | Latest 14 database snapshots |

## Check

```bash
sudo python3 /opt/darksiders2-server/ds2_server.py --config /etc/darksiders2-server/config.json --check
systemctl status darksiders2-server --no-pager
journalctl -u darksiders2-server -n 50 --no-pager
systemctl list-timers darksiders2-backup.timer
```

`GET https://SERVER_IP:8443/health` checks service/database availability, not
console TLS compatibility. Its legacy `ofw_verified:false` field is fixed.
Verify signed inbox access and gift delivery through the game.

## Update and restore

Back up the database, configuration, news and TLS keys. Prepare the new source
with the existing TLS material, then rerun the installer. It replaces code and
TLS files, preserves the existing database/news, and writes proposed settings
to `config.json.new`. Review new configuration fields before enabling them.

Trigger a database backup with:

```bash
sudo systemctl start darksiders2-backup.service
```

To restore, stop the service, retain a current snapshot, replace the database
with the selected backup, set owner `ds2-server:ds2-server` and mode `0600`,
then start the service. Never overwrite an active SQLite database.

## Troubleshooting

| Result | Check |
| --- | --- |
| No DNS request | Console/router DNS, routing, firewall, restricted-mode allowlist |
| Correct DNS, no TCP | Port 8443, gateway, VPN route |
| TLS alert 46 | Certificate chain and client compatibility |
| HTTP 403 | PSN session, ticket signature/service/expiry, server clock |
| HTTP 503 | Unsupported operation, permissions, quota or malformed request |
| Letter has no Take All action | Check that the sender attached an item |
| Deleted mail returns after restart | Save the game after changing local mail |

On Windows, run from the same network as the console:

```powershell
nslookup -type=A thqc-darksiders2-ps3-na.thqconnect.com
nslookup -type=A thqc-darksiders2-ps3-na.thqconnect.com 193.232.178.202
nslookup -type=A example.com 193.232.178.202
Test-NetConnection 193.232.178.202 -Port 8443
```

Replace the IP for another deployment. The game hostname must resolve to the
server; unrelated domains must retain their ordinary answers. TCP success does
not establish TLS or PSN authentication. PC and console routing may differ.
