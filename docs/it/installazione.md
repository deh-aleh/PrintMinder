# Guida all'installazione

[Indice della documentazione](../README.md) · [English](../en/installation.md) · Italiano

Due modi per installare PrintMinder:

- **Docker (consigliato)** — tutto gira in contenitori (`ipp-usb`, CUPS, gateway, mDNS). Sull'host non si installa né si modifica nulla.
- **Installazione sull'host (avanzata)** — un servizio systemd più un CUPS di sistema riconfigurato. Modifica
  `/etc/cups/cupsd.conf`: usala solo se sai perché.

Problemi? Vedi [risoluzione-problemi.md](risoluzione-problemi.md).

## 1. Requisiti

| | |
|---|---|
| Server | Macchina **Linux** (ideale un mini-PC o un Raspberry Pi). Il passaggio USB e la rete `host` usata da mDNS esistono solo su Linux; su Docker Desktop (Windows, macOS) il gateway parte ma funzionano solo le stampanti **di rete** e i telefoni non le trovano da soli. |
| Software | Docker Engine con il plugin Compose (`docker compose version`), `openssl`, `curl` e `tar` (li usano gli script), `python3` (lo usa `scripts/backup.sh`). Non serve `git`: l'installazione parte dal pacchetto della release. |
| Stampante | USB (tramite `ipp-usb`) o di rete (IPP). Qualunque cosa CUPS sappia pilotare. |
| Rete | Una porta TCP raggiungibile dai client (predefinita **8631**; `631` se nessun altro CUPS la usa). I client devono fidarsi del certificato (vedi §3.4) |
| Architettura | **amd64** (PC, server) e **arm64** (Raspberry Pi 4/5, NAS ARM). Le immagini pubblicate contengono entrambe e Docker sceglie quella giusta. ARM a 32 bit (armv7) non è supportato |
| Un gateway per stampante USB | `ipp-usb` vuole il dispositivo in esclusiva: vedi §5 |

## 2. Percorso rapido (Docker)

```sh
# 0. scarica il pacchetto. Scrivi in VERSION l'ultima versione: la trovi in https://github.com/deh-aleh/PrintMinder/releases
VERSION=1.0.0
curl -LO https://github.com/deh-aleh/PrintMinder/releases/download/v$VERSION/printminder-$VERSION.tar.gz
curl -LO https://github.com/deh-aleh/PrintMinder/releases/download/v$VERSION/SHA256SUMS
sha256sum -c --ignore-missing SHA256SUMS            # deve rispondere «OK»: il file è quello pubblicato
tar xzf printminder-$VERSION.tar.gz && cd printminder-$VERSION

# 1. nomi / IP con cui i client raggiungeranno il server (finiscono nel certificato TLS)
scripts/docker-init.sh print.lan 192.168.1.50

# 2. impostazioni (RADIUS è facoltativo: lascia host e secret vuoti per usare solo account locali)
$EDITOR .env

# 3. stampanti: vedi §5 (USB) e §6 (rete); poi avvia
docker compose up -d

# 4. leggi il codice monouso e scegli la password dell'amministratore
docker compose logs gateway | grep "FIRST RUN"
#    apri https://<server>:8631/admin/setup
```

L'account amministratore è `cups_orchestrator`. Da terminale si ottiene lo stesso con
`docker compose exec -it gateway cups-policy-admin set-admin-password`.

## 3. Passo per passo

### 3.1 Preparazione

`scripts/docker-init.sh [nome-o-IP ...]` scrive **solo dentro la cartella del progetto**:

| Creato | Cosa |
|---|---|
| `.env` | **tutte** le impostazioni in un solo file. La parte A è per compose: `PRINTGW_REGISTRY`/`PRINTGW_VERSION` (quali immagini pubblicate girano), `PUID`/`PGID` (il tuo utente), `PROJECT_DIR`, `GATEWAY_PORT`, `CUPS_QUEUES`, `CUPS_VIRTUAL_QUEUE`, percorsi sull'host. La parte B sono le impostazioni del programma `CUPSPL_*`, con una `CUPSPL_SECRET_KEY` appena generata. Permessi 600 (contiene segreti) |
| `config/tls/` | un certificato autofirmato (825 giorni) i cui nomi alternativi sono i nomi/IP indicati |
| `data/audit-archive/`, `data/backups/` | cartelle sull'host per l'audit compresso e i backup |

