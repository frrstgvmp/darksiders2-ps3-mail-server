#!/bin/sh
# Initialize or update a local Docker Compose deployment without replacing data.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
command -v docker >/dev/null 2>&1 || { echo 'Install Docker Engine and Docker Compose first.' >&2; exit 1; }
docker compose version >/dev/null
docker info >/dev/null
[ "$(uname -s)" = Linux ] || { echo 'This setup targets Linux Docker Engine.' >&2; exit 1; }
[ "$#" -le 1 ] || { echo 'Usage: ./setup.sh [PUBLIC_IPV4]' >&2; exit 1; }
image="darksiders2-ps3-mail-server:$(cat VERSION)"
if [ -f .env ]; then
    public_ip=$(sed -n 's/^PUBLIC_IP=//p' .env | head -n 1)
    if [ "$#" = 1 ] && [ "$1" != "$public_ip" ]; then
        echo 'Update PUBLIC_IP in .env and public_ip in config/config.json together.' >&2
        exit 1
    fi
    ds2_uid=$(sed -n 's/^DS2_UID=//p' .env | head -n 1)
    ds2_gid=$(sed -n 's/^DS2_GID=//p' .env | head -n 1)
else
    public_ip=${1:-}
    [ -n "$public_ip" ] || { echo 'Usage: ./setup.sh PUBLIC_IPV4' >&2; exit 1; }
    case "$public_ip" in ''|*[!0-9.]*) echo 'PUBLIC_IP must be an IPv4 address.' >&2; exit 1;; esac
    ds2_uid=$(id -u)
    ds2_gid=$(id -g)
    if [ "$ds2_uid" = 0 ]; then ds2_uid=10001; ds2_gid=10001; fi
    umask 077
    printf 'PUBLIC_IP=%s\nBIND_IP=%s\nDS2_UID=%s\nDS2_GID=%s\nDNS_UPSTREAM=1.1.1.1\n' \
        "$public_ip" "$public_ip" "$ds2_uid" "$ds2_gid" > .env
fi
case "$public_ip" in ''|*[!0-9.]*) echo 'PUBLIC_IP must be an IPv4 address.' >&2; exit 1;; esac
case "$ds2_uid" in ''|*[!0-9]*) echo 'Set numeric DS2_UID in .env.' >&2; exit 1;; esac
case "$ds2_gid" in ''|*[!0-9]*) echo 'Set numeric DS2_GID in .env.' >&2; exit 1;; esac
[ "$ds2_uid" != 0 ] || { echo 'DS2_UID must be nonzero.' >&2; exit 1; }
umask 077
mkdir -p config data
if [ "$(id -u)" = 0 ]; then chown "$ds2_uid:$ds2_gid" config data; fi
docker compose config --quiet
if ! docker image inspect "$image" >/dev/null 2>&1; then
    if [ -f image-amd64.tar.gz ] && [ "$(uname -m)" = x86_64 ]; then
        docker load --input image-amd64.tar.gz
    else
        docker compose build server
    fi
fi
docker compose run --rm --no-deps init
docker compose up -d server backup
printf '\nServer started. Set PS3 DNS to %s.\n' "$public_ip"
printf '%s\n' 'Status: docker compose ps' 'Logs: docker compose logs -f server'
