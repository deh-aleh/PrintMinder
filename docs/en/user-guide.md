# User guide

[Documentation index](../README.md) · English · [Italiano](../it/guida-utente.md)

For people who print and scan. Everything is at `https://<server>:8631/me` (administrators arrive at `/admin`; the menu
links to both).

## 1. Sign in

Open the portal and sign in with the account the administrator gave you (a local password), or with your office
credentials if the installation uses RADIUS. A temporary password must be changed at the first login.

## 2. My profile (`/me`)

- **Consumption**: jobs and pages used in the current week or month, your limit (including any extra quota granted to you),
  and when it resets.
- **Print keys**: create a key for each device (give it a label). It is shown **once**: copy it at once (copy button). Use it
  as the password when the computer or phone asks for credentials; the user name is yours. A key only prints and scans — it
  never opens the portal and your domain password is never needed on a device. Revoke a key (or all of them) in *My keys* if a device is lost.
  When you create one you choose how long it lasts (from 1 month to 2 years, or one print only); RADIUS users have a shorter maximum and renew by signing in to the portal again. The bell at the top tells you when an administrator revokes, switches off or extends one of your keys.
- **Requests**: ask for more quota (temporary or permanent), for a change of group or for a permission (see below), with a reason. The administrator
  approves, edits or rejects. You can have up to 3 open requests, and cancel them.

- **Your permissions**: whether you may print in colour and one-sided, on which printers, and at which hours. If you may not print in
  colour, your prints come out in black and white; if you may not print one-sided, they come out double-sided. Scanning is not affected.
  Next to what you lack there is an **Ask** link (and **Ask for another printer**): choose what you need, write why, and an
  administrator answers. While a request waits, "(request waiting)" stands in place of the link. The answer may be permanent or last until a date; the bell tells you when it is approved, rejected or has
  ended, and the box shows the permissions you were granted and until when.

If a print is refused for quota, the message includes the link to ask for an exception. If it is refused because of your permissions
(a printer you may not use, a time outside your hours, or colour / one-sided when the installation refuses instead of correcting),
the message points to this page, and the bell tells you what happened and what to change. When a print is made in black and white or
double-sided because of your permissions, the bell tells you that too.

## 3. Print (`/me/print`)

Upload a PDF, photo (JPEG, PNG, GIF) or plain text. Choose the printer (only the ones you may use are listed), paper size, orientation, colour or black and white (only if you may print in colour), one-sided or double-sided (only if you may print one-sided and the printer has a duplex unit), a page
range (`1,5` or `2-4`), copies and an optional comment (50 characters, visible to administrators next to the file name). Same
quota and audit as every other print. Works from a phone with nothing installed. See [printing.md](printing.md) for connecting a
computer.

## 4. Scan (`/me/scan`)

Choose the scanner (if more than one), the source (automatic, glass, or feeder for all sheets), colour mode, quality, paper size,
format (PDF or JPEG) and a file name. You can leave the page while it scans and come back to download the file within 15 minutes.
See [scanning.md](scanning.md).

## 5. Settings (click your name, top right)

- **Theme**: light, dark or automatic.
- **Language**: English, Italiano, Español, Русский, 中文. Saved for your account.
- **Auto-refresh** interval of the audit page (administrators); the Audit and Printers pages also have an *Automatic refresh* switch.
- **Change password** (local accounts).

## 6. Good to know

- Your quota counts accepted, completed and held jobs; rejected, failed and canceled-before-printing jobs are free.
- A pages limit is checked before printing: a document that does not fit is refused at once.
- Printers that do not answer, or are blocked, are not offered. Printers you may not use are not offered either.
- If your hours are limited and it is outside them, the print page says when you can print, and a job sent anyway is refused.
