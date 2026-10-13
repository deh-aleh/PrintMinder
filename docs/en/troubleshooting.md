# Troubleshooting

[Documentation index](../README.md) · English · [Italiano](../it/risoluzione-problemi.md)

First, collect facts:

```sh
docker compose ps                                  # are all services up? is cups "healthy"?
docker compose logs --tail=100 gateway             # the application log
docker compose logs --tail=100 cups ipp-usb mdns
curl -sk https://<server>:8631/healthz             # 200 = gateway and database ok, 503 = not
```

Increase detail with `CUPSPL_LOG_LEVEL=DEBUG` in `config/gateway.env`, then `docker compose up -d`.

## 1. The gateway does not start

| Symptom | Cause and fix |
|---|---|
| `refusing to start without TLS` | There is no certificate. Run `scripts/docker-init.sh` or put `fullchain.pem` + `privkey.pem` in `config/tls/`. |
| `refusing to start: set both CUPSPL_RADIUS_HOST and CUPSPL_RADIUS_SECRET, or neither` | RADIUS is half configured. Fill both or empty both. |
| Permission denied on `config/tls/privkey.pem` | The key must be readable by the user `PUID:PGID` of `.env` (`chown`/`chmod 600`). |
| `Bind for 0.0.0.0:631 failed` | Another CUPS uses 631. Keep `GATEWAY_PORT=8631`, or stop the other service. |
| "archive folder not usable" | `data/audit-archive` must be writable by the container user (same uid as `PUID`). |
| Everybody is logged out at each restart | `CUPSPL_SECRET_KEY` is empty, so a random one is generated at every start. Set it (`scripts/docker-init.sh` does). |

## 2. Cannot sign in

| Symptom | Cause and fix |
|---|---|
| `docker compose logs gateway \| grep 'FIRST RUN'` prints nothing | Check in this order. **1.** `docker compose ps`: `gateway` must be *Up*; if it restarts or exits, read `docker compose logs gateway \| tail -40`. **2.** The line is only printed while the administrator has no password. If this folder ran before, the database (the Docker volume `printgw_gateway-data`) still has the account with its old password: the log then says *"administrator … already has a password"*; sign in at `https://<server>:8631/admin/login`, or set a new password with `docker compose exec -it gateway cups-policy-admin set-admin-password`. **3.** `CUPSPL_BOOTSTRAP_ADMIN=false` in `config/gateway.env` switches the first-run account off. For a truly empty start (this **deletes all users, quotas and audit**): `docker compose down -v`, then `docker compose up -d`. |
| Locked after wrong passwords | 5 *different* wrong passwords in 5 minutes block the (user, IP) pair. Wait 5 minutes or restart the gateway (the lock is in memory). |
| A RADIUS user cannot log in | RADIUS unreachable ⇒ access denied (fail closed). Check `CUPSPL_RADIUS_*`, that this machine is a RADIUS *client* with the same secret, and the log. A local account of the same name is **never** opened by RADIUS. |
| Forced to change the password | Normal for temporary passwords created or reset by an administrator. |
| A user was disabled but still prints | Local users are blocked at once. For RADIUS users, print keys stop at expiry (`CUPSPL_KEY_TTL_DAYS_RADIUS`) — revoke their keys in the portal for an immediate stop. |

## 3. Printing

| Symptom | Cause and fix |
|---|---|
| The client asks for the password again and again | The **domain password does not work for printing**: use a print key from *Profile* (`CUPSPL_IPP_AUTH=keys`). Or the pair (user, IP) is locked out. |
| `Forbidden` / HTML 426 from CUPS | CUPS policy is not the gateway's: use `docker/stack/cups/cupsd.conf` (`DefaultAuthType None`). |
| 502 from the gateway | CUPS is stopped or `CUPSPL_CUPS_URL` is wrong. `docker compose logs cups`. |
| Job rejected with a quota message | The user reached a limit; the message includes the portal link to ask for more. See [quotas.md](quotas.md). |
| "printer is blocked" / "gateway is in maintenance" | An administrator blocked the printer or switched maintenance mode on ([printers.md](printers.md)). Administrators can still print during maintenance. |
| Job stays `accepted` forever | The reconciler cannot reach CUPS: look for `reconcile:` in the log. |
| The printer is shown NOT REACHABLE and is missing from the print form | The device does not answer (off, unplugged, USB asleep). Detection can lag up to ~30 s. For network queues it is a TCP check: it does not know about empty paper. |
| `:60000` does not answer | `ipp-usb` is not running or the printer is not seen: `docker compose logs ipp-usb`; replug the USB cable; make sure the **host's** `ipp-usb`/SANE are stopped and masked. |
| A new USB printer does not appear | Wait up to a minute or press **Look now** in Printers. Check `docker compose logs gateway \| grep discovery`. If the page says "CUPS has no driver for it", the model has no driver in the `cups` image (add one to `docker/stack/cups/Dockerfile`). Make sure the **host's** `ipp-usb`/SANE are stopped and that `CUPSPL_AUTO_DISCOVER` is not `false`. |
| An unplugged printer is still listed | It shows NOT REACHABLE with a countdown (USB queues, `CUPSPL_OFFLINE_REMOVE_HOURS`, default 8 h) and a **Delete queue** button. Network queues are never removed by themselves. |
| A queue I deleted does not come back, although it is in `CUPS_QUEUES` | By design: each queue of `CUPS_QUEUES` (and `virtual`) is created once. To create it again: `scripts/queue-restore.sh NAME --reboot` (takes the name out of the list of created queues and restarts the `cups` container; without `--reboot` it only forgets the name, and the queue returns at the next start). `scripts/queue-restore.sh --list` shows the remembered names. The queue must still be in `CUPS_QUEUES` (or be `virtual` with `CUPS_VIRTUAL_QUEUE=1`). |
| The queue was not created | `CUPS_QUEUES` is wrong, or the printer answered late. The entrypoint retries for 5 minutes; otherwise `docker compose exec cups lpadmin -p NAME -E -v URI -m everywhere`. |
| A "Create-Job" without a document keeps quota | Quota is freed only when CUPS cancels it (default after 3 h). |
| Page limit exceeded by one file | The limit is *soft* for files whose pages cannot be counted (unknown format, encrypted PDF, over 64 MB): see [limitations.md](limitations.md). |
| Browser print: "unsupported file" | Only PDF, JPEG, PNG, GIF and plain text are accepted, checked by content and not by the file name. |
| Browser print: "larger than N MB" | `CUPSPL_WEB_UPLOAD_MB` (default 25). |

