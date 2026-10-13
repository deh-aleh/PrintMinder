# Printers: overview, controls, maintenance print

[Documentation index](../README.md) · English · [Italiano](../it/stampanti.md)

The **Printers** page (`/admin/printers`, administrators) shows what each printer says about itself next to what the gateway
recorded. Everything is read live and best effort: a printer that does not offer a source just lacks that section.

## 1. What a printer card shows

- State and queue of every CUPS queue; for a device that does not answer, **NOT REACHABLE** (and it disappears from the
  print form and from the mDNS announcement). Detection can lag by ~30 s. For network queues it is a TCP probe (it can
  not know that paper ran out); queues on `usb:` / `file:` are assumed present.
- **Ink** left (levels and colours from CUPS).
- **Printer counters** (lifetime): total pages, black and white, colour, single/double-sided sheets, jams, pick failures —
  read from HP's embedded web service (`/DevMgmt/ProductUsageDyn.xml`). Other brands show only IPP data.
- Serial number, firmware, speed, paper ready, alerts (as the device reports them).
- State and capabilities of the **scanner** (eSCL), with an *MFP* badge for multifunction devices.
- Beside them, what the gateway recorded: jobs, pages, scans, last job.

Reads are parallel, fault tolerant and cached for `CUPSPL_PRINTERS_REFRESH_SECONDS` seconds (default 15; 0 or an unusable value means 15; minimum 5,
maximum 3600 — lower means the printers are asked more often). The **Automatic refresh** switch under the title reloads the page by itself every
that many seconds, so an unplugged printer shows up without pressing F5. It starts off, is remembered by the browser, and the page does not reload
while a popup is open or something is being typed. Nothing is tied to a printer model: colour support, name, inks and
counters are read from the device. Texts coming from the device (ink names, firmware, warnings) are shown as received.

## 2. New and unplugged USB printers

**New printers appear by themselves.** Every `CUPSPL_DISCOVERY_INTERVAL` seconds (30) the gateway looks at the USB side and
creates the CUPS queue of each new device — within about a minute of plugging it in. Two ways, in this order of priority:

1. **ipp-usb** (preferred): a printer with IPP-over-USB (most recent ones) is served by the `ipp-usb` container on a port of
   `CUPSPL_USB_BRIDGE_PORTS`; its queue points at `ipp://ipp-usb:<port>/ipp/print` and needs no driver.
2. **CUPS' own usb backend**: for printers with no IPP-over-USB (many older lasers, for example Brother DCP-7055): the queue
   points at `usb://Maker/Model?serial=…` and CUPS needs a driver. The image ships brlaser, gutenprint, splix and foo2zjs; if CUPS
   has none for the model, the Printers page says so ("found, but CUPS has no driver for it"). A device that ipp-usb serves is
   never taken this way.

   *Checked with a Brother DCP-7055 connected by USB:* it was detected as a USB printer (not as ipp-usb), the queue was created
   with the brlaser driver (`drv:///brlaser.drv/br7055.ppd`) and the very first print from the portal worked, with no setting
   changed. *Landscape* from the portal also gives the expected result on it (see [printing.md](printing.md)).

A device is taken through the usb backend only after it has stayed unserved for two passes in a row (ipp-usb restarts for a few seconds whenever a USB device is plugged or unplugged, and a printer it serves must not be grabbed in that moment).

