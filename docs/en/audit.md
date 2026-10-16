# Audit

[Documentation index](../README.md) · English · [Italiano](../it/audit.md)

PrintMinder keeps **two append-only logs**:

| Log | Table | Content | Page |
|---|---|---|---|
| Print and scan audit | `job_log` | who printed or scanned what | **Audit** (`/admin/jobs`) |
| Administrative actions | `admin_audit` | who did what in the portal | **Admin actions** (`/admin/actions`) |

Ids are never reused. **No portal function deletes a row.** Audit is kept forever.

## 1. Print and scan audit

Each row has: sequential number (N.), time, user, device (printer queue or scanner), file name, type (print / scan), outcome,
pages, rejection reason, and options (paper, colour, duplex, source, copies, page range, comment, `via` web / IPP…).

**The file name is encrypted** in the database and you can stop saving it with the green/red button at the top right of the page; with retention (`.env`) it disappears
after a number of days you choose. The row always stays, with everything else. Details in [data-protection.md](data-protection.md).

| State | Meaning |
|---|---|
| `accepted` | Passed the checks and was handed to CUPS or the scanner (printing, queued or in progress). **Already counts toward quota.** |
| `completed` | Finished; the pages are the **real** ones read from CUPS |
| `held` | Held in the queue; counts toward quota |
| `rejected` | Refused (quota, block, maintenance, invalid). Does not count. The reason is stored (in English) |
| `failed` | Accepted but the printer or scanner could not carry it out. Does not count |
| `canceled` | Stopped before printing, by the user, an administrator or the scanning program. Quota is freed |

The page is readable on a phone: 30 actions per page, an **Automatic refresh** switch on the page itself (the interval is set in *Settings*, default 30 s; with 0 the switch starts off and uses 30 s when turned on; the choice is remembered by the browser), alternating
rows, long texts shortened with «…» and a popup for the full text, columns *Device* / *Action* (feeder, colour, duplex), an
adaptive layout and a menu that is always visible. Filters and **CSV export** are available (formula injection is neutralised).
The *Cancel* button stops a queued job (the owner's identity is used).

Scans without credentials (anonymous eSCL) show the caller's IP and host name in the information column. A scan made through a scan window shows the same icon with the address it came from. A request refused because it came from another address than the one the window was opened for is a *denied* row under the window's owner; the icon shows the two addresses.

### Usage report

*Report* (button next to *Export CSV* in `/admin/jobs`, page `/admin/report`) ranks the users by pages printed in a period. You choose the dates (default: the last 30 days),
how many users to list, the groups to **leave out** (by the group each user has now; a deleted account has none and is always counted), and **Detailed report**, which adds the prints per
printer for each user. It can be shown in the page or downloaded as **CSV** or **PDF**. Only prints count (completed, waiting or running); failed and cancelled ones and scans do not.
Rows already moved to a compressed archive are not read: the page warns when the period reaches back that far. The PDF is in English and uses the standard fonts, so names with
Cyrillic or Chinese letters show as `?` there; the CSV keeps them.

## 2. Reconciliation with CUPS

Every 30 s the **reconciler** reads CUPS: a finished job becomes `completed` with its real pages; one canceled before printing
returns its quota; reservations with no CUPS job for over 1 hour (gateway died mid-way) are released; a job gone from history
for over a day is marked completed.

## 3. Administrative audit

Logins of administrators, creation / change / deletion of users and groups (`user.*`, `group.*`), passwords and keys
(`password.change`, `key.*`), approvals and rejections (`request.approve/reject`), grants (`grant.create/revoke`),
printer controls (`printer.block/unblock`, `printer.mdns_hide/mdns_show`, `printer.keepalive_on/off/save`,
`printer.test_print`, `printer.debug_create/delete`, `printer.move`, `printer.rename`, and by the system itself `printer.auto_add` / `printer.auto_remove`), backups (`backup.*`), maintenance mode (`maintenance.on/off`),
audit archiving (`audit.archive`). 
Each entry keeps the actor's *name* (it survives deleting the actor), the action,
the target and details. The page has filters with suggestions.

## 4. Archive

When the active tables exceed `CUPSPL_AUDIT_MAX_MB` (default 50), the archiver (checks every `CUPSPL_AUDIT_CHECK_INTERVAL`,
default 1 h) moves the **oldest rows** to `data/audit-archive/audit-<table>-<from>-<to>.jsonl.gz`. Guarantees:

1. Rows of the quota windows still in play (previous and current month, plus margin) are **never** archived, so limits do not change.
2. The file is written as `.pending`, flushed, **read back and verified** (sha256).
3. Only then, in **one transaction**, the archive is registered in `audit_archive` (path, date and id range, rows, size, sha256)
   and the rows are removed from the table.
4. The file is renamed and made read-only. An existing archive is never overwritten.
5. An interruption anywhere loses nothing and duplicates nothing: `.pending` files are repaired or cleaned at restart.

The **Audit archive** page (`/admin/archive`) lists archives with the path inside the container and on the host
(`AUDIT_ARCHIVE_HOST_PATH`, informational), size and sha256; opens them with search and pagination (streaming), **downloads**
them and **verifies integrity**. It can not delete them. The Audit page shows a banner when archives exist.
`cups-policy-admin audit-archive [--force]` runs the archiver by hand; `cups-policy-admin jobs` shows the latest rows.

File names in the archive stay **encrypted** (the portal decrypts them when it shows them and when you search); with retention on, rows past the limit are written without the name. Files already written are never modified.

The folder must be writable by the container user; it lives on the host, outside docker volumes, so it can be found and
copied by hand. It is included in the backups ([backup.md](backup.md)).

## 5. Privacy

The database and the archives are **not encrypted** and contain the names of printed files, which are personal data:
protect `data/` and the volume like personal data. Anonymisation and syslog/SIEM export are not implemented yet.
