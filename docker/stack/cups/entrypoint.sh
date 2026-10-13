#!/bin/sh
# CUPS as a private backend: unix socket only (config mounted from deploy/cupsd.conf).
# Queues are created from CUPS_QUEUES="NAME=URI NAME2=URI2" (idempotent, retried until the printer answers)
# and CUPS_VIRTUAL_QUEUE=1 adds a "virtual" queue that writes PDFs: handy to try quotas without paper.
set -u
cupsd

for i in $(seq 1 40); do lpstat -r >/dev/null 2>&1 && break; sleep 0.5; done

if [ "${CUPS_VIRTUAL_QUEUE:-0}" = "1" ] && ! lpstat -p virtual >/dev/null 2>&1; then
    lpadmin -p virtual -E -v cups-pdf:/ -m lsb/usr/cups-pdf/CUPS-PDF_noopt.ppd \
        || lpadmin -p virtual -E -v cups-pdf:/ -m /usr/share/ppd/cups-pdf/CUPS-PDF_noopt.ppd
fi

add_queue() {
    name="$1"; uri="$2"
    lpstat -p "$name" >/dev/null 2>&1 && return 0
    for i in $(seq 1 60); do   # the printer may take a while (USB enumeration, ipp-usb start)
        if lpadmin -p "$name" -E -v "$uri" -m everywhere 2>/dev/null; then
            echo "[entrypoint] queue $name -> $uri created"; return 0
        fi
        sleep 5
    done
    echo "[entrypoint] WARNING: could not create queue $name ($uri); add it later: docker compose exec cups lpadmin -p $name -E -v $uri -m everywhere" >&2
}
for q in ${CUPS_QUEUES:-}; do add_queue "${q%%=*}" "${q#*=}" & done

tail -F /var/log/cups/error_log &
wait $!
