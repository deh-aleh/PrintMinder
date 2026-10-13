#!/bin/sh
# Add the options that a newer version brought to your .env and config/gateway.env, with their explanations.
# Values you set are never changed: new options are appended at the end, with their default value. A copy of each
# changed file is kept next to it (.env.bak-<date>).
#   scripts/env-sync.sh            add the missing options
#   scripts/env-sync.sh --check    only list them, change nothing
#
# Where the list of new options comes from:
#   * in a git clone (the normal case) from the templates of THIS folder: run it after "git pull";
#   * otherwise from the templates inside the gateway image.
# scripts/update.sh runs it for you, from the new image, before the restart.
set -eu
cd "$(dirname "$0")/.."

# the usual case: the folder has the code and python3 (docker-init.sh needs python3 too)
if [ -f app/envsync.py ] && [ -f docker/env.example ] && command -v python3 >/dev/null 2>&1; then
    exec python3 -m app.envsync --root . "$@"
fi

# no python3 here: do it inside the gateway image
if ! docker compose run --rm --no-deps -T -v "$(pwd):/project" gateway \
        python -m app.envsync --root /project --project-dir "$(pwd)" "$@"; then
    echo "" >&2
    echo "The gateway image on this machine may be older than this folder (it does not contain app/envsync.py)." >&2
    echo "Rebuild it with:  docker compose build gateway    (or download the new one with scripts/update.sh), then run this again." >&2
    exit 1
fi
