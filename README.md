<picture>
  <source media="(prefers-color-scheme: dark)" srcset="app/admin/static/icon-light.svg">
  <img src="app/admin/static/icon-dark.svg" alt="PrintMinder icon" width="96" align="right">
</picture>

# PrintMinder

**English** · [Italiano](README.it.md)

Authentication, quotas and an audit trail in front of CUPS (IPP), with a web portal. CUPS and ipp-usb stay unmodified
dependencies. The gateway is the only entry point: it authenticates users (local accounts and/or RADIUS), **imposes** their
identity, enforces print limits, records who printed and scanned what, and forwards the job to CUPS.

```
IPP client ──ipps (TLS + Basic)──▶ gateway ──unix socket──▶ CUPS ──internal net──▶ ipp-usb ──USB──▶ printer
browser ───────https───────────▶     │  └─▶ DB (SQLite): users, groups, rules, audit
                                     └────▶ RADIUS (optional)           portal on /admin (admins) and /me (users)
```

> Internal names such as `CUPSPL_*`, `cups-policy-admin` and the compose project `printgw` predate the name PrintMinder and are
> kept so existing installations keep working.

## What it does

- **Accounts**: local (argon2id) and/or RADIUS; personal, revocable **print keys** so a domain password is never stored on a PC or phone.
- **Quotas**: jobs and pages per week or month, per group with per-user overrides; users ask for more, administrators approve.
- **Printing**: IPP/IPPS for computers, **print from the browser** for any phone, LAN announcement (AirPrint/Mopria).
- **Scanning**: eSCL through the gateway and from the portal, together with printing on the same USB device.
- **Audit**: who printed/scanned what (real pages), a separate log of administrative actions, kept forever with verified compressed archives.
- **Printers**: status, ink and counters, block/hide, test printers, periodic maintenance print and test print for physical printers.
- **Backups**: scheduled per administrator, encrypted with a recovery key, restorable from the command line.
- **Portal in 5 languages**: English, Italian, Spanish, Russian, Simplified Chinese; chosen per user.

## Features and status

✅ done and tested · 🟡 partial · ⬜ planned

| Area | Feature | Status |
|---|---|---|
| **Identity** | Local accounts (argon2id); RADIUS login (optional); first administrator through a one-time code | ✅ |
| | Other providers (LDAP/AD, OIDC); two-factor authentication for administrators | ⬜ |
| **Printing** | IPP/IPPS proxy in front of CUPS; no bypass (CUPS is not reachable); personal print keys | ✅ |
| | Any printer CUPS supports (USB through ipp-usb, or network) | 🟡 tested with two printers over USB: an HP Smart Tank 7300 (through ipp-usb) and a Brother DCP-7055 (CUPS usb backend, brlaser driver: found, queue created and first print worked without any setting) |
| | LAN announcement (DNS-SD) and printing from the browser | ✅ seen by Android with Mopria; iPhone not tested |
| | New USB printers get their queue by themselves (ipp-usb first, CUPS usb backend + driver otherwise); unreachable USB queues are removed after a countdown, any dead queue can be deleted by hand | ✅ |
| | Held printing with later release (pull printing) | ⬜ |
| **Policy** | Users and groups; job and page limits per week/month; per-user overrides | ✅ |
| | Exceptions: user requests, administrator approval, temporary or permanent grants; group change on request | ✅ |
| | Pages counted before printing for PDF, images, text and PostScript | ✅ soft limit for other files |
| | Limits per feature (colour, duplex, paper size) or per printer; allowed hours | ⬜ |
| **Scanning** | eSCL through the gateway (same keys, audit, together with printing) and scanning from the portal | ✅ |
| | Native eSCL clients that can authenticate (field test) | ⬜ |
| **Audit** | Print/scan audit with real pages; separate log of administrative actions | ✅ |
| | Unlimited retention with verified compressed archives; CSV export, filters, archive viewer and download | ✅ |
| | syslog/SIEM export; anonymisation | ⬜ |
| **Portal** | Admin portal (audit, users, groups, requests, grants, actions, printers, backups, archive) and user area (consumption, keys, requests, print, scan) | ✅ |
| | Settings: password, theme, language, refresh; phone-friendly layout; copy buttons | ✅ |
| | Printers page: status, ink, lifetime counters (HP), firmware, scanner; block, hide, test printers; gateway maintenance mode | ✅ |
| | Periodic maintenance print and test print with statistics (physical printers); ordering physical first, movable with up/down arrows (own order per administrator); queues can be renamed; IPP-USB / USB badges | ✅ |
| | Portal in English, Italian, Spanish, Russian, Chinese | ✅ Spanish/Russian/Chinese need native review |
| | Notifications (email/webhook) for pending requests; usage reports | ⬜ |
| | Permission requests (colour, duplex, scanning…) as these features appear | ⬜ |
| **Operations** | Docker stack (ipp-usb + CUPS + gateway + mDNS), nothing installed on the host | ✅ |
| | Scheduled backups per administrator (folder, hour, rotation, passphrase/recovery-key encryption), restore from CLI | ✅ |
| | Database migrations (Alembic), health check, logs, admin CLI | ✅ |
| | Images for amd64 and arm64 on ghcr.io; update script with backup and automatic return to the old version; notice of new versions; new options added to your `.env` and `gateway.env` without changing your values | 🟡 not yet run on a real ARM machine |
| | Update button in the portal (optional `updater` container, needs the Docker socket) | 🟡 only tested with simulations |
| | Backups on a network disk or USB disk: marker file against an unmounted disk, time limit for a disk that stops answering | ✅ tested with an SMB share |
| | Bell with notices for administrators; `/healthz` shows only the status unless you ask for more | ✅ |
| | High availability, Prometheus metrics, direct remote backup targets (SSH/S3) | ⬜ |

