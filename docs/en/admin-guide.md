# Administrator guide

[Documentation index](../README.md) · English · [Italiano](../it/guida-amministratore.md)

For people who run the installation. The portal is at `https://<server>:8631/admin`. The top menu:

| Menu | Page | What you do there |
|---|---|---|
| **Audit** | `/admin/jobs` | Who printed or scanned what; filters, CSV, cancel queued jobs → [audit.md](audit.md) |
| **Users** | `/admin/users` | Create local or RADIUS users, edit, reset password, revoke keys, delete |
| **Groups** | `/admin/groups` | Create, rename, limits, "requestable", delete |
| **Requests** | `/admin/requests` | Approve, edit or reject quota and group requests (badge = pending) → [quotas.md](quotas.md) |
| **Grants** | `/admin/grants` | Give or revoke extra quota directly |
| **Actions** | `/admin/actions` | Who did what in the portal |
| **Printers** | `/admin/printers` | State, ink, counters; block, hide, rename, move up/down (your own order), test printers, maintenance print, test print → [printers.md](printers.md) |
| **Backup** | `/admin/backups` | Your scheduled backups → [backup.md](backup.md) |
| **Archive** | `/admin/archive` | Compressed old audit, readable and downloadable |
| **Print / Scan / Profile** | `/me…` | The same pages users have → [user-guide.md](user-guide.md) |
| **Logo, name and (user)** | `/me/settings` | The block at the top left opens the settings: theme, language, refresh |
| **Bell** (administrators only) | `/admin/notices` | Things the gateway noticed (badge = open ones), see "Notices" below |
| **Maintenance** (red wrench) | — | Stops print and scan for everyone but administrators |
| **Door with arrow** | — | Log out |

## 1. First steps

