# Installation guide

[Documentation index](../README.md) · English · [Italiano](../it/installazione.md)

Two ways to install PrintMinder:

- **Docker (recommended)** — everything runs in containers (`ipp-usb`, CUPS, gateway, mDNS). Nothing is installed or
  changed on the host.
- **Host install (advanced)** — a systemd service plus a reconfigured system CUPS. It modifies `/etc/cups/cupsd.conf`:
  use it only if you know why.

Problems? See [troubleshooting.md](troubleshooting.md).

## 1. Requirements

| | |
|---|---|
| Server | **Linux** machine (a mini-PC or a Raspberry Pi is ideal). USB passthrough and the `host` network used by mDNS exist only on Linux; on Docker Desktop (Windows, macOS) the gateway starts but only **network** printers work and phones will not discover them. |
| Software | Docker Engine with the Compose plugin (`docker compose version`), `openssl` and `python3` (used by the init script), `git` or the source archive |
| Printer | USB (through `ipp-usb`) or on the network (IPP). Anything CUPS can drive. |
| Network | One TCP port reachable by clients (default **8631**; `631` if no other CUPS uses it). Clients must trust the certificate (see §3.4) |
| Architecture | **amd64** (PC, server) and **arm64** (Raspberry Pi 4/5, ARM NAS). The published images contain both and Docker picks the right one. 32-bit ARM (armv7) is not supported |
| One gateway per USB printer | `ipp-usb` needs exclusive use of the device: see §5 |

## 2. Quick path (Docker)

```sh
git clone <repository-url> printminder && cd printminder

# 1. names / IPs by which clients will reach the server (they go into the TLS certificate)
scripts/docker-init.sh print.lan 192.168.1.50

# 2. settings (RADIUS is optional: leave host and secret empty to use local accounts only)
$EDITOR config/gateway.env

# 3. printers: see §5 (USB) and §6 (network); then start
docker compose up -d

# 4. read the one-time code and choose the administrator password
docker compose logs gateway | grep "FIRST RUN"
#    open https://<server>:8631/admin/setup
```

The administrator account is `cups_orchestrator`. From a shell you can do the same with
`docker compose exec -it gateway cups-policy-admin set-admin-password`.

## 3. Step by step

### 3.1 Initialise

`scripts/docker-init.sh [name-or-IP ...]` writes **only inside the project folder**:

| Created | What |
|---|---|
| `config/gateway.env` | all `CUPSPL_*` settings, with a freshly generated `CUPSPL_SECRET_KEY`; mode 600 (it holds secrets) |
| `.env` | compose variables, each one explained in the file: `PRINTGW_REGISTRY`/`PRINTGW_VERSION` (which published images run), `PUID`/`PGID` (your user), `PROJECT_DIR`, `GATEWAY_PORT`, `CUPS_QUEUES`, `CUPS_VIRTUAL_QUEUE`, host paths |
| `config/tls/` | a self-signed certificate (825 days) whose alternative names are the names/IPs you passed |
| `data/audit-archive/`, `data/backups/` | host folders for compressed audit and backups |

Re-running it never overwrites existing files. Never share `config/` or `.env`: they contain secrets.

### 3.2 Configure `config/gateway.env`

Defaults are sensible; the settings you will most often touch:

| Setting | When |
|---|---|
| `CUPSPL_RADIUS_HOST`, `CUPSPL_RADIUS_SECRET` | You want office (RADIUS) logins. Register this machine as a RADIUS *client* with the same secret. Fill both or neither. |
| `CUPSPL_PORTAL_URL` | Set `https://print.lan:8631` so messages sent to print clients contain the right link |
| `CUPSPL_TIMEZONE` | Quota weeks/months and displayed times follow it (default `UTC`: set yours, for example `Europe/Rome`) |
| `CUPSPL_LANGUAGE` | Default portal language (`en`, `it`, `es`, `ru`, `zh`) |
| `CUPSPL_MDNS_HOSTNAME` | If the machine name is not in the certificate |
| `CUPSPL_BACKUP_*` | The general scheduled backup (see [backup.md](backup.md)) |
| `CUPSPL_HEALTHZ_INFO` | What `/healthz` shows besides the status (nothing by default): `version`, `printers` |
| `CUPSPL_UPDATE_CHECK` | `false` stops the daily question to GitHub about a newer version |
| `CUPSPL_ESCL_ANONYMOUS` | `true` accepts scans from apps that cannot send a password (see [scanning.md](scanning.md)) |

