# Scanning

[Documentation index](../README.md) · English · [Italiano](../it/scansione.md)

Scanning uses **eSCL** (AirScan): `ipp-usb` serves it on the same port as IPP, so printing and scanning go through the same
USB device without fighting over it — **ipp-usb is the only owner** (the host's `ipp-usb` and SANE must be stopped). A print
sent during a scan works. SANE over the network was rejected: it does not authenticate per user and would bring back the
device conflict; TWAIN Direct is hardly supported.

## 1. Scanner discovery

Scanners are not configured one by one; they are **found at run time**:

- every network CUPS queue (ipp-usb gives each USB printer its own port) is asked for its eSCL capabilities;
- plus the addresses listed in `CUPSPL_SCAN_URL` (`name=url`, comma separated; the image presets `http://ipp-usb:60000`;
  empty = automatic discovery only).

Scanners answer eSCL on the queue's IPP port or on port 80; other cases go in `CUPSPL_SCAN_URL`. A disconnected scanner
disappears within ~30 s. The `mdns` service announces each scanner as `_uscans._tcp` (`rs` = `eSCL` for the default one,
`eSCL-<id>` for the others).

## 2. Scanning from the portal

*Scan* (`/me/scan`): no installation, works from any phone.

- **Scanner** selection if there are several.
- **Source**: *Automatic* (feeder if the scanner declares `ScannerAdfLoaded`, otherwise glass), *Glass*, or *Feeder* (reads **all** sheets until
  `NextDocument` answers 404; maximum 100).
- Colour / grey / black and white; **quality** and **paper size** from what the scanner really declares for that source
  (for example a flatbed up to 1200 dpi and a single-sided feeder up to 300).
- Output: **PDF** (several sheets merged with pypdf) or **JPEG** (several sheets: ZIP); a **file name** field.
- Where to save: Chromium browsers open a folder-picker (File System Access API); others save to the downloads folder (a web
  page can not write to a hand-typed path).
- The scan runs as a **background task on the server**: you can leave the page and download later (the result is kept
  **15 minutes in memory**, visible only to its owner; one web scan at a time). If the scanner answers 409/503 (waking up)
  the gateway retries 3 times.

## 3. Scanning with eSCL clients

The gateway exposes `/eSCL/...`. `ScannerCapabilities` and `ScannerStatus` are public (like the IPP capability query);
everything else needs HTTP Basic with **user name + print key**, same authentication and throttling as printing. Allowed paths:
`ScanJobs` (POST), `ScanJobs/<id>/NextDocument|ScanImageInfo` (GET), `ScanJobs/<id>` (DELETE); the rest is 404.

- Every scan is a row in the audit with `kind=scan`; the device is the scanner's CUPS queue. States: `accepted` → `completed`
  (1 page per `NextDocument`), `failed` (scanner busy or not answering), `canceled` (only if canceled before delivering the page).
- A user can neither read nor cancel another user's scan (404). `Location` is rewritten to the gateway address.
- The eSCL job stays tied to the user until the client deletes it with DELETE — that is what frees the scanner.
- **Clients with no credentials** (NAPS2 can not send them): `CUPSPL_ESCL_ANONYMOUS=true` accepts scans without login, recorded
  as the passwordless local account `ospite-scansione` (it can not log in to the portal), with the caller's IP in the audit
  options. Wrong credentials are still 401. While the option is off, a request without credentials is refused (401) and shows up as a notice in the bell ([admin-guide.md](admin-guide.md)), at most once per interval and source. **Default off**; anyone on the network who reaches port 8631 could scan: use only on a trusted
  network. NAPS2 did not find the mDNS announcement: type IP and port by hand.

## 4. Notes

- A scan delivered to the client counts as completed even if the user does not save the file.
- If the feeder is asleep the scanner may declare it empty: *Automatic* then uses the glass (blank page). Choose *Feeder*, or
  remove and re-insert the sheets.
- Maintenance mode stops scanning too ([printers.md](printers.md)).
- Not tried yet: native eSCL clients that authenticate (sane-airscan, Image Capture).
