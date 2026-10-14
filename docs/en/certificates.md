# TLS certificates: notices and synchronisation

[Documentation index](../README.md) · English · [Italiano](../it/certificati.md)

The gateway only talks in encrypted form (TLS, the padlock in the browser) and for that it needs a **certificate**. This page explains what it must
look like, what the portal tells you when something is wrong, and how to keep it up to date by itself when another machine renews it (for example
Nginx Proxy Manager).

## 1. What a phone checks when it connects

The certificate is like an identity card of the server. When a phone or computer connects, it checks three things:

1. the card was issued by someone the device trusts (a **CA**, an authority that issues certificates);
2. the name or address written on the card is the one it is connecting to;
3. the card has not expired.

**Example.** The certificate says "valid for `print.company.com` and `192.168.1.50`". The phone finds the printer as `https://192.168.1.50:8631`:
the address is on the card, so it is fine. If one day the router gives the server `192.168.1.77`, the phone does not find that address on the card
and shows "invalid certificate". This is why the certificate must list the address that the gateway announces on the network (mDNS).

If one of these three fails, the device refuses to print or shows a security warning.

## 2. The notices in the portal (the bell)

The gateway never changes the certificate by itself: it **looks at it** and, if it sees a problem, puts a notice in the administrators' bell.
The notice goes away by itself when the problem is solved.

| Notice | When it appears | Can it be turned off? |
|---|---|---|
| The certificate has expired | The expiry date has passed: devices no longer connect | No, it is always on |
| The last certificate update failed | The last run of `scripts/cert-sync.sh` ended with an error (the message of the script is in the notice) | No, it only appears if you use the script |
| The announced address is not in the certificate | Neither the IP nor the `.local` name that the gateway announces on the network is in the certificate | Yes: `CUPSPL_CERT_NAME_CHECK=false` |
| The certificate is about to expire | Less than N days are left | **Off by default.** `CUPSPL_CERT_EXPIRY_WARN_ENABLED=true` turns it on, `CUPSPL_CERT_EXPIRY_WARN_DAYS=14` chooses the days |

The settings are in `.env` (then `docker compose up -d`).

**Why the "about to expire" notice is off.** We do not want anyone to find a notice to deal with when the renewal is simply not due yet.
Let's Encrypt certificates last 90 days and are renewed about 30 days before the end: with the threshold at 14 days the notice only appears if the
renewal has failed for more than two weeks, that is, if there really is a problem. With a high threshold (for example 45 days) the notice would
appear every time before the normal renewal, so do not set it above 30 days with Let's Encrypt. Certificates of a company CA often last a year and are
renewed by hand: there a threshold of 30 days is fine.

The notice also says where to look: if the last synchronisation worked, "the source has not renewed it yet, check Nginx Proxy Manager"; if it
failed, it points to the other notice.

## 3. The CA file: what to do with it

If your company has its own CA, the person who runs it gives you a file (usually `.crt` or `.pem`): it is the **certificate of the CA**, never the private key.
It makes devices trust every certificate that CA issues, the gateway's included. It must be installed **once on every device**:

