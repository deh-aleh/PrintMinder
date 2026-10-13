# Quotas, requests and grants

[Documentation index](../README.md) · English · [Italiano](../it/quote.md)

## 1. Limits

A **rule** says: *this user or this group may print at most N **jobs** (or **pages**) per **week** (or **month**)*.

- Rules belong to a group, with optional **per-user overrides**. A user rule replaces the group's rule for the same metric.
- Metrics: **jobs** and **pages**. Periods: **weekly** (Monday–Sunday) or **monthly** (calendar month), in the time zone
  `CUPSPL_TIMEZONE`, also across the daylight-saving change.
- No rule = no limit.
- Where to set them: *Groups* → edit (group limits), *Users* → edit (personal limits), or the CLI:
  `cups-policy-admin group-limit staff 20 --period monthly`, `cups-policy-admin user-limit mario 5 --metric pages`
  (`none` removes a limit).

### What counts

Jobs in the state `accepted`, `completed` or `held` count. **Rejected, failed and canceled-before-printing jobs do not
consume quota.** The user sees consumption and the next reset in *Profile*.

### Counting pages before printing

When a pages limit applies to a user, the gateway reads the document **before** printing (up to 64 MB) and counts its pages:
PDF (pypdf), JPEG/PNG/GIF = 1, URF from the header, PostScript from `%%Pages`, plain text ≈ 60 lines per page; then
multiplies by the copies and by the selected page range. If `used + pages > limit` the job is **refused at once**:

> `would be exceeded (used 90, this document 200, limit 100)`

Otherwise the pages are recorded immediately, so simultaneous jobs see them. After printing, the reconciler replaces the
estimate with the **real pages** read from CUPS. A job whose page count is not yet known counts as at least 1 page.

### The soft limit (important)

The pages limit is **hard** only for documents the gateway can count. It is **soft** in these cases:

- unknown format, **encrypted PDF**, or a file larger than 64 MB: the job that crosses the limit *is printed*, and its
  real pages then block the following jobs;
- a job sent with `Create-Job` + `Send-Document`: the pages are counted at `Send-Document`, when the job has already
  been accepted;
- a `Create-Job` without any document frees its quota only when CUPS cancels it (default after 3 hours).

### Atomic reservation

Checking the limit and recording the job happen under a lock (thread + `BEGIN IMMEDIATE` on SQLite; advisory lock on
PostgreSQL), so many simultaneous jobs can not exceed the limit. Active grants are added to the limit **inside** the same check.

## 2. Requests from users

In *Profile* a user can ask for:

1. **More quota** — choose the metric, the amount, **temporary** or **permanent**, and write a reason. The user can ask only
   for metrics that actually have a limit. The **period is not chosen by the user**: it is that of the rule the
   administrator set; the form shows it read-only ("your pages limit is monthly: the exception lasts until 1 November").
2. **Change of group** — only towards groups marked *requestable*.

Brakes: at most `CUPSPL_MAX_OPEN_REQUESTS` (3) open requests per user, a reason is mandatory (always treated as plain text),
requests expire after `CUPSPL_REQUEST_TTL_DAYS` (14). The user can cancel a pending request.

## 3. Approval and grants

Administrators see pending requests in **Requests** (with a badge in the menu) and can **approve, edit or reject** them. When
approving they can change the amount and the type (even turning a permanent request into a temporary one) and add a note.

Approval produces a **grant** (concession) that is **added** to the limit:

`effective limit = rule + active grants`

- A **temporary** grant lasts until the end of the period window **in which the approval happens** (not the one of the
  request: a request made on Sunday night and approved on Monday must not be born expired).
- A **permanent** grant applies to every following period ("+20 pages every month") until revoked.
- A group change moves the user at once; the new group's limits apply from then on.
- Approval is **idempotent**: one conditional `UPDATE`, so two administrators or a double click grant once.
- Grants never touch history (`job_log` is not edited).

Administrators can also grant or revoke quota directly in **Grants**. Everything lands in the administrators' audit
([audit.md](audit.md)). The users list shows active grants as a coloured `+N`.

## 4. Reasons shown to users

When a job is refused, the IPP client receives the reason in English plus the portal address to ask for an exception.
The portal shows the same sentence translated ([languages.md](languages.md)). The audit stores the English reason.