1. Set the `cups_orchestrator` password with the one-time code ([installation.md](installation.md#36-first-administrator)).
2. Create your **own** administrator account (Users → create → administrator) and use it day to day; keep `cups_orchestrator` for emergencies.
3. Edit the **default** group limits (Groups) and create groups for the people who need different limits.
4. Create users, or let RADIUS users log in. Tell people to create a print key ([user-guide.md](user-guide.md)).
5. Set up a backup ([backup.md](backup.md)).

## 2. Users

The list is read-only: a user's own limit or the inherited one (italics), active grants as a coloured `+N`, consumption and active keys.
**Edit** opens the page with every field, including the **source** (local ↔ RADIUS), and **Delete** (type the name to confirm).

- Create **local**: a temporary password is shown once; the user changes it at first login.
- Create **RADIUS**: choose the group; the person signs in with their office password.
- **Reset password** (local): new temporary password, shown once.
- **Keys**: the list per user is at `/admin/users/<id>/keys`. For each key you can **switch it off** (its expiry keeps running; switch it on again later), **extend it** (the new expiry counts from today, the time left is not added) or **revoke it**; "Revoke all" stops every device of the user. The user gets a notice for each action (not for their own). Revoked and expired keys disappear after `CUPSPL_KEY_HISTORY_DAYS` days (14).
- **Admin flag**: promotion moves the user to the `administrator` group, demotion to `default`.
- Protected: you can not disable, demote or delete yourself, the emergency account or the last administrator.

Deleting keeps the history ([accounts.md](accounts.md#7-deleting-a-user)).

## 3. Groups and limits

A group has limits (jobs / pages, weekly / monthly) and a **requestable** flag. System groups `default` and `administrator` can not be
deleted; deleting another group moves its users to `default`. Personal limits are set in the user's edit page. Details in [quotas.md](quotas.md).

## 4. Requests and grants

Review requests (edit the amount or the kind before approving, add a note). Approval is idempotent. In **Grants** you see active
grants and revoke them; you can create one directly with a reason. Everything is logged.

## 5. Printers

Block a printer (nobody prints, administrators included), hide it from mDNS, create test printers, set up the periodic maintenance
print, send a test print with statistics, switch on **gateway maintenance** (red wrench button). See [printers.md](printers.md).

## 6. Audit and archive

Use filters and the CSV export; cancel queued jobs; read archived files; verify their integrity. Nothing can be deleted
([audit.md](audit.md)).

## 7. Command line (`cups-policy-admin`)

Inside the container: `docker compose exec gateway cups-policy-admin <command>` (add `-it` when it asks for a password).

| Command | Purpose |
|---|---|
| `set-admin-password [user]` | create or update a **local** administrator (default `cups_orchestrator`) and set its password |
| `make-admin <user>` | grant admin rights (creates the user if needed) |
| `set-group <user> <group>` | move a user to a group (creates the group) |
| `group-limit <group> <limit\|none> [--period weekly\|monthly] [--metric jobs\|pages]` | set a group limit; `none` removes it |
| `user-limit <user> <limit\|none> [--period …] [--metric …]` | set a personal limit |
| `jobs [-n N]` | show the latest audit rows (and warn about archives) |
| `audit-archive [--force]` | archive old audit rows now |
| `backup-key` | create a backup recovery key from a passphrase |
| `backup-run [--id N]` | run the enabled backups now |
| `backup-verify <file>` | check a backup file |
| `backup-restore <file>` | restore database and audit files (stop the gateway first) |

## 7b. Notices (the bell)

The bell in the top bar (administrators only) lists what the gateway noticed and nobody asked about. Each notice shows the
last time, the source, and how many times it happened; *Dismiss* closes it (the dismissal is recorded in *Actions*).
The kinds of notice:

| Notice | What it says | Closes by itself when |
|---|---|---|
| Scan without login | A scan request without user name and password was refused because `CUPSPL_ESCL_ANONYMOUS` is off | never (dismiss it) |
| Backup not done / Backup failed | A backup could not be saved, with the real name of the backup ([backup.md](backup.md)) | the next backup works |
| Certificate expired | Devices no longer trust the gateway ([certificates.md](certificates.md)) | a valid certificate is in place |
| Certificate update failed | The last run of `scripts/cert-sync.sh` failed | the next run works |
| Announced address not in the certificate | Phones that find the printers by themselves will show a certificate error | the certificate lists the address |
| Certificate about to expire | Only if you turned it on (`CUPSPL_CERT_EXPIRY_WARN_ENABLED`) | the certificate is renewed |

To keep one client that retries 100 times from filling the list, the same notice from the same source is written again only
after an interval; the repeats in between are counted. The interval depends on `CUPSPL_LOG_LEVEL`, and the same text is
written to the container log with the same limit:

| `CUPSPL_LOG_LEVEL` | Same notice, same source, reported again after |
|---|---|
| `DEBUG` | 1 minute |
| `INFO` (default) | 1 day |
| `WARNING` | 3 days |
| `ERROR` | 7 days |

`CUPSPL_NOTICE_INTERVAL` (seconds) replaces the table. At most 200 open notices of a kind are kept; dismissed ones are removed after 90 days.

## 8. Operations

- Health: `GET /healthz` → 200 or 503, body `{"status":"ok"}`. It needs no login. `CUPSPL_HEALTHZ_INFO=version,printers` adds the version and the number of queues (usb / network / virtual / total); the default is the status only. Logs: `docker compose logs gateway`.
- Migrations run automatically at start. Back up before updating an important database.
- File names in the audit: the green/red button at the top right of the *Audit* page stops saving them, `.env` can erase them after some days, and they are stored encrypted ([data-protection.md](data-protection.md)). Do not change `CUPSPL_SECRET_KEY`.
- Updates: a note appears at the top of the portal when a newer release exists. Update with `scripts/update.sh`, or with the *Update* button in the menu *Backup* when the optional updater container runs and a scheduled backup works ([installation.md](installation.md#updates)). The updater controls Docker, which is full control of the server: keep it off if you do not need it.
- Do not leave test accounts or test printers on a real installation.
- Protect `config/`, `.env`, `data/` and the volume: they hold secrets and personal data.
