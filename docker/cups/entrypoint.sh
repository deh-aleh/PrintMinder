#!/bin/sh
set -e
cupsd
for i in $(seq 1 20); do lpstat -r >/dev/null 2>&1 && break; sleep 0.5; done
# virtual queue: PDF written to /var/spool/cups-pdf/ANONYMOUS (cups-pdf default)
lpadmin -p virtual -E -v cups-pdf:/ -m lsb/usr/cups-pdf/CUPS-PDF_noopt.ppd 2>/dev/null \
 || lpadmin -p virtual -E -v cups-pdf:/ -m /usr/share/ppd/cups-pdf/CUPS-PDF_noopt.ppd
lpoptions -d virtual
exec tail -F /var/log/cups/error_log
