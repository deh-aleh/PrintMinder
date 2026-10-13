# Known limitations

[Documentation index](../README.md) · English · [Italiano](../it/limiti.md)

What PrintMinder does **not** do (yet) or does with caveats. The short version is in the
[README](../../README.md#limits).

## 1. Installation

- A **Linux host** is required for USB printers and for mDNS (USB passthrough and the `host` network do not exist on Docker
  Desktop for Windows/macOS: there only network printers work and nothing is announced).
- One gateway per USB printer (`ipp-usb` needs exclusive use). Its container can see every USB device of the host (needed for hot-plug).
- One gateway per SQLite database; no high availability.
- Published images exist for amd64 and arm64 only (no 32-bit ARM).
- `scripts/update.sh` updates the images and adds new options to `.env` and `config/gateway.env`; changes to `docker-compose.yml` and the scripts arrive with `git pull`.
- The *Update* button of the portal needs the optional `updater` container, which holds the Docker socket (root on the host): it is off by default. It only updates inside the same major version.
- Backups on a network share: permissions are decided by the mount (use encryption), and an unmounted share is detected only if the "write only if mounted" option is ticked.
- Going back to an older version after a database migration requires restoring a backup.
- Migrations are tested on SQLite only; PostgreSQL needs verification (enum types shared between tables).
- The database is not encrypted and holds printed file names: protect it as personal data.
- Certificates: devices must trust the company CA; the announcement uses the IP, so the certificate must list it.

## 2. Quota

- The **pages limit is soft** for files whose pages can not be counted: unknown formats, encrypted PDFs, files over 64 MB. The
  job that crosses the limit is printed; its real pages then block the following ones.
- With `Create-Job` + `Send-Document` the count arrives after the job was accepted.
- A `Create-Job` with no document frees its quota only when CUPS cancels it (default 3 h).
- Page counting applies only when a pages limit exists and the document is readable.
- If RADIUS tells `Mario` from `mario`, for the gateway they are one person (same quota).
- Limits per feature (colour, duplex, paper size, per printer) do not exist yet.

## 3. Clients

- **Android's system print service can not authenticate**: use Mopria Print Service, or print from the browser.
- Android keeps credentials per printer and per session; the gateway can only revoke the key.
- iPhone/iPad, Windows and macOS have **not been tested**; whether the file name arrives in `job-name` from them is not verified.
- Print keys of Linux/CUPS clients end up saved on the client (revocable and useless elsewhere).
- Announced printers appear on Linux desktops (Avahi) without a key; they do nothing until the queue is added with the key.

## 4. Printers and scanners

- Automatic USB discovery: a printer served by `ipp-usb` is never taken through CUPS' usb backend. Printers without IPP-over-USB need a driver present in the `cups` image (brlaser, gutenprint, splix, foo2zjs are included). Whether CUPS' usb backend and `ipp-usb` coexist on the same USB bus with several printers has been tested with one device at a time only.
- USB queues unreachable for 8 h (configurable) are removed by themselves; network queues never are.

- Disconnected-device detection lags by up to ~30 s; for network queues it is a TCP probe (no paper information).
- Scanners are found automatically only if they answer eSCL on the queue's IPP port or on port 80; otherwise `CUPSPL_SCAN_URL`.
- Lifetime counters come from HP's web service only; other brands show IPP data.
- A scan delivered to the client counts as completed even if the user does not save the file.
- A sleeping feeder may be declared empty: in *Automatic* the glass is used (blank page).
- Native eSCL clients that authenticate have not been tried (sane-airscan, Image Capture).
- Pages printed by the gateway (test, maintenance) are always in English; Russian/Chinese need an embedded font.
- If the gateway is off, a missed maintenance interval is not made up: the page prints as soon as it restarts.

- Printing from the browser, *Landscape*: PDFs with portrait pages are turned and shrunk (the text is not re-flowed as a word processor would do); plain text files cannot be turned; photos are turned by CUPS. Details in [printing.md](printing.md).
- A queue of `CUPS_QUEUES` is created once: if you delete it, it stays deleted (`scripts/queue-restore.sh NAME --reboot` brings it back).

## 5. Backup and security

- Built-in backups: SQLite only; CUPS queues not included (they are in `scripts/backup.sh`); configuration files are restored by hand;
  no direct remote destinations; the passphrase can not be recovered. `scripts/backup.sh restore` is tested by hand only.
- The login lock-out is in memory and resets at restart.
- The audit and the database are not encrypted.

## 6. Languages

- Spanish, Russian and Chinese were written without native review.
- Dates and numbers are not localised.
- The audit's stored text and the server logs stay English.

## 7. Feature status

The status of every feature is in the [README](../../README.md#features-and-status).
