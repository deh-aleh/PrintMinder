# Riferimento della configurazione (`.env`)

[Indice della documentazione](../README.md) · [English](../en/configuration.md) · Italiano

Tutte le impostazioni di PrintMinder stanno in un solo file, `.env`, nella cartella del progetto. `scripts/docker-init.sh` lo crea da
[`docker/env.example`](../../docker/env.example) e imposta i permessi 600 (contiene segreti). Questa pagina elenca **tutte** le variabili.
L'elenco ufficiale, con i valori predefiniti, è [`app/config.py`](../../app/config.py); un test controlla che ogni impostazione che c'è lì sia
descritta qui.

Come leggere la pagina:

- **Predefinito** è il valore usato quando la variabile manca o è scritta vuota (`NOME=`). Scrivi solo le righe che vuoi cambiare.
- **Dopo ogni modifica** esegui `docker compose up -d` nella cartella del progetto: ricrea i contenitori che leggono `.env`. Le
  impostazioni sono lette una volta sola, all'avvio del programma, quindi prima non hanno effetto. Non serve altro (non modificare mai
  `docker-compose.yml`).
- Un valore con spazi, `$` o `#` va tra apici singoli: `CUPSPL_RADIUS_SECRET='my$secret #1'`.
- `true` / `false` sono i valori delle impostazioni acceso/spento (vanno bene anche `1` / `0`).
- Un numero che non è un numero (`CUPSPL_BACKUP_HOUR=notte`) ferma il gateway all'avvio con un errore in `docker compose logs gateway`:
  l'errore ti dice di correggere quella riga.
- Un aggiornamento non cambia mai il tuo `.env`. Una versione nuova può portare impostazioni nuove: funzionano con il loro valore
  predefinito anche se non sono nel tuo file; `docker/env.example` (sostituito a ogni aggiornamento) le mostra con la spiegazione.
- I due contenitori `gateway` e `mdns` leggono lo stesso file. Le impostazioni che interessano l'annuncio in rete sono indicate nel testo.

Il file ha due parti. La **parte A** la legge docker compose (quale versione, quale utente, quale porta). La **parte B** la legge il
programma e ogni variabile inizia con `CUPSPL_`. L'installazione sull'host senza docker usa `/etc/cups-policy-gateway/env` con gli stessi
nomi `CUPSPL_*` (vedi [installazione.md](installazione.md)).

## 1. La chiave segreta

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_SECRET_KEY` | creata da `docker-init.sh` | Un testo casuale e lungo che conosce solo questo server. Vedi sotto. |

Serve a tre cose:

- **cifra i nomi dei file** conservati nell'audit ([protezione-dati.md](protezione-dati.md));
- **firma la sessione del portale** (il cookie che dice chi ha fatto il login);
- **protegge il canale** tra `gateway` e `mdns` (cosa può pubblicare l'annunciatore).

Non cifra il resto del database e non è la password di nessuno: non la scrivi mai a mano.

**Tieni una copia fuori dal server** (va bene un password manager). Un backup non cifrato **non** la contiene, apposta. Se viene cambiata o
persa, i nomi dei file già salvati compaiono come `[encrypted]` per sempre (utenti, quote, pagine e date non sono toccati) e tutti devono
rifare il login. Se è vuota, il gateway ne crea una nuova a ogni avvio: le sessioni finiscono a ogni riavvio, il canale verso `mdns` non è
protetto e i nomi sono salvati senza cifratura. In produzione impostala sempre. Il portale avvisa gli amministratori nella campanella in
questi casi. Come salvarla e cosa fa un backup cifrato: [backup.md](backup.md#salva-la-chiave-segreta).

Per crearne una a mano: `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Non condividerla e non metterla mai in un
repository git: ogni installazione ha la sua.

## 2. Account e accesso

### RADIUS (facoltativo)

