# Printing from Windows 11

[Documentation index](../README.md) · English · [Italiano](../it/windows.md)

Step by step guide to add a printer of the gateway to a Windows PC and print. Tested on Windows 11 Home 25H2: the printer was
added at the first attempt, Windows asks for the credentials when you print, and it has a checkbox to remember them.

You need three things: the **server name** (the address of the portal, for example `print.example.org`), your **user name**, and a
**print key**. The key is not your account password: it is a long text made for printing only.

## 1. Create a print key

1. Sign in to the portal (`https://<server>:8631/`) and open **My print keys** (`/me/keys`).
2. Create a key. Choose how long it lasts and write a label that tells you which PC it is for (for example "office PC").
3. The next page shows the key **only once**: copy it into a safe place (a password manager) before you leave the page. If you lose it,
   create another one and revoke the old one.

## 2. Check that the PC trusts the server

The PC must trust the certificate of the server. If your organisation uses a certificate from a public authority (for example
Let's Encrypt) there is nothing to do. With a private authority or a self-signed certificate, install the certificate file first
(your administrator gives it to you): double-click it → *Install Certificate* → *Local Machine* → *Place all certificates in the
following store* → *Trusted Root Certification Authorities*. Without this step Windows refuses the connection before sending anything
and the gateway log shows nothing.

## 3. Add the printer

1. Open *Settings → Bluetooth & devices → Printers & scanners → Add device*.
2. After a few seconds the printers of the gateway appear, named `<printer> @ <server name>`. Click the one you want and press **Add**.
3. The printer is added and shows as ready. If Windows says "Connecting…" for a long time, **wait up to 3-4 minutes**.

If no printer appears:
- restart the PC;
- if that is not enough, in *Printers & scanners* find *Windows protected print mode*, turn it on and off, then try again;
- if they never appear, the PC and the server are probably on different networks (VLANs) and the announcement does not cross: ask the
  administrator for an mDNS repeater, or add the printer by hand (section 6).

## 4. Print and enter the credentials

1. Print from any program, choosing the printer you added.
2. Windows asks for credentials:
   - **User name**: your portal user name;
   - **Password**: the **print key** from step 1, not the account password.
3. Tick **Remember my credentials**. Later prints ask nothing.

If you do not tick the box, Windows asks again at every print.

## 5. If the printer does not connect

If after 3-4 minutes the printer is still not ready, save the credentials before adding it:

1. *Control Panel → User Accounts → Credential Manager → Windows Credentials → Add a Windows credential*.
2. **Internet or network address**: the same server name you use for the printer (for example `print.example.org`).
3. **User name**: your portal user name. **Password**: the **print key**.
4. Remove the printer from the list in *Printers & scanners* and repeat step 3.

## 6. Adding by hand

When the announcement does not arrive: *Add device → Add manually → Select a shared printer by name* and paste
`https://<server>:8631/printers/<queue>` (without `:8631` when the server is behind a proxy on port 443). Windows picks the
"Microsoft IPP Class Driver" by itself. This way has not yet been tested all the way to a print.

## 7. Later

- **Key expired or revoked**: prints are refused with a login error. Create a new key (step 1) and replace the saved one: *Credential
  Manager → Windows Credentials*, open the entry, change the password. From a terminal: `cmdkey /list` lists the entries and
  `cmdkey /delete:<entry>` removes one.
- **Printer renamed by the administrator**: the old entry stops working. Remove it and add the new one (step 3).
- **Print refused**: the portal tells you why in the bell (`/me/notices`): quota reached, printer or hours not allowed, and so on. From
  your profile you can ask for more quota or a permission ([user-guide.md](user-guide.md)).