The file is fully commented. After any change: `docker compose up -d`.

### 3.3 Compose variables (`.env`)

Edit `.env` for the printer queues (`CUPS_QUEUES`), the published port (`GATEWAY_PORT=631` to replace port 631), the
user (`PUID`/`PGID`) and, for downloaded images, `PRINTGW_REGISTRY` + `PRINTGW_VERSION` (pin a fixed version in
production, never `latest`).

### 3.4 TLS certificate

TLS is **mandatory**: the gateway refuses to start without it.

- The generated certificate is self-signed. Install it as trusted on every client, **or**
- put your CA-signed `fullchain.pem` and `privkey.pem` in `config/tls/` (the key must be readable by the `PUID` user) and
  run `docker compose restart gateway`.

The certificate must list the names/IPs clients use, including the IP announced by mDNS.

**You already have a valid certificate (for example one issued by Nginx Proxy Manager on another machine).** The simplest way is to let the
gateway use that same certificate itself, with no proxy in between:

1. Make a name that certificate covers (say `print.example.com`) resolve to the server inside your network (local DNS record or router entry).
2. Copy the pair from the machine that holds it (NPM: `data/letsencrypt/live/npm-<n>/fullchain.pem` and `privkey.pem`; custom certificates:
   `data/custom_ssl/npm-<n>/`) to `config/tls/fullchain.pem` and `config/tls/privkey.pem`, make the key readable by the `PUID` user
   (`chmod 600`), and run `docker compose restart gateway`.
3. Set `CUPSPL_PORTAL_URL=https://print.example.com:8631` in `config/gateway.env`, and use `ipps://print.example.com:8631/printers/<queue>`.
4. Let's Encrypt certificates are renewed about every 60 days: copy the two files again after each renewal (a `scp` or `rsync` from cron) and
   restart the gateway.

Devices that find printers through mDNS are given the `<name>.local` name or the IP, which a certificate for `print.example.com` does not
cover: use the real name by hand on those devices, or stop the `mdns` service if you do not need discovery.

*Behind a reverse proxy instead* (the proxy keeps the certificate and forwards to `https://<server>:8631`; not tested by the project): the
proxy host must forward to scheme `https`, allow large bodies and not buffer them (`client_max_body_size 250m; proxy_request_buffering off;
proxy_read_timeout 600s;`), and the gateway sees every client as the proxy's address (login lock-out per address, audit IPs) unless
`FORWARDED_ALLOW_IPS=<proxy address>` is set in `config/gateway.env` so uvicorn trusts `X-Forwarded-For`. Printer addresses given back to clients
carry the `Host` the proxy forwards, without `:443`, so devices must keep the address they were set up with.

### 3.5 Start

```sh
docker compose up -d --build          # build from source
# or, with published images (set PRINTGW_REGISTRY and PRINTGW_VERSION in .env):
docker compose pull && docker compose up -d
```

Check: `curl -sk https://<server>:8631/healthz` answers 200; `docker compose ps` shows `cups` healthy.

### 3.6 First administrator

`docker compose logs gateway | grep "FIRST RUN"` prints a one-time code. Open `https://<server>:8631/admin/setup`, enter
the code and choose the password of `cups_orchestrator` (minimum 12 characters). The code is single-use and protected
against guessing. If nothing appears, the account probably already has a password (this folder ran before and the Docker volume kept the database): the log then says "already has a password"; sign in, or reset it with `docker compose exec -it gateway cups-policy-admin set-admin-password`. More causes: [troubleshooting.md](troubleshooting.md).

