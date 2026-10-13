# Printing and connecting devices

[Documentation index](../README.md) · English · [Italiano](../it/stampa.md)

There are two ways to print: through the **gateway's IPP address** (computers and apps) or from the **browser**
(any phone, nothing to install). Both go through the same quota, audit and identity (`gw:<user>`).

## 1. Printing from the browser

*Print* in the menu (`/me/print`), signed in, no key needed.

- Accepted files: PDF, JPEG, PNG, GIF, plain text — recognised by their **content**, not by name or browser claim.
- Maximum size `CUPSPL_WEB_UPLOAD_MB` (default 25); copies up to `CUPSPL_WEB_MAX_COPIES` (default 20).
- Options depend on the selected printer: paper size (only those the queue lists), orientation, colour / black and white
  (if the queue is colour-capable), **page range** (`1,5`, `2-4`, `3-`), copies and a **comment** (max 50 characters) shown
  under the file name in the audit.
- **Orientation.** *Automatic* follows the file: a PDF whose pages are already wide prints in landscape by itself. *Landscape* on a
  PDF with portrait pages turns every such page 90° and shrinks it to the same sheet (the portal does it, because CUPS' PDF
  filters turn a portrait page upside down on some printers, for example Brother ones). It cannot re-flow the text as LibreOffice
  does when you change the page style to landscape: for that, set landscape in the program and export the PDF again. Photos are
  turned by CUPS. Plain text files cannot be turned (the portal says so and prints nothing).
- The pages counted for the pages limit are the selected pages × copies; a range beyond the end of the document is refused
  before any quota is reserved.
- A printer that does not answer is not offered; a blocked printer is not offered either. The list order is described in
  [printers.md](printers.md).

## 2. Printing with the IPP address

Address: `ipps://<server>:8631/printers/<queue>`. The client authenticates with HTTP Basic: **user name + print key**
(created in *Profile*; see [accounts.md](accounts.md)). The domain password does not print.

| Device | How to connect | Status |
|---|---|---|
| **Linux** (KDE, GNOME, CUPS) | After creating a key the profile page shows the address `ipps://user:key@server/printers/queue` and a ready `lpadmin` command; alternatively `scripts/add-printer-linux.sh <server> <queue> <user>`. The key stays in the queue address (`/etc/cups/printers.conf`, readable only by root and group `cups`) and the computer never asks again. | ✅ tested |
| **Any device with a browser** | `/me/print` | ✅ tested on Android |
| **Android + Mopria Print Service** | Sees the announced printers, asks for name and key per printer and remembers them. | ✅ tested (Android 13) |
| **Android system print service** | Sees the printers but can not ask for credentials: it gives up at the 401. Manual add accepts only an IP, so the key can not be put in the address. | ❌ not usable — use Mopria or the browser |
| **iPhone / iPad** | The announcement carries the AirPrint subtype and `air=username,password`; whether iOS sends the credentials is unknown. | ⬜ not tested |
| **Windows, macOS** | Add a network printer with the IPP address and enter user name + key; "remember". | ⬜ not tested |

The device must trust the server's certificate. Printers announced by mDNS also appear on Linux desktops (Avahi) without
a key: using them does nothing until the queue is added with the key in its address.

Scripts: `scripts/print-test.sh [queue] [user]` sends one small text page (uses a sheet).

## 3. What the gateway does with each IPP operation

Allowed: print (`Print-Job`, `Create-Job` + `Send-Document`), cancel, list jobs and printers, capability queries.
Forbidden for everybody: CUPS administrative operations, `Print-URI`, `Send-URI` (SSRF risk). Capability queries
(`Get-Printer-Attributes`, small bodies) are answered **without credentials** because clients ask before they have any
(`CUPSPL_ANONYMOUS_DISCOVERY=true`): they create no users, no audit rows and forward nothing. The full path is in
[architecture.md](architecture.md#4-path-of-an-ipp-request).

The gateway tells clients `uri-security-supported=tls` and `uri-authentication-supported=basic` (CUPS would say `none`):
without it Mopria does not send credentials.

## 4. Announcement on the network (DNS-SD)

The `mdns` service announces every queue as `_ipps._tcp` with the `_universal` (AirPrint) subtype and TXT records
`rp`, `pdl`, `URF`, `Color`, `Duplex`, `TLS`, `air`, refreshed every `CUPSPL_MDNS_INTERVAL` seconds. The announced host
name is `<name>.local` (Android resolves only those via multicast), and its address must be in the TLS certificate.
Blocked-hidden printers, unreachable devices and maintenance mode withdraw the announcement. Scanners are announced as
`_uscans._tcp` ([scanning.md](scanning.md)).

## 5. Refused jobs, cancel and states

If a job is refused the client gets an IPP error with the reason and the portal address. A user can cancel their own
jobs; an administrator can cancel queued jobs from the audit ("Cancel"), using the owner's identity (no extra CUPS
privilege). States and their meaning are explained in the *Audit* page ([audit.md](audit.md)).