## Limits

The full list, with workarounds, is in [docs/en/limitations.md](docs/en/limitations.md). The ones to know before you start:

- **The pages limit is soft** for files whose pages cannot be counted (unknown format, encrypted PDF, over 64 MB): the job that
  crosses the limit *is printed* and its real pages then block the following ones. With `Create-Job` + `Send-Document` the count
  arrives after the job was accepted. A `Create-Job` without a document frees its quota only when CUPS cancels it (default 3 h).
- **Linux host required** for USB printers and mDNS announcement (Docker Desktop on Windows/macOS: network printers only, no discovery).
- **Android's system print service cannot authenticate**: use Mopria Print Service or print from the browser. iPhone, Windows and macOS are untested.
- **One gateway per USB printer** and **one per SQLite database** (no high availability). Images are built for the building machine's
  architecture; going back to an older version after a migration needs a backup.
- **TLS is mandatory**: install the self-signed certificate on clients or use your CA's.
- Printer disconnection is detected within ~30 s (network queues: a TCP check, not paper).
- The database is **not encrypted** and holds printed file names: protect it as personal data.
- Spanish, Russian and Chinese translations are not reviewed by native speakers; pages printed by the gateway stay English.

## Install (Docker, recommended)

Requirements: a **Linux** server, Docker Engine with Compose, `openssl`, `python3`, a USB or network printer, and a TCP port
reachable by clients (default 8631). Nothing is installed on the host.

```sh
git clone <repository-url> printminder && cd printminder

# 1. names / IPs clients will use to reach the server (they go into the TLS certificate)
scripts/docker-init.sh print.lan 192.168.1.50      # creates config/gateway.env, .env, config/tls/, data/

# 2. settings: RADIUS is optional (leave host and secret empty for local accounts only)
$EDITOR config/gateway.env

# 3. printers, in .env — USB (stop the host's ipp-usb first: sudo systemctl disable --now ipp-usb && sudo systemctl mask ipp-usb)
#       CUPS_QUEUES=HP7305=ipp://ipp-usb:60000/ipp/print
#    or a network printer:
#       CUPS_QUEUES="OFFICE=ipp://192.168.1.60/ipp/print"

# 4. start
docker compose up -d

# 5. read the one-time code and set the password of the administrator "cups_orchestrator"
docker compose logs gateway | grep "FIRST RUN"
#    then open https://<server>:8631/admin/setup
```

Then: create users and groups in the portal (`https://<server>:8631/admin`); every user creates a **print key** in *Profile*
and uses it as the password when a computer or phone asks for credentials (printer address `ipps://<server>:8631/printers/<queue>`);
phones with nothing installed can use *Print* in the portal. Check the install with `curl -sk https://<server>:8631/healthz`.
To use a CA-signed certificate put `fullchain.pem` and `privkey.pem` in `config/tls/` and `docker compose restart gateway`.
Update with `scripts/update.sh` (backup first, automatic return if the new version does not start; images for amd64 and arm64).
Try it with no printer or RADIUS: see the guide. The alternative host install (systemd, modifies `/etc/cups`) is also in the guide.

Full guide: [docs/en/installation.md](docs/en/installation.md).

## Documentation

| Topic | Document |
|---|---|
| **Installation** (docker and host, USB/network printers, TLS, updates) | [installation.md](docs/en/installation.md) |
| **Troubleshooting** | [troubleshooting.md](docs/en/troubleshooting.md) |
| Architecture and technologies | [architecture.md](docs/en/architecture.md) |
| How the application is built (each source file, `.env`, `gateway.env`, scripts) | [application-internals.md](docs/en/application-internals.md) |
| User guide · Administrator guide (incl. CLI) | [user-guide.md](docs/en/user-guide.md) · [admin-guide.md](docs/en/admin-guide.md) |
| Accounts, groups, print keys | [accounts.md](docs/en/accounts.md) |
| Quotas, requests, grants | [quotas.md](docs/en/quotas.md) |
| Printing and connecting devices | [printing.md](docs/en/printing.md) |
| Printers: overview, controls, maintenance print | [printers.md](docs/en/printers.md) |
| Scanning | [scanning.md](docs/en/scanning.md) |
| Audit and archive | [audit.md](docs/en/audit.md) |
| Backup and restore | [backup.md](docs/en/backup.md) |
| Languages and translating | [languages.md](docs/en/languages.md) |
| Known limitations | [limitations.md](docs/en/limitations.md) |

Everything is also available in Italian: [docs/it](docs/it) · [docs/README.md](docs/README.md).

## License

PrintMinder is released under the [Apache License 2.0](LICENSE). You may use, modify and distribute it, commercially included, as long as you keep
the copyright notice and the [NOTICE](NOTICE) file (credit to Alessio Paccino) and state the changes you make. Copyright 2026 Alessio Paccino.