### 3.7 First users

In the portal (**Users**) create local users, or let RADIUS users log in (they are created in the default group on first
login). In **Groups** set limits. Each user then creates a **print key** in *Profile* and uses it as the password
when a computer or phone asks for credentials. See [user-guide.md](user-guide.md) and [admin-guide.md](admin-guide.md).

## 4. Connecting devices

| Device | How |
|---|---|
| Any phone / computer | Portal → **Print** (`/me/print`): upload PDF, JPEG, PNG, GIF or text. Nothing to install. |
| Linux | After creating a key the profile page shows a ready `lpadmin` command; or `scripts/add-printer-linux.sh <server> <queue> <user>`. |
| Android | **Mopria Print Service** discovers the printers and asks for name and key. The built-in Android print service cannot authenticate. |
| Windows, macOS, iPhone | Add a network printer `ipps://<server>:8631/printers/<queue>`; enter user name and key when asked. Not yet tested by the project. |

The device must trust the certificate. Details in [printing.md](printing.md).

## 5. USB printer

**New USB printers are added by themselves** (within about a minute): plug the printer in and it appears in the Printers page. If it has
IPP-over-USB it is served by `ipp-usb`; if not (many older lasers), the `cups` container uses it directly and needs a driver — the image
includes brlaser, gutenprint, splix and foo2zjs (add others in `docker/stack/cups/Dockerfile`). `CUPS_QUEUES` is only needed to give a
fixed name to a queue; a queue named there is created once, and stays deleted if you delete it later (or if the gateway removes an unplugged USB printer). To bring one back: `scripts/queue-restore.sh NAME --reboot`. See [printers.md](printers.md#2-new-and-unplugged-usb-printers).

`ipp-usb` needs exclusive use of the printer. If it is installed on the host, stop and mask it (SANE too):

```sh
sudo systemctl disable --now ipp-usb && sudo systemctl mask ipp-usb
```

Then in `.env`:

```
CUPS_QUEUES=HP7305=ipp://ipp-usb:60000/ipp/print
```

and `docker compose up -d`. The queue is created automatically as soon as the printer answers (retried for 5 minutes).
Further printers: `docker compose exec cups lpadmin -p NAME -E -v ipp://ipp-usb:600NN/ipp/print -m everywhere`
(each printer's port is shown by `docker compose logs ipp-usb`). Plugging or unplugging a printer restarts `ipp-usb`
by itself within seconds.

## 6. Network printer

Give `CUPS_QUEUES` the printer's IPP address: `CUPS_QUEUES="OFFICE=ipp://192.168.1.60/ipp/print"` (several queues are
separated by spaces). Scanners that answer eSCL on the printer's IPP port (or port 80) are found automatically;
otherwise list them in `CUPSPL_SCAN_URL`.

## 7. Try it without a printer or RADIUS

```sh
# .env:  CUPS_VIRTUAL_QUEUE=1        config/gateway.env:  CUPSPL_RADIUS_HOST=radius  CUPSPL_RADIUS_SECRET=testing123
docker compose --profile radius-test up -d --build
```

Creates the queue `virtual` (writes PDFs, no paper) and a test RADIUS with `mario/mario123`, `anna/anna123`,
`admin/admin123`. Example: `ipptool -t -f file.txt "ipps://mario:mario123@localhost:8631/printers/virtual" job.test`.
PDFs: `docker compose exec cups ls /var/spool/cups-pdf/ANONYMOUS`. You can also create **test printers** from the
Printers page. Never leave test accounts on a real installation.

## 8. Updating, backing up, moving

- **Update** — see "Updates" below.
- **Backups**: the portal's *Backup* menu ([backup.md](backup.md)); `scripts/backup.sh backup` for a full host-side copy
  (database, config, audit archive, CUPS queues, `.env`) to move the machine.
- **Logs**: `docker compose logs gateway`. **Health**: `GET /healthz`.

### Updates

The images are published for each release (`ghcr.io/deh-aleh/{gateway,cups,ipp-usb,updater}:<version>`, amd64 + arm64) and
`.env` holds the version that runs (`PRINTGW_VERSION`). A version is only changed **on purpose**: nothing updates by itself.
Database migrations run at start. Going back to an older version after a migration needs a restore of the backup.

| How | When |
|---|---|
| `scripts/update.sh` | **Normal way.** Makes a full backup (`data/backups/pre-update/`), writes the new version in `.env`, downloads the images, restarts, waits until the gateway is healthy and, if it is not, puts the old version back. `scripts/update.sh 1.2.0` picks a version; `--check` only tells if a newer one exists. A change of major version (1.x → 2.x) asks for confirmation: read the release notes first. |
| Button *Update* in the portal | Optional. Menu *Backup*, box *Update*. Needs the `updater` container (below) **and** a scheduled backup that is on and succeeded in the last 48 h: a fresh backup is made, then the update starts. If there is no working scheduled backup the button stays off and says why. Only updates inside the same major version. |
| `git pull && docker compose up -d --build` | Only if you build the images yourself (`PRINTGW_REGISTRY` empty in `.env`). |

**Notice of a new version.** Once a day the gateway asks GitHub for the newest release and shows a note to administrators.
Only that one request goes out and it sends nothing about your server. Switch it off with `CUPSPL_UPDATE_CHECK=false`.

**The optional `updater` container** applies updates asked for in the portal. It is **off by default** because it needs the
Docker socket (`/var/run/docker.sock`), and whoever controls that socket controls the whole machine (root). It only reads a version
number `x.y.z` written by the gateway; images always come from the registry in your `.env`. Turn it on with:

```sh
echo "COMPOSE_PROFILES=autoupdate" >> .env      # one line in .env (or add --profile autoupdate every time)
docker compose up -d
```

If you do not want that risk, keep it off and use `scripts/update.sh`.

**New options in your files.** When a version brings new settings, `scripts/update.sh` adds them at the end of `.env` and
`config/gateway.env`, each with its explanation and its default value, so the behaviour stays the same until you change them. Values
you set are never touched; a copy is kept next to the file (`.env.bak-<date>`). `scripts/env-sync.sh --check` lists what would be added,
`scripts/env-sync.sh` adds it: run it after a `git pull` (it reads the templates of this folder; `update.sh` reads those of the new image). It needs `python3` or, without it, an up-to-date gateway image.
The folder itself (`docker-compose.yml`, scripts) is changed by `git pull`, not by `update.sh`: the release notes say when that is needed.

**Pin the version.** Never use `latest`: leave `PRINTGW_VERSION` at a number, so an update is a decision.

## 9. Alternative: install on the host (no docker)

> This **modifies the system**: it creates the user `cupspl`, files in `/opt` and `/etc`, a systemd unit, and replaces
> `/etc/cups/cupsd.conf` (the original is saved as `cupsd.conf.pre-gateway`).

```sh
sudo sh deploy/install.sh                 # user, venv in /opt/cups-policy-gateway, /etc/cups-policy-gateway/env, unit file
sudoedit /etc/cups-policy-gateway/env     # RADIUS (optional), TLS paths, …; put the certificate in /etc/cups-policy-gateway/tls
sudo sh deploy/setup-cups.sh              # makes CUPS a private backend (unix socket, no TCP); --revert goes back
sudo systemctl enable --now cups-policy-gateway
journalctl -u cups-policy-gateway | grep "FIRST RUN"
```

Needs Python ≥ 3.12 with `venv`. The service runs as `cupspl`, sandboxed, and binds port 631 through
`CAP_NET_BIND_SERVICE`. `deploy/env.example` lists the settings. The mDNS announcer is a separate process
(`python -m app.mdns`) that you must run yourself if you want it.

## 10. Development

```sh
pip install -e '.[dev]'
docker compose -f docker-compose.test.yml up -d --build   # test CUPS on :6310 and FreeRADIUS on :1812
pytest                                                    # tests needing docker skip themselves if it is off
```