RADIUS permette di entrare con la password dell'ufficio. Con `CUPSPL_RADIUS_HOST` e `CUPSPL_RADIUS_SECRET` entrambi vuoti esistono solo
account locali. Se ne compili uno solo, il gateway **non parte** (un sistema di accesso a metà è peggio di nessuno). Il server RADIUS deve
elencare questa macchina come client, con lo stesso segreto. Se RADIUS non risponde, l'accesso è **negato** (fallisce chiuso).

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_RADIUS_HOST` | vuoto | Nome o indirizzo del server RADIUS. Esempio: `radius.ufficio.lan` |
| `CUPSPL_RADIUS_PORT` | `1812` | Porta UDP del server. Cambiala solo se la tua è diversa. |
| `CUPSPL_RADIUS_SECRET` | vuoto | Segreto condiviso con il server (non è la password di un utente). Metti gli apici se contiene `$` o `#`. |
| `CUPSPL_RADIUS_TIMEOUT` | `5` | Secondi di attesa della risposta. Alzalo per un server lento o lontano. |
| `CUPSPL_AUTH_CACHE_SECONDS` | `60` | Un accesso riuscito viene ricordato per questo tempo, così il server non è interpellato a ogni richiesta. |

### Autenticazione di stampa e chiavi

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_IPP_AUTH` | `keys` | Cosa può presentare come password un **client di stampa** (computer, telefono). `keys` = solo le chiavi di stampa personali (consigliato: la password dell'ufficio non viene mai salvata su un dispositivo e una chiave persa si revoca). `keys+radius` = anche la password RADIUS, solo per un periodo di transizione. Per il portale web serve sempre la password. |
| `CUPSPL_KEY_TTL_DAYS_RADIUS` | `90` | La durata **massima** che un utente RADIUS può scegliere per una chiave di stampa, in giorni (il menu mostra solo le scelte che ci stanno). Breve apposta: per rinnovarla deve rifare il login RADIUS, così chi lascia l'azienda smette di stampare quando la chiave scade. |
| `CUPSPL_KEY_TTL_DAYS_LOCAL` | `730` | Lo stesso, per gli account locali. |
| `CUPSPL_KEY_ONCE_HOURS` | `24` | Una chiave "una sola stampa" che nessuno usa smette di funzionare dopo queste ore. |
| `CUPSPL_KEY_ONCE_GRACE_SECONDS` | `120` | Dopo la sua stampa, una chiave monouso può ancora rispondere a "come va il mio lavoro?" per questo tempo (lo chiedono telefoni e PC). |
| `CUPSPL_KEY_HISTORY_DAYS` | `14` | Le chiavi revocate e scadute spariscono dall'elenco dopo questi giorni dalla fine. `0` = restano per sempre. |
| `CUPSPL_KEY_EXPIRY_WARN_ENABLED` | `false` | `true` avvisa il proprietario nella campanella prima che una chiave scada. |
| `CUPSPL_KEY_EXPIRY_WARN_DAYS` | `7` | Quanti giorni prima della fine compare l'avviso (solo se la riga sopra è attiva). |
| `CUPSPL_AUTO_CREATE_USERS` | `true` | Un utente RADIUS sconosciuto che entra nel portale viene creato nel gruppo predefinito. `false` = prima registra gli utenti; chi non è in elenco non entra. |
| `CUPSPL_DEFAULT_GROUP` | `default` | Il gruppo dei nuovi utenti e dove finiscono gli utenti quando il loro gruppo viene eliminato. |
| `CUPSPL_CUPS_USER_PREFIX` | `gw:` | Messo davanti al nome utente che vede CUPS (`gw:mario`). Non può coincidere con un account locale del server, così un utente RADIUS chiamato `root` non diventa amministratore di CUPS. Non cambiarlo senza un motivo. |
| `CUPSPL_ANONYMOUS_DISCOVERY` | `true` | Risponde a "che stampante sei?" senza login. I client IPP Everywhere (Linux, Android, macOS) lo chiedono alla stampante prima di avere le credenziali. Non permette di stampare e non mostra nomi o documenti. Metti `false` solo se sai che i tuoi client non ne hanno bisogno. |

### Primo avvio

Al primo avvio esiste un amministratore di emergenza **senza password**. Il gateway scrive nel log un codice monouso; con quello scegli la
password su `https://<server>:8631/admin/setup` (vedi [installazione.md](installazione.md)). Il codice funziona una volta sola.

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_BOOTSTRAP_ADMIN` | `true` | Crea quell'account quando non c'è nessun amministratore. |
| `CUPSPL_BOOTSTRAP_ADMIN_USERNAME` | `cups_orchestrator` | Il suo nome. È anche la persona che riceve il promemoria per salvare la chiave segreta. |

### Richieste di più quota

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_MAX_OPEN_REQUESTS` | `3` | Quante richieste può avere aperte insieme un utente. |
| `CUPSPL_REQUEST_TTL_DAYS` | `14` | Dopo quanti giorni scade una richiesta a cui nessuno ha risposto. |
| `CUPSPL_REQUEST_REASON_REQUIRED` | `false` | `true` = chi chiede quota, un permesso o un cambio di gruppo deve scrivere un motivo; `false` = il motivo è facoltativo. |

