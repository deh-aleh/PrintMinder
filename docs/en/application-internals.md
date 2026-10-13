# How the application is built

[Documentation index](../README.md) · English · [Italiano](../it/funzionamento-applicazione.md)

A guided tour of the repository: what every source file is for, how configuration works (`.env`, `config/gateway.env`,
`CUPSPL_*`), and what the scripts and container files do. For the big picture read [architecture.md](architecture.md) first.

> **Naming.** The product is called **PrintMinder**. Some technical names predate it and are kept on purpose so that
> existing installations keep working: the Python package `app`, the variables `CUPSPL_*`, the command
> `cups-policy-admin`, the compose project `printgw`, the service `cups-policy-gateway`. They are not typos.

## 1. Repository layout

```
app/            the application (Python package)
  admin/        the web portal: routes + Jinja templates
  audit/        administrative log and audit archive
  auth/         accounts, passwords, print keys, RADIUS, login protection
  backup/       backup engine (files, encryption, scheduler)
  db/           models, sessions, migration runner
  ipp/          IPP codec, reverse proxy, URI rewriting
  locales/      translations (.po) for it, es, ru, zh
  migrations/   Alembic revisions
  policy/       quotas, grants, page counting, controls, keep-alive, ordering
  cli.py  config.py  cups_client.py  escl.py  i18n.py  main.py  mdns.py
deploy/         installation on the host without docker (systemd)
docker/         container definitions (stack/ is the production one)
docs/           this documentation (en/ and it/)
scripts/        helper scripts
tests/          automated tests
docker-compose.yml  docker-compose.test.yml  pyproject.toml  alembic.ini
```

## 2. Configuration: who reads what

There are three different files with similar names. This is the most common source of confusion.

| File | Read by | Contains | Created by |
|---|---|---|---|
| **`.env`** (project folder) | **docker compose** only, to build `docker-compose.yml` | `PUID`, `PGID`, `GATEWAY_PORT`, `CUPS_QUEUES`, `CUPS_VIRTUAL_QUEUE`, `AUDIT_ARCHIVE_HOST_PATH`, `BACKUP_HOST_PATH`, `BACKUP_DIR`, `PRINTGW_REGISTRY`, `PRINTGW_VERSION` | `scripts/docker-init.sh` |
| **`config/gateway.env`** | the **gateway** and **mdns** containers (`env_file`) | every `CUPSPL_*` setting, including secrets | `scripts/docker-init.sh` (from `docker/gateway.env.example`), mode 600 |
| **`deploy/env.example`** → `/etc/cups-policy-gateway/env` | systemd unit of the **host install** | same `CUPSPL_*` settings, for installs without docker | `deploy/install.sh` |

The application itself ([`app/config.py`](../../app/config.py)) reads **only real environment variables** with the prefix
`CUPSPL_` (it does not read a `.env` file: that one belongs to compose). Every setting has a safe default; an empty value
means "not set". After editing `config/gateway.env` run `docker compose up -d` (recreates the containers that use it).

### 2.1 `.env` (docker compose variables)

| Variable | Default | Meaning |
|---|---|---|
| `PUID`, `PGID` | your user | Unix user that runs the gateway; owns the TLS key and `data/` folders |
| `GATEWAY_PORT` | `8631` | Port published on the host (use `631` if nothing else uses it) |
| `CUPS_QUEUES` | empty | Queues created in CUPS at start: `NAME=URI NAME2=URI2` |
| `CUPS_VIRTUAL_QUEUE` | `0` | `1` creates a queue `virtual` that writes PDFs (try quotas without paper) |
| `AUDIT_ARCHIVE_HOST_PATH`, `BACKUP_HOST_PATH` | set by init | Only displayed in the portal, to tell where files are on the host |
| `BACKUP_DIR` | `./data/backups` | Host folder mounted at `/backups`: the only place backups may be written |
| `PRINTGW_REGISTRY`, `PRINTGW_VERSION` | set by init | Download published images instead of building; the version that runs (changed by `scripts/update.sh`) |
| `PROJECT_DIR` | set by init | Full path of the project folder; only the optional `updater` container uses it |
| `COMPOSE_PROFILES` | unset | `autoupdate` starts the optional `updater` container |

The file is made from `docker/env.example`. `scripts/update.sh` and `scripts/env-sync.sh` (code: `app/envsync.py`) add the options of newer versions at the end of `.env` and `config/gateway.env`, with their explanation; a value that exists is never changed, and a copy of the file is kept (`.env.bak-<date>`).

### 2.2 `config/gateway.env` (`CUPSPL_*` settings)

The commented reference is [`docker/gateway.env.example`](../../docker/gateway.env.example) (plain English comments) and the
authoritative list is `app/config.py`. Summary:

