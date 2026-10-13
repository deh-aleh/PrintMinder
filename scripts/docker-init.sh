#!/bin/sh
# One-time setup for the docker stack. Writes only inside this project directory:
#   config/gateway.env   settings of the program + a generated session secret (edit RADIUS_HOST / RADIUS_SECRET)
#   config/tls/          self-signed certificate (skipped if you put your own fullchain.pem/privkey.pem there)
#   .env                 compose variables (version, host user id, published port, printer queues)
# Both come from templates with every option explained; scripts/env-sync.sh adds the options of later versions to them.
# usage: scripts/docker-init.sh [NAME-OR-IP ...]   names/IPs clients will use to reach this server
set -eu
cd "$(dirname "$0")/.."
mkdir -p config/tls data/audit-archive data/backups

# .env and config/gateway.env are made from the templates docker/env.example and docker/gateway.env.example
# (a secret is generated for the session key; existing files are never touched here)
python3 -m app.envsync --init --root . --project-dir "$(pwd)"
echo "set CUPSPL_RADIUS_HOST and CUPSPL_RADIUS_SECRET in config/gateway.env if you use RADIUS (optional)"

if [ ! -e config/tls/privkey.pem ]; then
    san="DNS:localhost,IP:127.0.0.1"
    for n in "$@"; do
        case "$n" in
            *[!0-9.]*) san="$san,DNS:$n" ;;
            *)         san="$san,IP:$n" ;;
        esac
    done
    cn="${1:-localhost}"
    openssl req -x509 -newkey rsa:3072 -nodes -days 825 \
        -keyout config/tls/privkey.pem -out config/tls/fullchain.pem \
        -subj "/CN=$cn" -addext "subjectAltName=$san" 2>/dev/null
    chmod 600 config/tls/privkey.pem
    echo "created self-signed certificate for: $san"
    echo "(replace config/tls/fullchain.pem + privkey.pem with your CA-signed pair when you have it)"
fi
echo "next: edit config/gateway.env (RADIUS is optional), then: docker compose up -d"
echo "then read the one-time code:  docker compose logs gateway | grep 'FIRST RUN'   and open https://<server>:8631/admin/setup"