### Permessi avanzati

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_PERMISSION_MODE` | `adjust` | Cosa succede quando un programma chiede **in modo esplicito** il colore, o una stampa solo fronte, che l'utente non può avere. `adjust`: il lavoro esce in bianco e nero / in fronte-retro e all'utente arriva un avviso. `refuse`: il lavoro viene rifiutato. Stampanti e orari rifiutano sempre. Un programma che non ha chiesto nulla viene corretto senza avviso in entrambe le modalità. Windows e Android chiedono spesso solo fronte o colore in ogni lavoro, quindi con `refuse` molti loro lavori vengono rifiutati ([quote.md](quote.md#5-permessi-avanzati)). Qualsiasi altro valore ferma il gateway all'avvio. |

### Accessi falliti

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_LOCKOUT_FILE` | `/data/login-lockout.json` | Gli accessi falliti sono contati per indirizzo e conservati in questo file dentro il contenitore (il volume `/data`), così un riavvio non annulla un blocco. Vuoto = solo in memoria. Con docker lascialo com'è; l'installazione sull'host (senza docker) imposta `/var/lib/cups-policy-gateway/login-lockout.json` nel suo `deploy/env.example`. |

## 3. Audit e nomi dei file

L'audit non si cancella mai dal portale. Quando le tabelle attive superano il limite qui sotto, le righe più vecchie vengono scritte in file
compressi, controllate e solo dopo tolte dal database ([audit.md](audit.md)).

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_AUDIT_MAX_MB` | `50` | Dimensione dell'audit attivo che fa partire l'archiviazione. Alzala per un database più grande, abbassala per archiviare prima. |
| `CUPSPL_AUDIT_ARCHIVE_DIR` | `/data/audit-archive` | Cartella dei file compressi **dentro il contenitore**. Il file compose la collega a `./data/audit-archive` sull'host: cambia quel collegamento, non questa riga. |
| `CUPSPL_AUDIT_ARCHIVE_HOST_PATH` | impostata dall'init | Solo **mostrata** nel portale, perché si sappia dove sono i file su questa macchina. Si riempie da `AUDIT_ARCHIVE_HOST_PATH` della parte A. |
| `CUPSPL_AUDIT_CHECK_INTERVAL` | `3600` | Secondi tra i controlli "serve archiviare?" |
| `CUPSPL_JOB_TITLE_RETENTION_ENABLED` | `false` | `true` cancella i nomi dei file stampati dopo i giorni qui sotto. La riga (chi, quando, pagine, stato) resta, perché serve alle quote. I nomi già dentro i file d'archivio non vengono toccati. |
| `CUPSPL_JOB_TITLE_RETENTION_DAYS` | `90` | Dopo quanti giorni il nome viene cancellato (solo se la riga sopra è attiva). |

I nomi sono cifrati con una chiave ricavata da `CUPSPL_SECRET_KEY` ([protezione-dati.md](protezione-dati.md)).

## 4. Backup

Il backup *generale* è quello impostato qui. Ogni amministratore crea i propri nel portale (pagina *Backup*), senza scrivere nulla in
`.env`. Tutto viene scritto dentro una sola cartella (`/backups` nel contenitore, `./data/backups` sull'host). Dettagli, cifratura e
ripristino: [backup.md](backup.md).

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_BACKUP_ENABLED` | `false` | Attiva il backup generale. |
| `CUPSPL_BACKUP_DIR` | `general` | La sua sottocartella dentro la cartella dei backup. |
| `CUPSPL_BACKUP_HOUR` | `3` | Ora locale (0-23) dell'esecuzione giornaliera. Se il gateway era spento a quell'ora, parte appena si riavvia. |
| `CUPSPL_BACKUP_KEEP_DAILY` | `7` | Copie conservate: l'ultima di ognuno degli ultimi N giorni. |
| `CUPSPL_BACKUP_KEEP_WEEKLY` | `4` | L'ultima di ognuna delle ultime N settimane. |
| `CUPSPL_BACKUP_KEEP_MONTHLY` | `12` | L'ultima di ognuno degli ultimi N mesi. Le copie più vecchie si cancellano solo dopo che la nuova è stata scritta e riletta. |
| `CUPSPL_BACKUP_REQUIRE_MARKER` | `false` | `true` scrive solo se nella cartella esiste il file `.printminder-destination`. Usalo quando la cartella è un disco USB o una condivisione di rete: se il disco non è montato il backup fallisce (rosso nel portale) invece di riempire il disco del server. Crea il file una volta, con il disco montato: `touch data/backups/<cartella>/.printminder-destination`. |
| `CUPSPL_BACKUP_RECIPIENT` | vuoto | La chiave di recupero creata da `cups-policy-admin backup-key` (`cpgbk1.xxxx.yyyy`). Vuoto = i backup **non sono cifrati** e **non contengono segreti** (né la chiave segreta, né la chiave TLS, né il segreto RADIUS). |
| `CUPSPL_BACKUP_ROOT` | `/backups` | L'unica cartella in cui il gateway può scrivere i backup, **dentro il contenitore**. Collegata a `BACKUP_DIR` della parte A. Lasciala. |
| `CUPSPL_BACKUP_HOST_PATH` | impostata dall'init | Solo mostrata nel portale: dove si trova `/backups` sull'host. Si riempie da `BACKUP_HOST_PATH` della parte A. |
| `CUPSPL_BACKUP_CONFIG_DIR` | `/config` | Copia in sola lettura di `config/` (TLS) dentro il contenitore. Salvata solo nei backup cifrati. Lasciala. |
| `CUPSPL_BACKUP_ENV_FILE` | `/project.env` | Copia in sola lettura di `.env` dentro il contenitore. Salvata solo nei backup cifrati. Lasciala. |