| Group | Variables |
|---|---|
| **Secret** | `CUPSPL_SECRET_KEY` — signs session cookies and authenticates gateway→mdns. Unset = random at each start (sessions lost on restart, mdns channel unprotected). Changing it only logs everybody out. |
| **RADIUS** (optional) | `RADIUS_HOST`, `RADIUS_PORT` (1812), `RADIUS_SECRET`, `RADIUS_TIMEOUT` (5), `AUTH_CACHE_SECONDS` (60). Both host and secret empty = local accounts only; only one filled = refuses to start. |
| **Print authentication** | `IPP_AUTH` (`keys` \| `keys+radius`), `KEY_TTL_DAYS_RADIUS` (90), `KEY_TTL_DAYS_LOCAL` (365), `AUTO_CREATE_USERS` (true), `DEFAULT_GROUP` (default), `CUPS_USER_PREFIX` (`gw:`), `ANONYMOUS_DISCOVERY` (true) |
| **First run** | `BOOTSTRAP_ADMIN` (true), `BOOTSTRAP_ADMIN_USERNAME` (`cups_orchestrator`) |
| **Requests** | `MAX_OPEN_REQUESTS` (3), `REQUEST_TTL_DAYS` (14) |
| **Audit** | `AUDIT_MAX_MB` (50), `AUDIT_ARCHIVE_DIR` (`/data/audit-archive`), `AUDIT_CHECK_INTERVAL` (3600) |
| **Backup** (general) | `BACKUP_ENABLED` (false), `BACKUP_DIR` (`general`), `BACKUP_HOUR` (3), `BACKUP_KEEP_DAILY/WEEKLY/MONTHLY` (7/4/12), `BACKUP_RECIPIENT` (recovery key; empty = unencrypted, no secrets in the file), `BACKUP_ROOT` (`/backups`), `BACKUP_CONFIG_DIR` (`/config`) |
| **Printers page** | `PRINTERS_REFRESH_SECONDS` (15; 0 or invalid = 15; 5–3600) |
| **USB printers** | `AUTO_DISCOVER` (true), `DISCOVERY_INTERVAL` (30), `USB_BRIDGE_HOST` (`ipp-usb`), `USB_BRIDGE_PORTS` (`60000-60099`), `USB_DIRECT` (true), `OFFLINE_REMOVE_HOURS` (8; 0 = never) |
| **Printing / scanning** | `WEB_UPLOAD_MB` (25), `WEB_MAX_COPIES` (20), `MAX_REQUEST_MB` (200), `RECONCILE_INTERVAL` (30), `SCAN_URL`, `SCAN_TIMEOUT` (180), `ESCL_ANONYMOUS` (false) |
| **Network / mDNS** | `PORTAL_URL`, `MDNS_HOSTNAME`, `MDNS_ADDRESSES`, `MDNS_PORT`, `MDNS_INTERVAL` (30), `PUBLIC_SCHEME` |
| **Misc** | `TIMEZONE` (UTC), `LANGUAGE` (en), `LOG_LEVEL` (INFO), `NOTICE_INTERVAL` (0 = by log level), `HEALTHZ_INFO` (empty = status only), `UPDATE_CHECK` (true) |
| **Set by the image/compose, do not set** | `TLS_CERTFILE`, `TLS_KEYFILE`, `DATABASE_URL`, `CUPS_URL`, `ALLOW_INSECURE_AUTH` (never in production), `HOST`, `PORT` |

## 3. The Python package, file by file

### 3.1 Entry points

| File | Role |
|---|---|
| `app/__main__.py` | The `cups-policy-gateway` command: refuses to start without TLS or with half-configured RADIUS, then runs uvicorn. |
| `app/main.py` | Builds the FastAPI app: HTTP client towards CUPS (unix socket), database, auth providers, middleware (sessions, language), routers, `/healthz`, and starts the background tasks. |
| `app/cli.py` | The `cups-policy-admin` command: `set-admin-password`, `group-limit`, `user-limit`, `set-group`, `make-admin`, `jobs`, `audit-archive`, `backup-key`, `backup-run`, `backup-verify`, `backup-restore`. |
| `app/config.py` | `Settings` (pydantic-settings): every `CUPSPL_*` variable with its default and validation. |
| `app/cups_client.py` | The gateway's own conversation with CUPS: lists queues (state, colour, media, online/offline, virtual flag) in the display order. |
| `app/mdns.py` | Separate process (`python -m app.mdns`): announces queues as `_ipps._tcp` (+ AirPrint subtype) and scanners as `_uscans._tcp`. |
| `app/escl.py` | Scanning: eSCL proxy for native clients (`/eSCL/...`) and the portal scan page (`/me/scan`); discovers scanners at run time. |
| `app/i18n.py` | Translation engine: language negotiation, `_()`, plurals, middleware. See [languages.md](languages.md). |

