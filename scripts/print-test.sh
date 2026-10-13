#!/bin/sh
# Prints ONE small text page through the gateway, as a user, with a personal print key. Uses one sheet of paper.
#   scripts/print-test.sh [printer-queue] [username]        (defaults: HP7305, your login name)
# The key (portal -> "Il mio profilo" -> Crea una chiave) is asked silently or taken from $PRINT_KEY.
set -eu
GATEWAY="${GATEWAY:-print.lan:8631}"
PRINTER="${1:-HP7305}"
USER_NAME="${2:-$(id -un)}"

if [ -z "${PRINT_KEY:-}" ]; then
    printf 'Print key for %s: ' "$USER_NAME" >&2
    stty -echo; trap 'stty echo' EXIT; read -r PRINT_KEY; stty echo; trap - EXIT; echo >&2
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
export PRINT_KEY USER_NAME
enc_user="$(python3 -c 'import os,urllib.parse as u; print(u.quote(os.environ["USER_NAME"], safe=""))')"
enc_pass="$(python3 -c 'import os,urllib.parse as u; print(u.quote(os.environ["PRINT_KEY"], safe=""))')"

printf 'Prova di stampa tramite gateway\nUtente: %s\nStampante: %s\nOra: %s\n' "$USER_NAME" "$PRINTER" "$(date)" > "$tmp/prova.txt"
cat > "$tmp/job.test" <<'TEST'
{
  OPERATION Print-Job
  GROUP operation-attributes-tag
  ATTR charset attributes-charset utf-8
  ATTR language attributes-natural-language en
  ATTR uri printer-uri $uri
  ATTR name job-name "prova-stampa.txt"
  ATTR mimetype document-format text/plain
  FILE $filename
  STATUS successful-ok
}
TEST
ipptool -tv -f "$tmp/prova.txt" "ipps://$enc_user:$enc_pass@$GATEWAY/printers/$PRINTER" "$tmp/job.test" \
  | grep -E "${SHOW:-PASS|FAIL|status-code|status-message|job-id|job-state }" || true