Rieseguirlo non sovrascrive mai file esistenti. Non condividere `config/` né `.env`: contengono segreti.

**Non modificare mai `docker-compose.yml`**: tutto quello che puoi cambiare sta in `.env`. Così un aggiornamento può sostituire il compose senza cancellare le tue scelte.

### 3.2 Le impostazioni del programma (parte B di `.env`)

I valori predefiniti sono ragionevoli; le impostazioni che toccherai più spesso:

| Impostazione | Quando |
|---|---|
| `CUPSPL_RADIUS_HOST`, `CUPSPL_RADIUS_SECRET` | Vuoi gli accessi con le credenziali d'ufficio (RADIUS). Registra questa macchina come *client* RADIUS con lo stesso secret. Compila entrambi o nessuno. |
| `CUPSPL_PORTAL_URL` | Scrivi `https://print.lan:8631` perché i messaggi inviati ai client di stampa contengano il link giusto |
| `CUPSPL_TIMEZONE` | Settimane/mesi delle quote e orari mostrati la seguono (predefinito `UTC`: imposta il tuo, per esempio `Europe/Rome`) |
| `CUPSPL_LANGUAGE` | Lingua predefinita del portale (`en`, `it`, `es`, `ru`, `zh`) |
| `CUPSPL_MDNS_HOSTNAME` | Se il nome della macchina non è nel certificato |
| `CUPSPL_BACKUP_*` | Il backup generale programmato (vedi [backup.md](backup.md)) |
| `CUPSPL_HEALTHZ_INFO` | Cosa mostra `/healthz` oltre allo stato (niente, di default): `version`, `printers` |
| `CUPSPL_UPDATE_CHECK` | `false` ferma la domanda giornaliera a GitHub su una versione più nuova |
| `CUPSPL_ESCL_ANONYMOUS` | `true` accetta le scansioni dalle app che non sanno inviare una password (vedi [scansione.md](scansione.md)) |

Il file è interamente commentato. Dopo ogni modifica: `docker compose up -d`.

Se il valore ha spazi, `$` o `#`, mettilo tra apici singoli, per esempio `CUPSPL_RADIUS_SECRET='il$mio #secret'`: senza apici compose legge il `$` come l'inizio di una variabile.

### 3.3 Le variabili di compose (parte A di `.env`)

Sempre in `.env`, modifica per le code delle stampanti (`CUPS_QUEUES`), la porta pubblicata (`GATEWAY_PORT=631` per prendere la porta 631),
l'utente (`PUID`/`PGID`) e, per le immagini scaricate, `PRINTGW_REGISTRY` + `PRINTGW_VERSION` (in produzione fissa una versione, mai `latest`).

### 3.4 Certificato TLS

Il TLS è **obbligatorio**: senza, il gateway non parte.