## 5. Aggiornamenti

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_UPDATE_CHECK` | `true` | Una volta al giorno il gateway chiede a GitHub qual è l'ultima versione e, se è più nuova, mostra un avviso agli amministratori. Non si aggiorna nulla da solo e la richiesta non invia nulla del tuo server. `false` = non chiedere mai. |
| `CUPSPL_UPDATE_API_URL` | l'indirizzo "ultima release" di GitHub | A chi lo chiede. Cambialo solo per un fork o uno specchio che risponde nello stesso formato. |
| `CUPSPL_UPDATE_DIR` | `/data/update` | Cartella condivisa con il contenitore facoltativo `updater` (`docker compose --profile autoupdate`). Lasciala. |

Come aggiornare: [installazione.md](installazione.md).

## 6. Stampa e scansione

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_WEB_UPLOAD_MB` | `25` | File più grande accettato stampando dal portale (telefoni). |
| `CUPSPL_WEB_MAX_COPIES` | `20` | Massimo di copie in un lavoro dal portale. |
| `CUPSPL_MAX_REQUEST_MB` | `200` | Un lavoro IPP (documento compreso) più grande di così viene rifiutato. Un reverse proxy davanti deve permetterne almeno altrettanto. |
| `CUPSPL_RECONCILE_INTERVAL` | `30` | Secondi tra i confronti dei lavori del gateway con CUPS (così si correggono le quote e le pagine reali). Se CUPS non è raggiungibile, nel log compare `reconcile:`. |
| `CUPSPL_SCAN_URL` | l'immagine imposta `http://ipp-usb:60000` | Scanner eSCL. Gli scanner si trovano da soli; scrivila solo per **aggiungerne** altri che non si trovano (una stampante di rete con eSCL su una porta insolita), come `nome=indirizzo` separati da virgole: `http://ipp-usb:60000,ufficio=https://192.168.1.50:443`. Vuoto = la scansione è spenta. |
| `CUPSPL_SCAN_TIMEOUT` | `180` | Secondi per una scansione (una pagina dal vetro può essere lenta). |
| `CUPSPL_ESCL_ANONYMOUS` | `false` | `true` accetta scansioni da app che non sanno inviare le credenziali (per esempio NAPS2). Sono attribuite all'account `ospite-scansione` con l'IP di chi le manda. Lascia `false` se la rete non è fidata ([scansione.md](scansione.md)). |