## 4. Phones and computers

| Symptom | Cause and fix |
|---|---|
| Certificate warning, or the device refuses to connect | The device does not trust the certificate. Install the CA, or use a CA-signed certificate in `config/tls/`. The name or IP used must be in the certificate. |
| The printers do not appear on the phone | `mdns` must run with host networking on the same LAN; `docker compose logs mdns`. Set `CUPSPL_MDNS_ADDRESSES` if the machine has several network cards, and `CUPSPL_MDNS_HOSTNAME` to a name that is in the certificate. Docker Desktop cannot do this. A printer that is blocked-hidden or unreachable, or maintenance mode, also removes the announcement. |
| Android: the system print service sees the printer but fails | It cannot authenticate. Install **Mopria Print Service**, or print from the portal. |
| Linux desktop shows the printers but nothing prints | Announced printers have no key until you add the queue with the key in its address (profile page or `scripts/add-printer-linux.sh`). |
| Windows / macOS / iPhone | Not tested by the project. Try `ipps://<server>:8631/printers/<queue>`, user name + print key, and report what happens. |

## 5. Scanning

| Symptom | Cause and fix |
|---|---|
| No scanner in the portal | Scanners are found when they answer eSCL on the queue's IPP port or on port 80. Otherwise add `CUPSPL_SCAN_URL=name=http://host:port`. A disconnected scanner disappears in ~30 s. |
| "scanner busy" | Another scan is in progress, or the previous eSCL job was not deleted by its client. The gateway retries 3 times when the device is waking. |
| Blank page from the feeder | The feeder was asleep and declared empty, so *Automatic* used the glass. Pick *Feeder* explicitly, or re-insert the sheets. |
| NAPS2 gets 401 without a prompt | It cannot send credentials. Set `CUPSPL_ESCL_ANONYMOUS=true` (trusted networks only) and enter IP and port by hand. |
| The scan result is gone | Results stay 15 minutes in memory, only for their owner. |

## 6. Backups and audit

| Symptom | Cause and fix |
|---|---|
| Backup shows red | It failed or the last one is older than 48 h. Open the page for the reason; usually the folder is not writable or the disk is full. |
| "Folder name not valid…", "Folder is outside the backup root", "Folder … is not writable by the gateway" | A backup folder must be a sub-folder of `/backups` (host `data/backups`) and writable by the `PUID` user. A USB disk or a network share must be mounted on the host *inside* that folder **before** the gateway starts (restart the gateway after mounting). |
| Lost the passphrase | Encrypted backups cannot be opened without it (no reset exists). Make a new recovery key (`backup-key`) for future backups. |
| Restore | Stop `gateway` and `mdns`, then `docker compose run --rm -it --no-deps gateway cups-policy-admin backup-restore /backups/<folder>/<file>`, then `docker compose up -d`. Check a file first with `backup-verify`. |
| The database is large | Audit is never deleted; it is archived to `data/audit-archive` when it passes `CUPSPL_AUDIT_MAX_MB`. Lower the value to archive sooner. |

## 7. Portal language

| Symptom | Cause and fix |
|---|---|
| Pages are in English although you expected Italian | Order is: user setting → browser language → `CUPSPL_LANGUAGE` → English. Set `CUPSPL_LANGUAGE=it` or choose the language in *Settings*. |
| Some text is not translated | Texts from the printer (ink names, firmware, device warnings) or CUPS are shown as received. Audit reasons are stored in English on purpose. |
| Chinese characters look like boxes | The *browser's computer* has no CJK font installed. |
| Printed test or maintenance pages are English | By design: Russian and Chinese would need an embedded PDF font ([languages.md](languages.md)). |

## 7b. Updates

| Symptom | Cause and fix |
|---|---|
| `scripts/env-sync.sh` prints `No module named app.envsync` | The script then ran inside a gateway image that was built before this folder got the new code (the image does not contain `app/envsync.py`). Recent scripts use the folder's own Python when `python3` exists; if you still see this, run `docker compose build gateway` (or `scripts/update.sh` for published images) and try again. |
| After `git pull` the new options are not in `.env` or `gateway.env` | A pull changes the folder, not your two files. Run `scripts/env-sync.sh` (`--check` first to see what would be added). |
| `scripts/update.sh` says `PRINTGW_REGISTRY is empty` | The images are built from this folder: update with `git pull && docker compose up -d --build`, then `scripts/env-sync.sh`. |

## 8. Still stuck

Gather `docker compose logs gateway`, `docker compose ps`, the output of `/healthz`, the gateway version
(`PRINTGW_VERSION` or the commit), and what the page showed, before asking for help. Never paste `config/gateway.env`,
`.env` or the TLS key.