The queue is named after the model, shortened (at most 24 characters): noise such as "series", "printer", "MFP" and a bracketed part
number is dropped, "Hewlett-Packard" becomes "HP", and a still-too-long name keeps the maker and the words with a digit — `HP Smart Tank
7300 series [A7E76E]` becomes `HP_Smart_Tank_7300`, `Brother DCP-7055` becomes `Brother_DCP-7055`. The model is what the printer itself
declares (for HP's 7300 series the printer says "Smart Tank 7300 series", not the sales name or SKU), so the gateway can not know a more
specific name. Every printer connected by USB shows a badge next to its name: **IPP-USB** (served by the ipp-usb bridge) or **USB**
(driven by CUPS directly). The **Look now** button on the Printers page runs a pass at once.
`CUPSPL_AUTO_DISCOVER=false` turns the whole thing off; `CUPSPL_USB_DIRECT=false` skips path 2.

**Unplugged printers.** A queue outlives the cable, so the card shows **NOT REACHABLE**, a red notice, and:

- a **Delete queue** button (any printer that does not answer, USB or network; it asks for confirmation; a printer that answers can
  not be deleted from here). Block, maintenance-print settings and list position of the queue are forgotten;
- for **USB queues** (ipp-usb or `usb://`), a **countdown** ("will be removed automatically in 7:41:23 (2026-10-13 04:12) unless the
  printer comes back"). When it reaches zero the gateway deletes the queue by itself and writes `printer.auto_remove` in the
  administrators' audit (actor `system`); new devices are logged as `printer.auto_add`. If the printer answers again before the end,
  the countdown disappears. The wait is `CUPSPL_OFFLINE_REMOVE_HOURS` (default 8; `0` = never).
- **network queues are never removed by themselves**: a printer switched off for the weekend must come back as it was. 

If the printer is plugged in again later it is simply added again as a new printer.

## 3. Order of the list

In **Printers**, in the print form of `/me/print` and wherever queues are listed: **physical printers first, in order of
connection** (oldest on top); **virtual / test printers** (CUPS-PDF, `debugprinter0`…) at the bottom, also oldest first.

**Moving printers.** Each card has an up and a down arrow next to its other buttons. They move the printer one place in **your own**
list: every administrator has their own order, so if you put printer A before B another administrator can still see B before A. The
order is also the one of your own print form (*Print*). A button is greyed out and not clickable when the printer is already at that end.
A printer moves only inside its group: physical printers stay above the virtual ones. Once you have moved a printer its place in your list
is fixed; a printer connected later goes after the ones you already placed (in its group). Moves are written to the administrators'
audit (`printer.move`). A printer you never moved follows the default order described below.

**Renaming a queue.** The pencil button opens a dialog with the queue name (the last part of the address, `…/printers/<name>`; letters,
digits and `. _ @ + -`). CUPS can not rename a queue, so the gateway creates the new one on the same device — same driver (IPP printers:
driverless; USB: the driver CUPS has for it; virtual: CUPS-PDF), same description and location — and only then removes the old one; if
anything fails the old queue stays. Block, hide-from-mDNS, maintenance-print settings, the countdown and the places in the lists follow the
queue; the audit keeps the old name for what already happened. Clicking *Rename* asks for confirmation and warns that **computers and
phones set up by hand with the old address will stop printing** until they are set up again. A queue with jobs waiting, a name already
in use, or a queue whose driver the gateway can not know (for example a `socket://` queue) is refused. Options set by hand in CUPS
(default paper, …) are not carried over. Logged as `printer.rename`.

CUPS does not say when a queue was created, so the gateway notes the **first time it sees** each queue (it looks every
minute, so a printer that was connected and never opened in any page is still registered within a minute). Queues that
existed when this feature was introduced were all "seen" at the same instant and stay alphabetical among themselves; a
deleted queue loses its place (a new queue with the same name goes last). The mDNS announcement has no database and stays alphabetical.

## 4. Periodic maintenance print (physical printers only)

A printer that sits idle for weeks dries its ink and glues its rollers. The gateway can print a small maintenance page at
regular intervals. Button with a printer-and-timer icon at the top right of each card (absent for virtual printers; the
server refuses the request anyway).

- **One setting per printer, the same for every administrator.**
- The popup has: an **activation switch** next to the title (acts immediately), the **interval** (number + hours/days,
  from 1 hour to 90 days; suggested: 1 week, with shortcuts), **colour print** (only if the printer declares colour) and
  **Save**, which stores the parameters **without** switching the schedule on or off. The ✕ closes without changing anything.
- The count starts at activation, then from the last **successful** maintenance page; normal user prints do not reset it.
- If the printer does not answer, it retries as soon as it is reachable again; if CUPS refuses the job, it retries after an
  hour and the error stays visible on the card. If the gateway was off, the page is printed as soon as it restarts (the
  missed interval is not made up).
- The page goes to CUPS with the identity `gw:maintenance`: it **uses no quota**, is **not in the print audit**, and
  **ignores the printer block and maintenance mode** (it is for the hardware's health). Who switches on, off or saves is in
  the administrators' audit (`printer.keepalive_on/off/save`).

## 5. Test print with statistics

Button with a bug icon: asks for confirmation with **Cancel**, **Print black & white**, **Print colour** (disabled if the
printer has no colour) and prints the same statistics as the card (state, ink, counters, gateway data, details, scanner). Logged as
`printer.test_print`. The page is A4 (the driver fits it to the loaded paper). Pages the gateway prints itself are always in
English ([languages.md](languages.md)).

## 6. Block, hide, maintenance

- **Block a printer** — takes no job from anybody, **administrators included** (out of order or reserved). Per queue.
- **Hide from mDNS** — the printer is no longer announced on the network; still usable by address.
- **Gateway maintenance** (red wrench button at the top) — stops printing **and scanning** for everybody except administrators and
  withdraws every mDNS announcement. A red banner shows the state on every page.

The mDNS announcer asks the gateway (`/mdns/policy`, authenticated by a code derived from `CUPSPL_SECRET_KEY`).

## 7. Test printers

In **Printers** an administrator can create and delete **test printers** (`debugprinter0`, `1`, …): CUPS-PDF queues that
write PDFs and use no paper. They behave like a printer for quotas and audit — useful to try the system — and are listed
last. They have no maintenance or test-print buttons.

A queue named `virtual` is created by `CUPS_VIRTUAL_QUEUE=1` for the same purpose.