## 7. Stampanti

### La pagina Stampanti

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_PRINTERS_REFRESH_SECONDS` | `15` | Per quanto tempo si riusa quello che dicono le stampanti, e ogni quanto la pagina si ricarica da sola quando un amministratore attiva "Aggiornamento automatico". `0` o un valore inutilizzabile = 15; minimo 5, massimo 3600. Più è basso, più spesso si interrogano le stampanti. |
| `CUPSPL_PRINTER_ALERTS_USERS` | `true` | Un inceppamento, la carta finita o l'inchiostro/toner finito sono sempre mostrati agli amministratori (la campanella). Con `true` vengono avvisate anche le persone che hanno una stampa in attesa su quella stampante, nella loro campanella, e solo loro. `false` = solo gli amministratori. |

### Stampanti USB: ricerca e rimozione

Una stampante USB nuova ottiene da sola la sua coda in CUPS entro circa un minuto: con il ponte `ipp-usb` se la stampante parla IPP su USB
(quasi tutte le recenti, senza driver), altrimenti con il backend `usb` di CUPS (molte laser più vecchie; serve un driver che CUPS conosca).
Una stampante servita da `ipp-usb` non viene mai presa nel secondo modo. Vedi [stampanti.md](stampanti.md).

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_AUTO_DISCOVER` | `true` | Cerca le stampanti da solo. `false` = solo le code che crei tu. |
| `CUPSPL_DISCOVERY_INTERVAL` | `30` | Secondi tra una ricerca e l'altra (e il controllo di quali stampanti USB non rispondono). |
| `CUPSPL_USB_BRIDGE_HOST` | `ipp-usb` | Dove si trova il ponte `ipp-usb`. Vuoto = non cercare lì. |
| `CUPSPL_USB_BRIDGE_PORTS` | `60000-60099` | Le porte che `ipp-usb` assegna alle stampanti (`http-min-port`..`http-max-port` della sua configurazione). |
| `CUPSPL_USB_DIRECT` | `true` | Cerca anche le stampanti USB che `ipp-usb` non serve. `false` = CUPS non tocca il bus USB. |
| `CUPSPL_OFFLINE_REMOVE_HOURS` | `8` | Una coda USB il cui dispositivo non risponde da queste ore viene rimossa da sola (la pagina Stampanti mostra un conto alla rovescia). `0` = mai. Le code di rete **non** vengono mai rimosse da sole: una stampante spenta per il fine settimana torna com'era. |

## 8. Rete e annuncio (mDNS)

`mdns` è il contenitore che annuncia le stampanti nella rete locale (Bonjour, AirPrint, Mopria). Usa la rete dell'host e legge lo stesso
`.env`.

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_PORTAL_URL` | vuoto | L'indirizzo pubblico del portale, usato nei messaggi ("chiedi più quota su ..."). Vuoto = ricavato dalla richiesta; per i messaggi mostrati dai client di stampa è meglio scriverlo. Esempio: `https://stampa.example.com:8631` |
| `CUPSPL_MDNS_HOSTNAME` | vuoto | Il nome che l'annunciatore pubblica. Deve essere uno dei nomi dentro il certificato TLS, altrimenti i client rifiutano di collegarsi. Vuoto = la parte host di `CUPSPL_PORTAL_URL`, altrimenti il nome della macchina. |
| `CUPSPL_MDNS_ADDRESSES` | vuoto | Indirizzi IPv4 da annunciare, separati da virgole. Vuoto = quello della route predefinita. Serve se la macchina ha più schede di rete e quella giusta non è la prima. |
| `CUPSPL_MDNS_PORT` | `0` | `0` = la porta del gateway. Il file compose la imposta da `GATEWAY_PORT`: non scriverla a mano. |
| `CUPSPL_MDNS_INTERVAL` | `30` | Secondi tra le letture dell'elenco delle code (una stampante scollegata o nascosta sparisce dalla rete entro questo tempo). |
| `CUPSPL_PUBLIC_SCHEME` | vuoto | Scrivi `ipps` solo dietro un reverse proxy che termina il TLS. Altrimenti lascialo vuoto: si ricava dalla richiesta. |