| Device | What to do |
|---|---|
| Android | *Settings → Security → Encryption & credentials → Install a certificate → CA certificate*, pick the file. The browser accepts it; **some apps ignore CAs added by the user**: if an app refuses to connect, use a certificate from a public CA (for example Let's Encrypt). |
| iPhone / iPad | Open the file (from Mail or Files), *Settings → Profile Downloaded → Install*. Then *Settings → General → About → Certificate Trust Settings* and switch the CA on: without this second step the certificate stays untrusted. |
| Windows | Double-click the file → *Install Certificate* → *Local Machine* → *Place all certificates in the following store* → *Trusted Root Certification Authorities*. |
| macOS | Open *Keychain Access*, drag the file into *System*, double-click the certificate → *Trust* → *Always Trust*. |
| Linux (Debian, Ubuntu) | Copy the file to `/usr/local/share/ca-certificates/` with the extension `.crt`, then `sudo update-ca-certificates`. Firefox has its own store: *Settings → Privacy & Security → Certificates → View Certificates → Authorities → Import*. |

If you have no CA and use the self-signed certificate made by `scripts/docker-init.sh`, the file to install is `config/tls/fullchain.pem`, with the same steps.

With a certificate from a public CA (Let's Encrypt) there is nothing to install on the devices: they already trust it.

## 4. Copying the certificate by hand

Put `fullchain.pem` (the certificate, with its chain) and `privkey.pem` (the key) in `config/tls/`, make the key readable only by you
(`chmod 600 config/tls/privkey.pem`) and restart: `docker compose restart gateway`. Details and an example with Nginx Proxy Manager are in
[installation.md](installation.md#34-tls-certificate).

A Let's Encrypt certificate is renewed about every 60 days: doing it by hand each time is easy to forget. That is why there is the script of the next chapter.

## 5. Keeping the certificate up to date by itself: `scripts/cert-sync.sh`

### 5.1 How it works

You run it **once** by hand to try it, then you put it in `cron` (the Linux clock that runs commands at fixed times). Each time the script:

1. downloads the two files from the machine that renews the certificates (with `rsync` over `ssh`) into a private temporary folder;
2. checks them: the certificate is not expired and the private key is really its own;
3. if they are the same as the ones in use, it **stops** (nothing to do, no restart);
4. otherwise it puts the old pair aside in `config/tls/previous/`, installs the new one and restarts the gateway;
5. writes how it went to `config/tls/sync-status.json`: if it went badly, the portal shows the notice "the last certificate update failed".

If something is wrong in the checks, **the files in use are not touched**: a wrong certificate cannot break a server that works.

### 5.2 The settings (in `.env`)

| Setting | What | Default |
|---|---|---|
| `CERT_SYNC_HOST` | The machine that has the certificate (name or address) | required |
| `CERT_SYNC_USER` | The user to connect as (the read-only one of §5.3) | required |
| `CERT_SYNC_KEY` | **Full** path of the ssh private key of this machine | required |
| `CERT_SYNC_REMOTE_DIR` | **Full** path, on the remote machine, of the folder that holds the two files | required |
| `CERT_SYNC_PORT` | ssh port | `22` |
| `CERT_SYNC_CERT_FILE` | Name of the certificate file (with the chain) | `fullchain.pem` |
| `CERT_SYNC_KEY_FILE` | Name of the key file | `privkey.pem` |

The path and the names change with the program that renews the certificates, which is why they can be chosen:

| Program | `CERT_SYNC_REMOTE_DIR` (example) | Files |
|---|---|---|
| Nginx Proxy Manager, Let's Encrypt certificate | `/home/you/npm/data/letsencrypt/live/npm-3` | `fullchain.pem`, `privkey.pem` |
| Nginx Proxy Manager, custom certificate | `/home/you/npm/data/custom_ssl/npm-3` | `fullchain.pem`, `privkey.pem` |
| certbot | `/etc/letsencrypt/live/yourdomain.com` | `fullchain.pem`, `privkey.pem` |
| Other (Caddy, Traefik, acme.sh, a company CA) | the folder where the program saves the files | the names it uses, for example `cert.pem` and `key.pem` |

The number in `npm-3` is different on every installation: look at which folder is inside `live/` on the NPM machine. To find where NPM keeps its data:
`docker inspect CONTAINER-NAME --format '{{ range .Mounts }}{{ .Source }} -> {{ .Destination }}{{ println }}{{ end }}'` (look for the one ending in `/etc/letsencrypt`).

### 5.3 Step by step: a user that can only read

The certificate is a secret (the private key above all). That is why the script does **not** use an administrator's account: if its ssh key were
stolen, the thief would get into the NPM machine with full powers. Instead, you create a separate user that can only read the certificates.

In the example the NPM machine is called `npm.lan`, the PrintMinder one `print.lan` (IP `192.168.1.50`), the user is called `certsync`.

**Step 1 — on `npm.lan`: create the user** (no password: it is entered only with the key).

```sh
sudo adduser --disabled-password --gecos "" certsync
sudo apt install rsync acl          # if missing: rsync does the copying, acl is for the permissions of step 4
```

**Step 2 — on `print.lan`: create the ssh key** (as your own user, the one that will run cron).
`rsync` and `ssh` are needed on this machine too (`sudo apt install rsync openssh-client` if missing).

```sh
ssh-keygen -t ed25519 -N "" -C "printminder cert-sync" -f ~/.ssh/printminder_certsync
cat ~/.ssh/printminder_certsync.pub          # one line starting with ssh-ed25519: we use it in step 3
```

The private key (`printminder_certsync`, without `.pub`) must not leave this machine. Its full path (for example `/home/you/.ssh/printminder_certsync`)
goes into `CERT_SYNC_KEY`.

**Step 3 — on `npm.lan`: authorise the key, with limits.** Replace `192.168.1.50` with the IP of `print.lan` and the `ssh-ed25519 AAAA…` part with the line printed in step 2.

```sh
sudo -u certsync mkdir -p -m 700 /home/certsync/.ssh
echo 'restrict,from="192.168.1.50" ssh-ed25519 AAAA… printminder cert-sync' | sudo -u certsync tee -a /home/certsync/.ssh/authorized_keys
sudo chmod 600 /home/certsync/.ssh/authorized_keys
```

The two words in front of the key are the limits: `from="192.168.1.50"` makes the key work **only** from `print.lan`; `restrict` removes everything else
(no port forwarding, no interactive terminal, no ssh agent).

**Step 4 — on `npm.lan`: give the user permission to read the certificates, and nothing else.** With ACLs (permissions for one particular user) you grant read access to one folder.
Example for NPM, with the data in `/home/you/npm/data`:

```sh
# the user must be able to "walk through" the folders above (x) and read (r) the ones with the certificates
sudo setfacl -m u:certsync:x /home/you /home/you/npm /home/you/npm/data
sudo setfacl -R -m u:certsync:rX /home/you/npm/data/letsencrypt
sudo setfacl -R -d -m u:certsync:rX /home/you/npm/data/letsencrypt    # also valid for the files created at the next renewals
```

For certbot: `sudo setfacl -R -m u:certsync:rX /etc/letsencrypt` (and the same line with `-d`).

If your disk does not support ACLs (`setfacl` answers "Operation not supported"), the alternative is to create a group that can read the folder and add `certsync` to that group.

Check that it works and that it is really read-only:

```sh
sudo -u certsync head -1 /home/you/npm/data/letsencrypt/live/npm-3/fullchain.pem     # must print -----BEGIN CERTIFICATE-----
sudo -u certsync touch /home/you/npm/data/letsencrypt/live/npm-3/test                 # must answer: Permission denied
```

**Step 5 — on `print.lan`: write the settings in `.env`.**

```sh
CERT_SYNC_HOST=npm.lan
CERT_SYNC_USER=certsync
CERT_SYNC_KEY=/home/you/.ssh/printminder_certsync
CERT_SYNC_REMOTE_DIR=/home/you/npm/data/letsencrypt/live/npm-3
```

**Step 6 — on `print.lan`: try it.** First without changing anything:

```sh
scripts/cert-sync.sh --dry-run
```

The first time, ssh remembers the fingerprint of `npm.lan` (in the file `config/ssh/known_hosts`) and checks it on every later run: if one day that fingerprint changes, the script
refuses to connect (it is the sign that someone is pretending to be `npm.lan`). If all is well it says "a new certificate is available" or "already up to date".
Then the real test: `scripts/cert-sync.sh`. Open the portal: no notice about the certificate, and if the certificate had changed the gateway has restarted.

**Step 7 — on `print.lan`: put it in cron.** As your own user (it must be able to use `docker`):

```sh
crontab -e
```

and add a line (change the path of the PrintMinder folder):

```
17 4 * * *  cd /home/you/printminder && scripts/cert-sync.sh >> data/cert-sync.log 2>&1
```

It reads like this: every day (`* * *`) at 4:17 (`17 4`), go to the folder and run the script, writing what it says to `data/cert-sync.log`. Once a day is enough:
if the certificate has not changed nothing happens and nothing restarts.

### 5.4 If something goes wrong

The message appears in the portal (bell) and in `data/cert-sync.log`. To see it right away: `scripts/cert-sync.sh --dry-run`.

| Message | What it means and what to do |
|---|---|
| `set CERT_SYNC_HOST, CERT_SYNC_USER, CERT_SYNC_KEY and CERT_SYNC_REMOTE_DIR in .env` | One of the four required settings is missing. |
| `the ssh key … does not exist or can not be read by this user` | The path in `CERT_SYNC_KEY` is wrong or the file belongs to another user. It must be the full path. |
| `could not download … Permission denied (publickey)` | The public key is not in the remote user's `authorized_keys`, or `from=` does not match this machine's IP. Redo step 3. |
| `could not download … REMOTE HOST IDENTIFICATION HAS CHANGED` | The fingerprint of the remote machine changed (reinstalled, or someone is pretending to be it). If you know why, delete its line from `config/ssh/known_hosts`. |
| `could not download … No such file or directory` | `CERT_SYNC_REMOTE_DIR` or the file names are wrong (the `npm-3` number, for example). |
| `could not download … Permission denied` (without `publickey`) | The remote user is not allowed to read: redo step 4. |
| `the certificate on … is already expired: it was not installed` | The source still has an expired certificate: the problem is there, find out why it does not renew. |
| `the private key … does not belong to the certificate …: nothing was installed` | The key file and the certificate file are not the same pair (wrong names, or a renewal half done). The files in use were not touched. |
| `the new certificate is installed but the gateway did not restart` | The new certificate is in place, but `docker compose restart gateway` failed: run it by hand and look at `docker compose logs gateway`. If cron cannot use docker, add its user to the `docker` group. |

To go back to the previous pair: copy the two files of `config/tls/previous/` to `config/tls/` and run `docker compose restart gateway`.

### 5.5 What the script does not do

- It does not **renew** the certificate: it copies it from whoever renews it. If the renewal fails at the source, the old one keeps arriving here; to notice, turn on the "about to expire" notice (§2).
- It does not change the names in the certificate: if the address the gateway announces is missing, the notice says so, but the certificate must be reissued at the source.
- It does not touch the devices' CA (§3).
- It does not use `rrsync` to restrict the key further: `rrsync` refuses to follow symbolic links, and both Nginx Proxy Manager and certbot keep links in `live/` that point into `archive/`.
  The limits here are those of step 3 (`restrict`, `from=`) and of step 4 (read-only, on the certificates only).
