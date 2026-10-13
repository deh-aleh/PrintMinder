#!/bin/sh
# Update PrintMinder to a newer published version, safely.
#   scripts/update.sh              update to the newest release
#   scripts/update.sh 1.2.0        update (or go back) to this exact version
#   scripts/update.sh --check      only say if a newer version exists
#   (--from-portal VERSION is used by the "updater" container: the portal already made the backup, there are no questions,
#    and the updater container itself is left alone while it works)
#
# What it does, in order:
#   1. saves a full backup (data/backups/pre-update/) - if this fails, nothing is changed
#   2. writes the new version in .env (PRINTGW_VERSION)
#   3. downloads the new images, adds the new options of that version to .env and config/gateway.env
#      (scripts/env-sync.sh: appended at the end with their explanation, your values never change), restarts the containers
#   4. waits until the gateway says it is healthy
#   5. if it is NOT healthy: puts the old version back and tells you what to do
# Needs: .env with PRINTGW_REGISTRY and PRINTGW_VERSION set (scripts/docker-init.sh does this), docker compose, curl, python3.
# Environment: PRINTGW_RELEASES_API  (default: GitHub releases of this project) - where the newest version is looked up.
set -eu
cd "$(dirname "$0")/.."

API="${PRINTGW_RELEASES_API:-https://api.github.com/repos/deh-aleh/PrintMinder/releases/latest}"
mode="update"; target=""; portal=0
if [ "${1:-}" = "--from-portal" ]; then portal=1; shift; fi
case "${1:-}" in
    --check) mode="check" ;;
    "")      ;;
    -*)      echo "usage: $0 [--check | VERSION]" >&2; exit 2 ;;
    *)       target="${1#v}" ;;
esac

# only plain numbers like 1.2.3 are accepted: the value ends up in .env and in image names
valid() { printf '%s' "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; }
envget() { sed -n "s/^$1=//p" .env 2>/dev/null | head -1; }

[ -e .env ] || { echo ".env not found: run scripts/docker-init.sh first" >&2; exit 1; }
current="$(envget PRINTGW_VERSION)"
registry="$(envget PRINTGW_REGISTRY)"
valid "${current:-x}" || { echo "PRINTGW_VERSION in .env is not a version number like 1.2.3 (found: '${current}')." >&2; exit 1; }

if [ -z "$target" ]; then
    target="$(curl -fsS --max-time 15 "$API" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')" \
        || { echo "could not look up the newest version (no network?). Give one: $0 1.2.0" >&2; exit 1; }
fi
valid "$target" || { echo "'$target' is not a version number like 1.2.3" >&2; exit 1; }

echo "installed: $current    wanted: $target"
if [ "$mode" = "check" ]; then
    [ "$current" = "$target" ] && echo "up to date" || echo "update available: run scripts/update.sh"
    exit 0
fi
[ "$current" != "$target" ] || { echo "already on $target"; exit 0; }
[ -n "$registry" ] || { echo "PRINTGW_REGISTRY is empty in .env: images are built from this folder. Update with: git pull && docker compose up -d --build" >&2; exit 1; }

# a jump to another major version can change things by hand: ask first
if [ "$portal" = 0 ] && [ "${current%%.*}" != "${target%%.*}" ]; then
    echo "WARNING: major version change ($current -> $target). Read the release notes first."
    printf "type YES to continue: "; read -r a; [ "$a" = "YES" ] || { echo "cancelled"; exit 1; }
fi

backup_file=""
if [ "$portal" = 0 ]; then
    echo "1/4 backup ..."
    scripts/backup.sh backup data/backups/pre-update || { echo "backup failed: nothing was changed" >&2; exit 1; }
    backup_file="$(ls -t data/backups/pre-update/printgw-*.tar.gz | head -1)"
else
    # the updater container must not recreate itself: an empty COMPOSE_PROFILES hides the "autoupdate" profile from here on
    export COMPOSE_PROFILES=
fi

setver() { # replace or add PRINTGW_VERSION in .env
    if grep -q '^PRINTGW_VERSION=' .env; then sed -i "s/^PRINTGW_VERSION=.*/PRINTGW_VERSION=$1/" .env
    else echo "PRINTGW_VERSION=$1" >> .env; fi
}
healthy() { # wait up to ~2 minutes
    i=0
    while [ $i -lt 24 ]; do
        s="$(docker compose ps --format '{{.Health}}' gateway 2>/dev/null | head -1)"
        [ "$s" = "healthy" ] && return 0
        i=$((i+1)); sleep 5
    done
    return 1
}

echo "2/4 downloading $target ..."
setver "$target"
if ! docker compose pull; then
    setver "$current"; echo "download failed: kept version $current" >&2; exit 1
fi
echo "    adding the new options of this version to .env and config/gateway.env (your values are kept) ..."
docker compose run --rm --no-deps -T -v "$(pwd):/project" gateway python -m app.envsync --root /project --project-dir "$(pwd)" \
    || echo "note: the new options could not be added; run scripts/env-sync.sh later (the update goes on, defaults apply)" >&2
echo "3/4 restarting ..."
docker compose up -d
echo "4/4 waiting for the gateway ..."
if healthy; then
    echo "OK: now on $target.${backup_file:+ Backup taken before: $backup_file}"
    exit 0
fi

echo "NOT healthy after the update: going back to $current" >&2
setver "$current"
docker compose up -d
cat >&2 <<MSG
The old version is running again. If the new version already changed the database, the old one may still fail.
In that case restore the backup taken just before:
    scripts/backup.sh restore ${backup_file:-<file>}   (from the portal: use the newest copy in the menu Backup)
Look at the cause with:  docker compose logs --tail 50 gateway
MSG
exit 1