- Il certificato generato è autofirmato. Installalo come attendibile su ogni client, **oppure**
- metti `fullchain.pem` e `privkey.pem` firmati dalla tua CA in `config/tls/` (la chiave deve essere leggibile dall'utente `PUID`) ed
  esegui `docker compose restart gateway`.

Il certificato deve elencare i nomi/IP usati dai client, compreso l'IP annunciato da mDNS. Se non è così, il portale lo dice con un avviso (la campanella): vedi [certificati.md](certificati.md).

**Hai già un certificato valido (per esempio emesso da Nginx Proxy Manager su un'altra macchina).** Il modo più semplice è far usare quello stesso
certificato direttamente al gateway, senza proxy in mezzo:

1. Fai in modo che un nome coperto da quel certificato (diciamo `print.example.com`) risolva verso il server dentro la tua rete (record nel DNS
   locale o nel router).
2. Copia la coppia dalla macchina che la tiene (NPM: `data/letsencrypt/live/npm-<n>/fullchain.pem` e `privkey.pem`; certificati personalizzati:
   `data/custom_ssl/npm-<n>/`) in `config/tls/fullchain.pem` e `config/tls/privkey.pem`, rendi la chiave leggibile dall'utente `PUID`
   (`chmod 600`) ed esegui `docker compose restart gateway`.
3. Imposta `CUPSPL_PORTAL_URL=https://print.example.com:8631` in `.env` e usa `ipps://print.example.com:8631/printers/<coda>`.
4. I certificati Let's Encrypt si rinnovano ogni circa 60 giorni. Per non copiarli a mano ogni volta usa `scripts/cert-sync.sh` da cron: copia i
   due file, li controlla e riavvia il gateway solo se sono cambiati. È spiegato passo per passo, compresa la creazione di un utente che può
   solo leggere, in [certificati.md](certificati.md).

I dispositivi che trovano le stampanti con mDNS ricevono il nome `<nome>.local` o l'IP, che un certificato per `print.example.com` non copre:
su quei dispositivi usa a mano il nome vero, oppure ferma il servizio `mdns` se non ti serve la scoperta.

*Dietro un reverse proxy invece* (il proxy tiene il certificato e inoltra a `https://<server>:8631`; non provato dal progetto): il proxy deve
inoltrare con schema `https`, accettare corpi grandi e non metterli in buffer (`client_max_body_size 250m; proxy_request_buffering off;
proxy_read_timeout 600s;`), e il gateway vede ogni client con l'indirizzo del proxy (blocco dei login per indirizzo, IP nell'audit) a meno che in
`.env` sia impostato `FORWARDED_ALLOW_IPS=<indirizzo del proxy>`, così uvicorn si fida di `X-Forwarded-For`. Gli indirizzi delle
stampanti restituiti ai client portano l'`Host` inoltrato dal proxy, senza `:443`, quindi i dispositivi devono tenere l'indirizzo con cui sono
stati configurati.

### 3.5 Avvio

```sh
docker compose up -d --build          # costruisce dal sorgente
# oppure, con immagini pubblicate (imposta PRINTGW_REGISTRY e PRINTGW_VERSION in .env):
docker compose pull && docker compose up -d
```

Verifica: `curl -sk https://<server>:8631/healthz` risponde 200; `docker compose ps` mostra `cups` in stato healthy.

### 3.6 Primo amministratore

`docker compose logs gateway | grep "FIRST RUN"` mostra un codice monouso. Apri `https://<server>:8631/admin/setup`, inserisci il
codice e scegli la password di `cups_orchestrator` (minimo 12 caratteri). Il codice vale una volta sola ed è protetto dai tentativi a caso.
Se non compare nulla, probabilmente l'account ha già una password (questa cartella è già stata usata e il volume Docker ha tenuto il database): il log dice allora "already has a password"; accedi, oppure reimposta con `docker compose exec -it gateway cups-policy-admin set-admin-password`. Altre cause: [risoluzione-problemi.md](risoluzione-problemi.md).

### 3.7 Primi utenti

Nel portale (**Utenti**) crea utenti locali, oppure lascia entrare gli utenti RADIUS (al primo accesso vengono creati nel gruppo
predefinito). In **Gruppi** imposta i limiti. Ogni utente crea poi una **chiave di stampa** in *Profilo* e la usa come password
quando un computer o un telefono chiede le credenziali. Vedi [guida-utente.md](guida-utente.md) e [guida-amministratore.md](guida-amministratore.md).

## 4. Collegare i dispositivi

| Dispositivo | Come |
|---|---|
| Qualunque telefono / computer | Portale → **Stampa** (`/me/print`): carica PDF, JPEG, PNG, GIF o testo. Nulla da installare. |
| Linux | Dopo aver creato una chiave la pagina del profilo mostra un comando `lpadmin` già pronto; oppure `scripts/add-printer-linux.sh <server> <coda> <utente>`. |
| Android | **Mopria Print Service** trova le stampanti e chiede nome e chiave. Il servizio di stampa di sistema di Android non sa autenticarsi. |
| Windows, macOS, iPhone | Aggiungi una stampante di rete `ipps://<server>:8631/printers/<coda>`; quando richiesto inserisci nome utente e chiave. Non ancora provato dal progetto. |

Il dispositivo deve fidarsi del certificato. Dettagli in [stampa.md](stampa.md).

## 5. Stampante USB

**Le stampanti USB nuove si aggiungono da sole** (entro circa un minuto): collega la stampante e compare nella pagina Stampanti. Se ha
l'IPP-su-USB la serve `ipp-usb`; se no (molte laser vecchie) la usa direttamente il contenitore `cups`, che ha bisogno di un driver — l'immagine
include brlaser, gutenprint, splix e foo2zjs (altri si aggiungono in `docker/stack/cups/Dockerfile`). `CUPS_QUEUES` serve solo per dare un nome
fisso a una coda; una coda indicata lì viene creata una sola volta e, se la elimini dopo (o se il gateway toglie una stampante USB scollegata), resta eliminata. Per rimetterla: `scripts/queue-restore.sh NOME --reboot`. Vedi [stampanti.md](stampanti.md#2-stampanti-usb-nuove-e-scollegate).

`ipp-usb` ha bisogno dell'uso esclusivo della stampante. Se è installato sull'host, fermalo e mascheralo (vale anche per SANE):

```sh
sudo systemctl disable --now ipp-usb && sudo systemctl mask ipp-usb
```

Poi in `.env`:

```
CUPS_QUEUES=HP7305=ipp://ipp-usb:60000/ipp/print
```

e `docker compose up -d`. La coda viene creata da sola appena la stampante risponde (si riprova per 5 minuti).
Altre stampanti: `docker compose exec cups lpadmin -p NOME -E -v ipp://ipp-usb:600NN/ipp/print -m everywhere`
(la porta di ciascuna la mostra `docker compose logs ipp-usb`). Collegando o scollegando una stampante `ipp-usb` si riavvia da solo
entro qualche secondo.

## 6. Stampante di rete

Dai a `CUPS_QUEUES` l'indirizzo IPP della stampante: `CUPS_QUEUES="UFFICIO=ipp://192.168.1.60/ipp/print"` (più code si separano con
spazi). Gli scanner che rispondono a eSCL sulla porta IPP della stampante (o sulla 80) si trovano da soli; altrimenti elencali in `CUPSPL_SCAN_URL`.

## 7. Provare senza stampante e senza RADIUS

```sh
# in .env:  CUPS_VIRTUAL_QUEUE=1   CUPSPL_RADIUS_HOST=radius   CUPSPL_RADIUS_SECRET=testing123
docker compose --profile radius-test up -d --build
```

Crea la coda `virtual` (scrive PDF, nessuna carta) e un RADIUS di prova con `mario/mario123`, `anna/anna123`, `admin/admin123`.
Esempio: `ipptool -t -f file.txt "ipps://mario:mario123@localhost:8631/printers/virtual" job.test`.
I PDF sono in `docker compose exec cups ls /var/spool/cups-pdf/ANONYMOUS`. Dalla pagina Stampanti puoi anche creare **stampanti di prova**.
Non lasciare account di prova su un'installazione vera.

## 8. Aggiornare, salvare, spostare

- **Aggiornamento** — vedi «Aggiornamenti» più sotto.
- **Backup**: il menu *Backup* del portale ([backup.md](backup.md)); `scripts/backup.sh backup` per una copia completa lato host
  (database, configurazione, archivio audit, code CUPS, `.env`) da usare per spostare la macchina.
- **Log**: `docker compose logs gateway`. **Salute**: `GET /healthz`.

### Aggiornamenti

Le immagini sono pubblicate a ogni release (`ghcr.io/deh-aleh/{gateway,cups,ipp-usb,updater}:<versione>`, amd64 + arm64) e `.env`
contiene la versione in uso (`PRINTGW_VERSION`). La versione cambia solo **di proposito**: niente si aggiorna da solo. Le migrazioni
del database partono all'avvio.

Ogni release ha anche un **pacchetto** (`printminder-<versione>.tar.gz` con il suo `SHA256SUMS`) che contiene `docker-compose.yml`, gli script,
`docker/env.example` e la documentazione. Non contiene mai `.env`, `config/` né `data/`: un aggiornamento non può toccarli.

| Come | Quando |
|---|---|
| `scripts/update.sh` | **Via normale.** Fa un backup completo (`data/backups/pre-update/`), scarica il pacchetto della nuova versione e ne controlla la somma sha256, sostituisce `docker-compose.yml` e gli script (i vecchi restano in `.update-prev/`), scrive la nuova versione in `.env`, scarica le immagini, riavvia e aspetta che il gateway sia in salute. Se non lo è, rimette i file e la versione di prima; se nemmeno la versione di prima parte (la nuova ha già cambiato il database), ti propone di ripristinare il backup appena fatto. `scripts/update.sh 1.2.0` sceglie una versione; `--check` dice solo se ne esiste una più nuova. Il cambio di versione maggiore (1.x → 2.x) chiede conferma: leggi prima le note di rilascio. |
| Pulsante *Aggiorna* nel portale | Facoltativo. Menu *Backup*, riquadro *Aggiornamento*. Richiede il contenitore `updater` (sotto) **e** un backup programmato attivo e riuscito nelle ultime 48 h: si fa un backup fresco, poi parte l'aggiornamento. Senza un backup programmato funzionante il pulsante resta spento e dice perché. Solo aggiornamenti dentro la stessa versione maggiore. Se la nuova versione non parte rimette quella vecchia, ma il ripristino del backup, se serve, lo fai tu dal menu *Backup* o con `scripts/backup.sh restore`. |
| `git pull && docker compose up -d --build` | Solo in una cartella clonata con git (sviluppo) e per le immagini costruite da te (`PRINTGW_REGISTRY` vuoto in `.env`). `scripts/update.sh` in una cartella con `.git` si rifiuta di partire, per non litigare con git. |

**Esempio.** Sei alla 1.0.0 e esce la 1.1.0 che cambia `docker-compose.yml` (un volume nuovo). Lanci `scripts/update.sh`: il compose nuovo arriva
insieme alle immagini nuove, quindi non c'è il rischio di avere immagini 1.1.0 con un compose 1.0.0. Il tuo `.env` resta com'era.

**Avviso di nuova versione.** Una volta al giorno il gateway chiede a GitHub qual è l'ultima release e mostra un avviso agli
amministratori. Esce solo quella richiesta e non invia nulla del tuo server. Si spegne con `CUPSPL_UPDATE_CHECK=false`.

**Il contenitore facoltativo `updater`** applica gli aggiornamenti chiesti dal portale. È **spento di default** perché usa il socket
di Docker (`/var/run/docker.sock`), e chi controlla quel socket controlla tutta la macchina (root): se qualcuno trovasse un difetto
nel portale e riuscisse a usarlo, potrebbe comandare Docker e prendere il server. Legge solo un numero di versione `x.y.z` scritto dal gateway;
le immagini arrivano sempre dal registry del tuo `.env`. Per accenderlo:

```sh
echo "COMPOSE_PROFILES=autoupdate" >> .env      # una riga in .env (oppure aggiungi --profile autoupdate ogni volta)
docker compose up -d
```

Se non vuoi quel rischio, lascialo spento e usa `scripts/update.sh`. Per spegnerlo di nuovo: togli la riga da `.env` e `docker compose stop updater`.

**Opzioni nuove nelle versioni successive.** Il tuo `.env` non viene mai modificato da un aggiornamento. Un'opzione nuova funziona subito con il suo valore
predefinito anche se nel tuo `.env` non c'è. Per vedere quali opzioni ci sono, apri `docker/env.example` (lo sostituisce ogni aggiornamento): ogni opzione
ha la sua spiegazione. Se ne vuoi cambiare una, copia la riga nel tuo `.env` e lancia `docker compose up -d`.

**Blocca la versione.** Non usare mai `latest`: lascia `PRINTGW_VERSION` a un numero, così l'aggiornamento è una decisione.

## 9. Alternativa: installazione sull'host (senza docker)

> Questo **modifica il sistema**: crea l'utente `cupspl`, file in `/opt` e `/etc`, un'unità systemd e sostituisce
> `/etc/cups/cupsd.conf` (l'originale resta salvato come `cupsd.conf.pre-gateway`).

```sh
sudo sh deploy/install.sh                 # utente, venv in /opt/cups-policy-gateway, /etc/cups-policy-gateway/env, unità systemd
sudoedit /etc/cups-policy-gateway/env     # RADIUS (facoltativo), percorsi TLS, …; metti il certificato in /etc/cups-policy-gateway/tls
sudo sh deploy/setup-cups.sh              # rende CUPS un backend privato (socket unix, nessun TCP); --revert per tornare indietro
sudo systemctl enable --now cups-policy-gateway
journalctl -u cups-policy-gateway | grep "FIRST RUN"
```

Serve Python ≥ 3.12 con `venv`. Il servizio gira come `cupspl`, isolato, e usa la porta 631 grazie a `CAP_NET_BIND_SERVICE`.
`deploy/env.example` elenca le impostazioni. L'annunciatore mDNS è un processo a parte (`python -m app.mdns`) che devi avviare tu se lo vuoi.

## 10. Sviluppo

```sh
pip install -e '.[dev]'
docker compose -f docker-compose.test.yml up -d --build   # CUPS di test su :6310 e FreeRADIUS su :1812
pytest                                                    # i test che richiedono docker si saltano da soli se è spento
```