## 9. Certificato TLS: avvisi

Il gateway si limita a guardare il certificato in `config/tls`; a rinnovarlo pensa altro (`scripts/cert-sync.sh`, vedi
[certificati.md](certificati.md)). "Il certificato è scaduto" e "l'ultima esecuzione di cert-sync.sh è fallita" sono sempre segnalati.

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_CERT_NAME_CHECK` | `true` | Avvisa quando l'indirizzo annunciato in rete non è nel certificato. `false` spegne questo avviso. |
| `CUPSPL_CERT_EXPIRY_WARN_ENABLED` | `false` | `true` avvisa prima che il certificato scada. Spento di default: un rinnovo che semplicemente non è ancora dovuto sembrerebbe un problema. |
| `CUPSPL_CERT_EXPIRY_WARN_DAYS` | `14` | Quanti giorni prima della fine. Let's Encrypt rinnova circa 30 giorni prima, quindi un valore sotto 30 vuol dire "il rinnovo fallisce da un po'". |

## 10. Altro

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CUPSPL_TIMEZONE` | `UTC` | Il fuso orario delle settimane e dei mesi delle quote, degli orari nel portale e dei log. **Cambialo con il tuo**, per esempio `Europe/Rome` o `America/New_York` ([elenco](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)). |
| `CUPSPL_LANGUAGE` | `en` | Lingua del portale per i browser che non dicono la propria e per gli utenti che non ne hanno scelta una: `en`, `it`, `es`, `ru`, `zh` ([lingue.md](lingue.md)). Ogni utente può scegliere la sua in *Impostazioni*. |
| `CUPSPL_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` o `ERROR`. `DEBUG` è molto prolisso: usalo per indagare su un problema. |
| `CUPSPL_HEALTHZ_INFO` | vuoto | Cosa mostra `/healthz` oltre allo stato. **Non chiede login**, quindi lo legge chiunque raggiunga la porta. Vuoto = solo lo stato. Aggiungi, separati da virgole: `version` (la versione in esecuzione), `printers` (quante code: usb, rete, virtuali; mai i nomi). Esempio: `version,printers`. |
| `CUPSPL_NOTICE_INTERVAL` | `0` | Ogni quanto lo stesso avviso dalla stessa fonte viene segnalato di nuovo, così un client che riprova 100 volte non inonda la campanella e il log. `0` = in base al livello del log: `DEBUG` 1 minuto, `INFO` 1 giorno, `WARNING` 3 giorni, `ERROR` 7 giorni. Scrivi un numero di secondi per scegliere tu. |

## 11. Parte A: variabili di docker compose