### 3.2 `app/ipp/` — the IPP side

| File | Role |
|---|---|
| `codec.py` | Lossless IPP (RFC 8010) parser/serializer, nested collections included. `decode_head` reads only the header so documents stream without entering memory. |
| `gateway.py` | The reverse proxy: HTTPS check, capability queries, authentication, operation filter, identity override, quota reservation, streaming to CUPS, recording the outcome. |
| `rewrite.py` | Rewrites internal CUPS URIs in responses so clients keep talking to the gateway; declares `uri-authentication-supported=basic` so Mopria sends credentials. |

### 3.3 `app/auth/` — who you are

| File | Role |
|---|---|
| `service.py` | Decides who may log in where: `portal_login` (any enabled user; the row decides local vs. delegated) and `print_login` (a print key; RADIUS password only in `keys+radius`). |
| `users.py` | Find/create users, default group, deletion (history kept). |
| `groups.py` | The two system groups `default` and `administrator`. |
| `bootstrap.py` | Creates `cups_orchestrator` without a password and prints the one-time `FIRST RUN` code. |
| `passwords.py` | argon2id hashing and the password rules (min. 12 characters, not equal to the user name). |
| `keys.py` | Print keys: creation, sha256 hash, expiry, verification, revocation. |
| `radius.py` | RADIUS provider (pyrad). `base.py`: the provider interface. `cache.py`: short cache of successful logins. |
| `throttle.py` | Login lock-out (in memory; resets on restart). |
| `dictionary` | RADIUS attribute dictionary needed by pyrad. |

### 3.4 `app/policy/` — quotas and controls

| File | Role |
|---|---|
| `engine.py` | Windows (weekly/monthly in the configured time zone, DST-safe), effective rules, usage, grants summed to limits, `check_job` → `Decision` (English `reason` for audit/IPP, `text()` localized for the portal). |
| `audit.py` | `reserve()` (atomic, under lock) and `finalize()` of a job; attaches the document to a `Create-Job` job. |
| `grants.py` | Quota/group requests, approval (idempotent), direct grants, revocation, expiry of old requests. |
| `rules.py` | Create/replace/remove limits for a user or group (shared by CLI and portal). |
| `pages.py` | Counts pages before printing (PDF, JPEG/PNG/GIF, URF, PostScript, text) and parses page ranges. |
| `reconcile.py` | Reconciler loop with CUPS (real pages, canceled jobs, orphan reservations). |
| `control.py` | Gateway maintenance mode, per-printer block and mDNS hiding, the token for the mdns channel. |
| `keepalive.py` | Periodic maintenance print: settings, scheduler, test print. |
| `testpage.py` | Builds the PDFs the gateway prints itself (no dependency). |
| `ordering.py` | List order: physical first, then virtual; each by first-seen time. |
| `discovery.py` | Finds new USB printers (ipp-usb first, CUPS usb backend + driver second), creates their queues, tracks unreachable USB queues and removes them after `OFFLINE_REMOVE_HOURS`. |

### 3.5 `app/admin/` — the portal

| File | Role (URL prefix) |
|---|---|
| `static/` | The icon: `icon.svg` (browser tab: ink tile with a light ring, readable on any tab colour), `icon-dark.svg` / `icon-light.svg` (ink tile for light backgrounds, paper tile for dark ones; the portal header picks one by theme), `favicon.ico`, `apple-touch-icon.png`, `icon-512.png`. Served without login at `/admin/static/`; `/favicon.ico` redirects there. |
| `routes.py` | Login/logout, first-run setup, audit list and CSV export, job cancel (`/admin/…`). |
| `accounts.py` | Users, groups, limits, user keys, admin-action log (`/admin/users`, `/groups`, `/actions`). |
| `requests.py` | Pending requests, approval/rejection, direct grants (`/admin/requests`, `/grants`). |
| `printers.py` | Printers overview, counters, test printers, keep-alive and test print (`/admin/printers`). |
| `controls.py` | Maintenance mode, block / hide a printer, `/mdns/policy` feed for the announcer. |
| `backups.py` | Backup targets (`/admin/backups`). |
| `audit_archive.py` | List/read/download/verify archives (`/admin/archive`). |
| `audit_view.py` | How one audit row is displayed (clipped text, device, print specs). |
| `me.py` | User area: consumption, keys, password, settings (theme, language, refresh), requests (`/me`). |
| `printing.py` | Print from the browser (`/me/print`). |
| `common.py` | Shared pieces: templates, session and CSRF dependencies, flash messages, redirects, helpers. |
| `templates/*.html` | Jinja pages: `base.html` (layout, menu, theme), `macros.html`, one template per page. |

