#!/bin/sh
# Install the prepared private VPS bundle on Debian/Ubuntu with systemd.
set -eu
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'Run as root or with sudo.' >&2
    exit 1
fi
ds2_source=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test -f "$ds2_source/config.json"
test -f "$ds2_source/pki/cloud-fullchain.pem"
test -f "$ds2_source/pki/cloud.key"
command -v apt-get >/dev/null
command -v systemctl >/dev/null
apt-get update
apt-get install --no-install-recommends -y python3 python3-cryptography
if ! id ds2-server >/dev/null 2>&1; then
    useradd --system --home /var/lib/darksiders2-server --shell /usr/sbin/nologin ds2-server
fi
install -d -m 0755 /opt/darksiders2-server /opt/darksiders2-server/assets
install -d -m 0750 -o root -g ds2-server /etc/darksiders2-server /etc/darksiders2-server/pki
install -d -m 0700 -o ds2-server -g ds2-server /var/lib/darksiders2-server
for ds2_file in ds2_server.py cloud_api.py dns_probe.py lab_server.py access_control.py generate_server_certificates.py backup_database.py psn_auth.py service_limits.py; do
    install -m 0644 "$ds2_source/$ds2_file" "/opt/darksiders2-server/$ds2_file"
done
install -m 0644 "$ds2_source/assets/thq-connect-root.pem" /opt/darksiders2-server/assets/thq-connect-root.pem
install -m 0644 "$ds2_source/assets/psn-darksiders2-key.json" /opt/darksiders2-server/assets/psn-darksiders2-key.json
for ds2_file in cloud-fullchain.pem cloud.key; do
    install -m 0640 -o root -g ds2-server "$ds2_source/pki/$ds2_file" "/etc/darksiders2-server/pki/$ds2_file"
done
if [ -e /etc/darksiders2-server/config.json ]; then
    install -m 0640 -o root -g ds2-server "$ds2_source/config.json" /etc/darksiders2-server/config.json.new
    printf '%s\n' 'Existing config kept; prepared config saved as config.json.new.'
else
    install -m 0640 -o root -g ds2-server "$ds2_source/config.json" /etc/darksiders2-server/config.json
fi
if [ -f "$ds2_source/state/cloud.sqlite3" ] && [ ! -e /var/lib/darksiders2-server/cloud.sqlite3 ]; then
    install -m 0600 -o ds2-server -g ds2-server "$ds2_source/state/cloud.sqlite3" /var/lib/darksiders2-server/cloud.sqlite3
fi
/usr/bin/python3 /opt/darksiders2-server/ds2_server.py --config /etc/darksiders2-server/config.json --check
install -m 0644 "$ds2_source/deployment/darksiders2-server.service" /etc/systemd/system/darksiders2-server.service
install -m 0644 "$ds2_source/deployment/darksiders2-backup.service" /etc/systemd/system/darksiders2-backup.service
install -m 0644 "$ds2_source/deployment/darksiders2-backup.timer" /etc/systemd/system/darksiders2-backup.timer
systemctl daemon-reload
systemctl enable darksiders2-server.service
systemctl restart darksiders2-server.service
systemctl enable --now darksiders2-backup.timer
systemctl --no-pager --full status darksiders2-server.service