Le legge docker compose stesso, non il programma.

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `PRINTGW_REGISTRY` | `ghcr.io/deh-aleh` | Da dove arrivano le immagini già pronte. Per costruirle da questa cartella (sviluppatori) cancella la riga. |
| `PRINTGW_VERSION` | la versione installata | Quale versione gira. Non cambiarla a mano: lo fa `scripts/update.sh`, dopo un backup. |
| `PUID`, `PGID` | il tuo utente | L'utente Linux che esegue il gateway. Deve poter leggere la chiave TLS e scrivere in `data/`. Compilati per te. |
| `PROJECT_DIR` | la cartella del progetto | Percorso completo di questa cartella. Lo usa solo il contenitore facoltativo `updater`. |
| `GATEWAY_PORT` | `8631` | La porta a cui si collegano le persone (`https://<server>:PORTA`). Cambiala se la 8631 è occupata; `631` se nient'altro la usa. |
| `CUPS_QUEUES` | vuoto | Stampanti create in CUPS all'avvio, come `NOME=INDIRIZZO` separati da spazi. Ognuna è creata una volta sola: se poi elimini la coda, non torna (`scripts/queue-restore.sh NOME --reboot` la riporta). Le stampanti USB non vanno elencate; elencane una solo per darle un nome fisso. Esempi: `CUPS_QUEUES="UFFICIO=ipp://192.168.1.60/ipp/print"`, `CUPS_QUEUES=HP7305=ipp://ipp-usb:60000/ipp/print` |
| `CUPS_VIRTUAL_QUEUE` | `0` | `1` crea anche una coda di prova che scrive file PDF invece di stampare (per provare le quote senza carta). In produzione usa `0`. |
| `AUDIT_ARCHIVE_HOST_PATH` | `<progetto>/data/audit-archive` | Solo mostrata nel portale (vedi `CUPSPL_AUDIT_ARCHIVE_HOST_PATH`). |
| `BACKUP_HOST_PATH` | `<progetto>/data/backups` | Solo mostrata nel portale. |
| `BACKUP_DIR` | `./data/backups` | La cartella dell'host montata su `/backups`: l'unico posto in cui possono andare i backup. Per salvare su un disco USB o una condivisione, montala **dentro** questa cartella. |
| `COMPOSE_PROFILES` | non impostata | `autoupdate` avvia il contenitore facoltativo `updater` (il pulsante "Aggiorna" nel portale; richiede il socket di Docker: leggi prima l'avvertenza in [installazione.md](installazione.md)). |
| `FORWARDED_ALLOW_IPS` | non impostata | Solo dietro un reverse proxy: l'indirizzo del proxy, perché il gateway si fidi di `X-Forwarded-For` (vedi [installazione.md](installazione.md)). |

### Sincronizzazione del certificato (`CERT_SYNC_*`)

Le legge solo `scripts/cert-sync.sh` (il programma no). Servono a copiare il certificato TLS dalla macchina che lo rinnova (Nginx Proxy
Manager, certbot) in `config/tls` e a riavviare il gateway se è cambiato. Non scriverle se non lo usi. Passo per passo, con l'utente di
sola lettura: [certificati.md](certificati.md).

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `CERT_SYNC_HOST` | nessuno (obbligatoria) | Nome o indirizzo della macchina che ha il certificato. Esempio: `npm.example.lan` |
| `CERT_SYNC_USER` | nessuno (obbligatoria) | L'utente ssh su quella macchina: uno che può solo leggere. |
| `CERT_SYNC_KEY` | nessuno (obbligatoria) | Percorso completo della chiave privata ssh di questa macchina. |
| `CERT_SYNC_REMOTE_DIR` | nessuno (obbligatoria) | Percorso completo, su quella macchina, della cartella con i due file. Nginx Proxy Manager: `.../data/letsencrypt/live/npm-3`; certbot: `/etc/letsencrypt/live/tuodominio`. |
| `CERT_SYNC_PORT` | `22` | La porta ssh. |
| `CERT_SYNC_CERT_FILE` | `fullchain.pem` | Nome del file del certificato (la catena completa). Solo un nome di file semplice. |
| `CERT_SYNC_KEY_FILE` | `privkey.pem` | Nome del file della chiave privata. Solo un nome di file semplice. |

## 12. Impostate dall'immagine: non cambiarle

Le decidono l'immagine e `docker-compose.yml`. Sono elencate perché si sappia cosa sono; scriverle in `.env` può impedire l'avvio del
gateway o aprire una falla di sicurezza.

| Variabile | Valore nel contenitore | Perché |
|---|---|---|
| `CUPSPL_TLS_CERTFILE`, `CUPSPL_TLS_KEYFILE` | `/tls/fullchain.pem`, `/tls/privkey.pem` | La cartella `config/tls`. Senza TLS il gateway non parte. |
| `CUPSPL_DATABASE_URL` | `sqlite:////data/gateway.db` | Il file SQLite nel volume `gateway-data`. |
| `CUPSPL_CUPS_URL` | `unix:///run/cups/cups.sock` | Il socket privato condiviso con CUPS. CUPS non è mai raggiungibile dalla rete. |
| `CUPSPL_ALLOW_INSECURE_AUTH` | `false` | `true` accetterebbe password su HTTP in chiaro. Solo per prove in un laboratorio chiuso. Mai in produzione. |
| `CUPSPL_HOST`, `CUPSPL_PORT` | `0.0.0.0`, `8631` | Dove il programma ascolta **dentro** il contenitore. Per cambiare la porta che usano le persone, cambia `GATEWAY_PORT` (parte A). |