### 3.6 Other packages

| File | Role |
|---|---|
| `app/audit/adminlog.py` | `record()`: writes an `admin_audit` row (who did what). |
| `app/audit/archive.py` | Size estimation, crash-safe archiving to `.jsonl.gz`, verification, streaming reader, the periodic archiver. |
| `app/backup/core.py` | Create/verify/prune/restore backups; SQLite snapshot; tar.gz with `MANIFEST.json`; retention. |
| `app/backup/crypto.py` | Recovery-key encryption (X25519 + HKDF + AES-256-GCM; private key wrapped by scrypt of the passphrase). |
| `app/backup/service.py` | `backup_target` bookkeeping and the 60 s scheduler. |
| `app/db/models.py` | All SQLAlchemy models. `session.py`: engine and sessions (SQLite WAL). `migrate.py`: runs Alembic from inside the app. |
| `app/notices.py`, `app/admin/notices.py` | The bell: notices for administrators with a limit on how often the same one is reported (interval by `CUPSPL_LOG_LEVEL`), table `notice`. |
| `app/updates.py`, `app/admin/updates.py` | Daily check for a newer release (note for administrators) and the portal button that hands an update to the `updater` container through files in `/data/update` (the gateway never touches Docker). |
| `app/migrations/` | `env.py` and the revisions `0001`…`0012` (schema history). |
| `app/locales/` | `messages.pot` (template) and `<lang>/messages.po` (it, es, ru, zh). |

## 4. Scripts

| Script | Purpose |
|---|---|
| `scripts/docker-init.sh [names/IPs]` | One-time setup: creates `config/gateway.env` (with a generated secret), `.env`, `data/` folders and a self-signed TLS certificate whose SAN lists the names/IPs given. |
| `scripts/backup.sh backup\|restore` | Full **host-side** backup (database, config, audit archive, CUPS queues, `.env`); used to move the machine. |
| `scripts/add-printer-linux.sh` | Adds a gateway printer to a Linux computer with the print key stored in the queue address. |
| `scripts/print-test.sh` | Sends one small text page as a user (uses a sheet of paper). |
| `scripts/gen_dev_cert.sh` | Development-only self-signed certificate. |
| `scripts/update.sh [VERSION\|--check]` | Safe update with the published images: backup, new version in `.env`, pull, restart, health wait, automatic return to the old version. `--from-portal` is the mode used by the `updater` container. |
| `scripts/i18n.py` | Translation tooling: `extract`, `missing`, `check`, `add`. |

## 5. Containers and host installation

| Path | Purpose |
|---|---|
| `docker-compose.yml` | The production-style stack (`ipp-usb`, `cups`, `gateway`, `mdns`, optional `radius`). Builds from source or pulls published images. |
| `docker-compose.test.yml` | Test environment: a real CUPS on `:6310` and FreeRADIUS on `:1812`. |
| `docker/stack/gateway/Dockerfile` | Gateway image (also used by `mdns`). |
| `docker/stack/cups/` | CUPS image: `cupsd.conf` (private backend policy), `entrypoint.sh` (creates the queues from `CUPS_QUEUES`), printer drivers (brlaser, gutenprint, splix, foo2zjs). It also sees `/dev/bus/usb` for printers ipp-usb can not serve. |
| `docker/stack/ipp-usb/` | ipp-usb image, `ipp-usb.conf`, and the entrypoint that restarts it when USB devices change. |
| `docker/cups/`, `docker/radius/` | Test CUPS image; test RADIUS users (`mario`, `anna`, `admin`). |
| `docker/stack/updater/` | Optional `updater` image (profile `autoupdate`): waits for `/data/update/request.json`, runs `scripts/update.sh --from-portal`, writes `status.json`. Has the Docker socket. |
| `docker/gateway.env.example`, `docker/env.example` | Templates of `config/gateway.env` and `.env`, with every option explained. The gateway image carries a copy in `/usr/share/printminder/` for `app/envsync.py`. |
| `deploy/install.sh`, `setup-cups.sh`, `cups-policy-gateway.service`, `cups.socket.d/`, `env.example` | Installation on the host without docker (see [installation.md](installation.md)). |

## 6. Where to look when…

| You want to… | Look at |
|---|---|
| change how a quota is computed | `app/policy/engine.py`, `app/policy/audit.py` |
| allow/forbid an IPP operation | `app/ipp/gateway.py` |
| add a portal page | a router in `app/admin/`, a template in `app/admin/templates/`, a menu entry in `base.html` |
| add a setting | `app/config.py`, then `docker/gateway.env.example` and [this page](#22-configgatewayenv-cupspl_-settings) |
| change the database | `app/db/models.py` **and** a new Alembic revision (a test checks they match) |
| translate a text | [languages.md](languages.md) |
