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
- **Permissions** ([quotas.md](quotas.md#5-advanced-permissions)). Only the printers the user may use are listed. The colour choice is
  hidden without the colour permission. A **double-sided choice** (printer default / one-sided / long edge / short edge) appears when the printer has a duplex unit
  and the user may print one-sided; a user who may not, prints double-sided (long edge). The form asks for a choice, the server decides
  with the same rules as the IPP gateway, so a form edited by hand gets the same result. Outside the allowed hours a banner at the top
  says when printing is possible, and a job sent anyway is refused.

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
| **Windows 11** | "Add device" finds the announced printers; the password is entered at the first print. Steps in the [Windows 11](#windows-11) section below. | 🟡 tested on Windows 11 25H2 |
| **macOS** | Add a network printer with the IPP address and enter user name + key; "remember". | ⬜ not tested |

The device must trust the server's certificate. Printers announced by mDNS also appear on Linux desktops (Avahi) without
a key: using them does nothing until the queue is added with the key in its address.

Scripts: `scripts/print-test.sh [queue] [user]` sends one small text page (uses a sheet).

### Windows 11

Tested on Windows 11 Home 25H2, with a server that has a trusted certificate and a name the PC resolves. The PC must trust the
server's certificate (see [certificates.md](certificates.md)): with a self-signed certificate that is not installed, Windows refuses
the connection before it sends any request, and nothing shows in the gateway log.

1. Open *Settings → Bluetooth & devices → Printers & scanners → Add device*. After a few seconds the announced printers appear,
   named `<printer> @ <server name>`.
   - If no printer appears, restart the PC. If that is not enough, the same page (*Printers & scanners*) has
     *Windows protected print mode*: turn it on and off, then try again.
   - If the printers never appear, the PC and the server are usually on different networks (VLANs) and the mDNS announcement does not
     cross: you need an mDNS repeater (many routers have an "mDNS repeater" option) or the manual way, below.
2. Click the printer and press *Add*. Windows says "Connecting…": **wait up to 3-4 minutes**. In the end the printer shows as ready.
3. At the first print Windows asks for the user name and the **print key** (not the account password). Tick "Remember my credentials":
   later prints ask nothing.
4. If the printer does not connect after 3-4 minutes, save the credentials beforehand:
   *Control Panel → User Accounts → Credential Manager → Windows Credentials → Add a Windows credential*.
   - Internet or network address: the same server name you use for the printer (for example `print.example.org`).
   - User name: your portal user name.
   - Password: the **print key**, not the account password.

   Then remove the printer from the list and repeat from step 1.

**Adding by hand**, when the announcement does not arrive: *Add device → Add manually → Select a shared printer by name* and paste
`https://<server>:8631/printers/<queue>` (without `:8631` when the server is behind a proxy on port 443). Windows picks the
"Microsoft IPP Class Driver" by itself. This way has not yet been tested all the way to a print.

If you rename a queue in the portal the PC does not know: the old entry stops working and the new one has to be added as above.
Saved credentials can be listed and removed with `cmdkey /list` and `cmdkey /delete:<entry>`.

## 3. What the gateway does with each IPP operation

Allowed: print (`Print-Job`, `Create-Job` + `Send-Document`), cancel, list jobs and printers, capability queries.
Forbidden for everybody: CUPS administrative operations, `Print-URI`, `Send-URI` (SSRF risk). Capability queries
(`Get-Printer-Attributes` and `Validate-Job`, small bodies) are answered **without credentials** because clients ask before they have any
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

### Permissions and IPP

For `Print-Job`, `Create-Job` and `Validate-Job` the gateway applies the user's permissions (colour, one-sided, printers, hours)
after the blocked-printer check and before the quota. To correct a job it rewrites `print-color-mode` and `sides` in the request before it goes to
CUPS, and removes the PPD-style options `ColorModel`, `ColorMode` and `Duplex`. `Validate-Job` does not fail on colour or sides in `adjust`
mode. `CUPS-Get-Printers` and `CUPS-Get-Classes` leave out the printers a limited user may not use. A phone or computer that found the
printer through the network announcement still sees it, because the announcement is the same for everybody; the job is refused. Details and cautions:
[quotas.md](quotas.md#5-advanced-permissions).

## 5. Refused jobs, cancel and states

If a job is refused the client gets an IPP error with the reason and the portal address. A user can cancel their own
jobs; an administrator can cancel queued jobs from the audit ("Cancel"), using the owner's identity (no extra CUPS
privilege). States and their meaning are explained in the *Audit* page ([audit.md](audit.md)).
