# Accounts, groups and print keys

[Documentation index](../README.md) · English · [Italiano](../it/account.md)

## 1. Who is who

Every person is **one row** in the `user` table with a *provider*:

- **local** — the password (argon2id) lives in the gateway database and is managed in the portal;
- **RADIUS** (optional) — the password is checked by the office RADIUS server; the gateway never sees it stored.

**User names are unique across all sources.** CUPS and the audit only receive `gw:<name>`, so two people with the same name
would share identity and quota. The method of login is decided by the *row*, never by who answers "yes": a local account
can not be opened by RADIUS even if RADIUS knows the same name. An unknown RADIUS user is created at the first portal login
(in the default group) when `CUPSPL_AUTO_CREATE_USERS=true`; if the name is already local, no.

RADIUS is optional. With `CUPSPL_RADIUS_HOST` and `CUPSPL_RADIUS_SECRET` empty only local accounts exist. If RADIUS does
not answer, access is denied (fail closed). RADIUS names are matched case-insensitively: `Mario` and `mario` are the same person.

## 2. The first administrator

`cups_orchestrator` exists without a password. At the first start the gateway prints a **one-time code** in its log
(`docker compose logs gateway | grep "FIRST RUN"`); `/admin/setup` asks for it and for the new password, then deactivates
itself. The code is protected by throttling. Alternative: `cups-policy-admin set-admin-password`. There is deliberately no
page open to everybody for becoming an administrator.

The emergency account cannot be disabled, demoted, deleted or have its source changed. Nobody can disable, demote or
delete themselves, nor the last administrator.

## 3. Passwords (local accounts)

Minimum 12 characters, not equal to the user name. A password created or reset by an administrator is **temporary**: shown
once, and the user must change it at first login. Changing a password closes the user's other sessions. Login always
spends the cost of a hash, even for names that do not exist, and never reveals whether a name exists.

## 4. Groups

Quota limits are set per **group**, with optional per-user overrides ([quotas.md](quotas.md)). Two system groups always exist
and cannot be deleted:

- `default` — where everybody starts and where users go when their group is deleted or they stop being administrators;
- `administrator` — only for administrators. Promoting a user moves them there; demoting moves them back to `default`.
  A non-administrator can not be moved into it by hand.

A group can be marked **requestable**: users may then ask to move into it ([quotas.md](quotas.md)). Administrative groups never are.

## 5. Print keys

Operating systems keep print passwords in clear text (for example `printers.conf` on Linux). So clients **never** use the
domain password: they use a **personal print key**.

- Created by the user in *Profile → Create a key* (label per device). Shown **once**; stored only as a sha256 hash of
  192 random bits.
- Valid **only for printing and scanning** (the IPP and eSCL endpoints); it never opens the portal.
- Has an expiry: default 90 days for RADIUS users, 365 for local ones. A RADIUS user renews by logging in again in the
  portal — so someone who leaves the company stops printing at the expiry. The administrator can revoke keys at any time.
- Last use (time and IP) is recorded at most once a minute.
- Revoke one key, or all of them, in *My keys* (`/me/keys`) or, for an administrator, in `/admin/users/<id>/keys`.

`CUPSPL_IPP_AUTH=keys` (default) accepts only keys for printing. `keys+radius` also accepts the RADIUS password for RADIUS
users during a transition (never for local accounts): it encourages saving the domain password on clients, so use it only
temporarily.

## 6. Protection of logins

- 5 *different* wrong passwords within 5 minutes for the same (user, IP) block that pair; there is also a per-IP cap. The
  same wrong password repeated by one client counts once (libcups retries 3–5 times), and a stranger can not lock another user out.
- The lock is in memory: a restart clears it. It blocks the (user, IP) pair for 5 minutes, it does **not** disable the account: the same
  user from another address is not affected. While blocked, the login page answers "Too many failed attempts, retry later" even if the
  password is then right. To see it, try six *different* wrong passwords; repeating the same one never blocks.
- Disabling a user in the portal blocks portal login and keys immediately.
- Portal sessions: signed, 8 hours, CSRF token on every POST, `Secure` + `SameSite=strict` cookies. Pages that show a secret
  are sent with `Cache-Control: no-store`.

## 7. Deleting a user

Removes the account, keys, requests, grants and personal limits, but **not the history**: audit rows keep the user name and
only lose the link to the user id; administrative audit rows already store the actor's name. The administrator types the user
name to confirm.

## 8. Changing the source of an account

From the user's edit page: local → RADIUS erases the stored password; RADIUS → local generates a temporary password shown once.
The emergency account stays local.
