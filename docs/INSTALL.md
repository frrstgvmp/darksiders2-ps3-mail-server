# Installation

## Docker Compose

Use Linux Docker Engine with Docker Compose. A public IPv4 address and open
UDP/TCP 53 and TCP 443/8443 are required. Docker Desktop is not the deployment
target. Check port conflicts with `ss -lntup`.

Download the `docker-amd64.tar.gz` bundle from [Releases](https://github.com/frrstgvmp/darksiders2-ps3-mail-server/releases).
It includes a Linux AMD64 image and the source needed to build locally.

```bash
mkdir -p ds2-server
tar -xzf darksiders2-ps3-mail-server-0.5.0-docker-amd64.tar.gz -C ds2-server --strip-components=1
cd ds2-server
./setup.sh 203.0.113.10
```

Replace `203.0.113.10` with the server's public IPv4. Setup loads the bundled
image, or builds from source if no suitable bundled image is available. It
creates `.env`, initializes persistent files and starts the server and daily
backup worker. Docker must be accessible to the current user; run the entire
setup as root if needed. Containers run with a nonzero UID.

The generated TLS chain is experimental. Verify it with an original console
client before advertising a new server. Existing keys are preserved on repeat
setup and updates; no operational keys are distributed.

For provider NAT, edit `BIND_IP` in `.env` to an address assigned to the local
interface before starting. `PUBLIC_IP` remains the address players can reach.
If creating `.env` manually from `.env.example`, set the IP and numeric UID/GID
first. An occupied bind address/port must be resolved before startup.

## Commands

```bash
docker compose ps
docker compose logs -f server
docker compose exec -T server python3 /app/docker_entrypoint.py check
docker compose exec -T server python3 /app/docker_entrypoint.py backup
docker compose stop
docker compose up -d
```

The backup worker creates a consistent SQLite snapshot on startup once the
database is available, then every 24 hours. It keeps the latest 14 snapshots.
`docker compose down` removes containers/network; persistent bind directories
remain. News edits are read automatically; the game may require a restart.

| Host path | Contents |
| --- | --- |
| `.env` | Published bind IP and container UID/GID |
| `config/config.json` | Runtime settings |
| `config/pki` | TLS chain and private key |
| `config/news.json` | Community news |
| `data/cloud.sqlite3` | Mail and profile ownership |
| `data/logs` | Rotating metadata logs |
| `data/backups` | Consistent SQLite snapshots |

Configuration is read-only in the server container. Edit it on the host.
The application filesystem is read-only; only persistent data and temporary
storage are writable. Published Docker ports must also be accounted for in
host firewall policy; do not rely solely on UFW input rules.

## Updates and backups

Before updating:

```bash
docker compose exec -T server python3 /app/docker_entrypoint.py backup
umask 077
tar -czf ../ds2-private-backup.tar.gz .env config data/backups
```

Download the next release, extract it into the same deployment directory with
`--strip-components=1`, then run `./setup.sh`. The new version replaces the
application image and recreates containers, preserving `.env`, `config/` and
`data/`. Keep the previous release bundle for rollback. Database format changes
may require restoring a compatible snapshot rather than only an older image.

To restore mail, stop both containers, retain a current snapshot, replace
`data/cloud.sqlite3` with the selected snapshot, ensure ownership matches
`DS2_UID:DS2_GID` from `.env`, then start the containers. Do not overwrite an
active SQLite database. Keep configuration and TLS keys with the backups.

## Migrate from systemd

Use the existing certificate chain and database instead of generating replacements.
Stop `darksiders2-server` and `darksiders2-backup.timer` before the final database
snapshot and container startup; they use the same ports.

1. Copy `/etc/darksiders2-server/` into the deployment's `config/` directory.
2. Use `backup_database.py` to snapshot the original database; place the snapshot at `data/cloud.sqlite3`.
3. In `config/config.json`, set `listen` to `0.0.0.0`, `state_dir` to `/data`, `cloud_cert` to `pki/cloud-fullchain.pem`, `cloud_key` to `pki/cloud.key` and `news_file` to `news.json`. Adjust any other absolute paths to container paths.
4. Set the directory/file ownership to the UID/GID in `.env`, then run `./setup.sh PUBLIC_IPV4`.
5. Check inbox access, news and gift delivery before disabling the old service permanently.

## Native systemd

Debian 13, Python 3.10+ and `python3-cryptography` are required.
Prepare from the source directory with the server's public IPv4:

```bash
sudo apt-get install python3 python3-cryptography
python3 generate_server_certificates.py --out _private/pki
python3 deployment/export_vps_bundle.py \
  --out _private/server --public-ip 203.0.113.10 --public \
  --cert _private/pki/cloud-fullchain.pem --key _private/pki/cloud.key
sudo sh _private/server/deployment/install.sh
```

Run installation on the VPS; transfer the prepared private directory first if
preparing elsewhere. For provider NAT add `--bind-ip INTERFACE_IPV4`. For
restricted access replace `--public` with repeated `--client IPV4/32` arguments.
To migrate mail add `--database /path/to/cloud.sqlite3`. Private bundles contain
keys and must not be published.

Native paths: code `/opt/darksiders2-server`, settings/news/keys
`/etc/darksiders2-server`, state/logs/backups `/var/lib/darksiders2-server`.
The installer enables systemd startup and a daily backup timer. Reinstallation
replaces code/TLS files, preserves the database/news and writes proposed settings
to `config.json.new`. Reuse working TLS material when updating.

```bash
systemctl status darksiders2-server --no-pager
journalctl -u darksiders2-server -n 50 --no-pager
sudo systemctl start darksiders2-backup.service
```

## Troubleshooting

| Result | Check |
| --- | --- |
| Setup cannot access Docker | Docker Engine status and current user's Docker permissions |
| Permission denied in config/data | UID/GID and file ownership; preserve existing `.env` |
| Port already allocated | Bind IP, existing DNS/HTTPS services or old systemd deployment |
| No DNS request | Console/router DNS, routing, firewall, restricted-mode allowlist |
| Correct DNS, no TCP | Port 8443, gateway, VPN route |
| TLS alert 46 | Certificate chain and client compatibility |
| HTTP 403 | PSN session, ticket signature/service/expiry, server clock |
| HTTP 503 | Unsupported operation, permissions, quota or malformed request |
| Letter has no Take All action | Check that the sender attached an item |
| Deleted mail returns after restart | Save the game after changing local mail |

Health checks establish service/database availability, not console TLS or
PSN authentication. The legacy `ofw_verified:false` health field is fixed.

On Windows, check from the console's network:

```powershell
nslookup -type=A thqc-darksiders2-ps3-na.thqconnect.com
nslookup -type=A thqc-darksiders2-ps3-na.thqconnect.com 193.232.178.202
Test-NetConnection 193.232.178.202 -Port 8443
```

Replace the IP for another deployment. The game hostname must resolve to the
server. A PC and console may use different router/VPN policies.
