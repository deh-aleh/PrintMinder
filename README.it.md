<picture>
  <source media="(prefers-color-scheme: dark)" srcset="app/admin/static/icon-light.svg">
  <img src="app/admin/static/icon-dark.svg" alt="Icona di PrintMinder" width="96" align="right">
</picture>

# PrintMinder

[English](README.md) · **Italiano**

Autenticazione, quote e registro delle attività davanti a CUPS (IPP), con un portale web. CUPS e ipp-usb restano dipendenze non
modificate. Il gateway è l'unico punto d'ingresso: autentica gli utenti (account locali e/o RADIUS), **impone** la loro identità,
applica i limiti di stampa, registra chi ha stampato e scansionato cosa e inoltra il job a CUPS.

```
client IPP ──ipps (TLS + Basic)──▶ gateway ──socket unix──▶ CUPS ──rete interna──▶ ipp-usb ──USB──▶ stampante
browser ───────https───────────▶     │  └─▶ DB (SQLite): utenti, gruppi, regole, audit
                                     └────▶ RADIUS (facoltativo)        portale su /admin (admin) e /me (utenti)
```

> I nomi interni come `CUPSPL_*`, `cups-policy-admin` e il progetto compose `printgw` precedono il nome PrintMinder e restano
> invariati perché le installazioni esistenti continuino a funzionare.

## Cosa fa

- **Account**: locali (argon2id) e/o RADIUS; **chiavi di stampa** personali e revocabili, così la password di dominio non resta mai su un PC o un telefono.
- **Quote**: job e pagine per settimana o mese, per gruppo con override per utente; gli utenti chiedono di più, gli amministratori approvano.
- **Permessi**: colore, stampa solo fronte, quali stampanti e in quali orari, per gruppo con override per utente; gli utenti chiedono ciò che manca, per sempre o fino a una data.
- **Stampa**: IPP/IPPS per i computer, **stampa dal browser** per qualunque telefono, annuncio sulla LAN (AirPrint/Mopria).
- **Scansione**: eSCL attraverso il gateway e dal portale, insieme alla stampa sullo stesso dispositivo USB.
- **Audit**: chi ha stampato/scansionato cosa (pagine reali), registro separato delle azioni amministrative, conservato per sempre con archivi compressi verificati.
- **Stampanti**: stato, inchiostro e contatori, blocco/nascondimento, stampanti di prova, stampa periodica di manutenzione e stampa di prova per le fisiche.
- **Backup**: programmati per amministratore, cifrati con una chiave di recupero, ripristinabili da riga di comando.
- **Portale in 5 lingue**: inglese, italiano, spagnolo, russo, cinese semplificato; scelta per utente. La documentazione (inglese e italiano) si legge dentro il portale, per gli amministratori.

## Funzionalità e stato

✅ fatto e provato · 🟡 parziale · ⬜ previsto

| Area | Funzionalità | Stato |
|---|---|---|
| **Identità** | Account locali (argon2id); accesso RADIUS (facoltativo); primo amministratore con codice monouso | ✅ |
| | Altri provider (LDAP/AD, OIDC); autenticazione a due fattori per gli admin | ⬜ |
| **Stampa** | Proxy IPP/IPPS davanti a CUPS; nessun bypass (CUPS non è raggiungibile); chiavi di stampa personali | ✅ |
| | Qualunque stampante supportata da CUPS (USB via ipp-usb, o di rete) | 🟡 provata con due stampanti via USB: una HP Smart Tank 7300 (tramite ipp-usb) e una Brother DCP-7055 (backend usb di CUPS, driver brlaser: trovata, coda creata e prima stampa riuscita senza alcuna impostazione) |
| | Annuncio sulla LAN (DNS-SD) e stampa da browser | ✅ visto da Android con Mopria; iPhone non provato |
| | Le stampanti USB nuove ottengono da sole la loro coda (prima ipp-usb, altrimenti backend usb di CUPS + driver); le code USB irraggiungibili si tolgono dopo un conto alla rovescia, qualunque coda morta si elimina a mano | ✅ |
| | Stampa trattenuta con rilascio successivo (pull printing) | ⬜ |
| **Policy** | Utenti e gruppi; limiti di job e pagine per settimana/mese; override per utente | ✅ |
| | Deroghe: richieste degli utenti, approvazione dell'admin, concessioni temporanee o permanenti; cambio gruppo su richiesta | ✅ |
| | Pagine contate prima di stampare per PDF, immagini, testo e PostScript | ✅ limite morbido per gli altri file |
| | Limiti per funzionalità (colore, fronte-retro) o per stampante; orari consentiti | 🟡 non ancora provato su stampanti vere |
| **Scansione** | eSCL attraverso il gateway (stesse chiavi, audit, insieme alla stampa) e scansione dal portale | ✅ |
| | Client eSCL nativi che sanno autenticarsi (prova sul campo) | ⬜ |
| **Audit** | Audit di stampe e scansioni con pagine reali; registro separato delle azioni amministrative | ✅ |
| | Conservazione illimitata con archivi compressi verificati; esportazione CSV, filtri, consultazione e download degli archivi | ✅ |
| | Report di utilizzo: utenti che stampano di più in un periodo, dettaglio per stampante, gruppi esclusi, pagina / CSV / PDF | ✅ |
| | Nomi dei file cifrati nel database; pulsante per smettere di salvarli; cancellazione facoltativa dopo qualche giorno | ✅ |
| | Esportazione verso syslog/SIEM; anonimizzazione | ⬜ |
| **Portale** | Portale admin (audit, utenti, gruppi, richieste con concessioni, azioni, stampanti, backup, archivio) e area utente (consumo, chiavi, richieste, stampa, scansione); la documentazione è inclusa per gli amministratori (inglese e italiano) | ✅ |
| | Impostazioni: password, tema, lingua, aggiornamento; interfaccia adatta al telefono; pulsanti «copia» | ✅ |
| | Pagina Stampanti: stato, inchiostro, contatori a vita (HP), firmware, scanner; blocco, nascondimento, stampanti di prova; manutenzione del gateway | ✅ |
| | Stampa periodica di manutenzione e stampa di prova con statistiche (stampanti fisiche); elenco con le fisiche per prime, spostabili con le frecce su/giù (ordine proprio per ogni amministratore); code rinominabili; badge IPP-USB / USB | ✅ |
| | Portale in inglese, italiano, spagnolo, russo, cinese | ✅ spagnolo/russo/cinese da far rivedere a madrelingua |
| | Notifiche (email/webhook) per le richieste in attesa; report di utilizzo | ⬜ |
| | Richieste di permessi (colore, solo fronte, stampanti, orari) | ✅ |
| **Operatività** | Stack docker (ipp-usb + CUPS + gateway + mDNS), nulla installato sull'host | ✅ |
| | Backup programmati per amministratore (cartella, ora, rotazione, cifratura con passphrase/chiave di recupero), ripristino da CLI | ✅ |
| | Migrazioni del database (Alembic), health check, log, CLI di amministrazione | ✅ |
| | Immagini per amd64 e arm64 su ghcr.io; script di aggiornamento che scarica un pacchetto di release controllato, fa prima un backup e torna indietro da solo (proponendo il ripristino del backup) se la nuova versione non parte; avviso di nuove versioni; un solo file `.env` che un aggiornamento non tocca mai | 🟡 non ancora provate su una vera macchina ARM |
| | Pulsante Aggiorna nel portale (contenitore facoltativo `updater`, usa il socket di Docker) | 🟡 provato solo con simulazioni |
| | Backup su disco di rete o USB: file segnaposto contro un disco non montato (attivo di default), avviso nella campanella quando un backup fallisce, limite di tempo per un disco che non risponde | ✅ provato con una condivisione SMB |
| | Certificato TLS: avvisi (scaduto, indirizzo annunciato mancante, avviso di scadenza facoltativo) e `scripts/cert-sync.sh` per copiare un certificato rinnovato da Nginx Proxy Manager o certbot | 🟡 script provato con simulazioni, non ancora con un vero Nginx Proxy Manager |
| | Campanella con gli avvisi per gli amministratori (una sola, prima i propri); problemi di stampante (inceppamento, carta, inchiostro) per gli amministratori e per chi aspetta; l'utente è avvisato se cambiano gruppo, diritti, quota o richiesta; promemoria, una volta sola, di salvare `CUPSPL_SECRET_KEY` e avviso se cambia; `/healthz` mostra solo lo stato se non chiedi di più | ✅ |

## Limiti

L'elenco completo, con le soluzioni, è in [docs/it/limiti.md](docs/it/limiti.md). Quelli da conoscere prima di cominciare:

- **Il limite pagine è morbido** per i file di cui non si contano le pagine (formato sconosciuto, PDF cifrato, oltre 64 MB): il job che
  supera il limite *viene stampato* e le sue pagine reali bloccano poi i successivi. Con `Create-Job` + `Send-Document` il conteggio
  arriva dopo l'accettazione del job. Un `Create-Job` senza documento libera la quota solo quando CUPS lo annulla (di default 3 h).
- **Serve un host Linux** per le stampanti USB e per l'annuncio mDNS (Docker Desktop su Windows/macOS: solo stampanti di rete, niente scoperta).
- **Il servizio di stampa di sistema di Android non sa autenticarsi**: usa Mopria Print Service o stampa dal browser. Windows 11 è provato in parte ([stampa.md](docs/it/stampa.md#windows-11)); iPhone e macOS non sono provati.
- **Un gateway per stampante USB** e **uno per database SQLite** (nessuna alta disponibilità). Le immagini sono costruite per
  l'architettura della macchina che le compila; tornare a una versione precedente dopo una migrazione richiede un backup.
- **TLS obbligatorio**: installa il certificato autofirmato sui client o usa quello della tua CA.
- Una stampante scollegata si rileva entro ~30 s (code di rete: prova TCP, non la carta).
- I **nomi dei file stampati sono cifrati** nel database (chiave da `CUPSPL_SECRET_KEY`: non cambiarla); il resto del database no. Per tutto il resto cifra il disco: [protezione-dati.md](docs/it/protezione-dati.md).
- Le traduzioni in spagnolo, russo e cinese non sono riviste da madrelingua; le pagine stampate dal gateway restano in inglese.

## Installazione (Docker, consigliata)

Requisiti: un server **Linux**, Docker Engine con Compose, `openssl`, `curl`, `tar`, `python3`, una stampante USB o di rete e una porta TCP
raggiungibile dai client (predefinita 8631). Sull'host non si installa nulla.

```sh
# 0. scarica il pacchetto della release (ultima versione: https://github.com/deh-aleh/PrintMinder/releases)
VERSION=1.0.0
curl -LO https://github.com/deh-aleh/PrintMinder/releases/download/v$VERSION/printminder-$VERSION.tar.gz
tar xzf printminder-$VERSION.tar.gz && cd printminder-$VERSION      # (nella guida c'è anche come controllare il download)

# 1. nomi / IP con cui i client raggiungeranno il server (finiscono nel certificato TLS)
scripts/docker-init.sh print.lan 192.168.1.50      # crea .env (tutte le impostazioni), config/tls/, data/

# 2. impostazioni: RADIUS è facoltativo (host e secret vuoti = solo account locali)
$EDITOR .env

# 3. stampanti, in .env — USB (prima ferma ipp-usb sull'host: sudo systemctl disable --now ipp-usb && sudo systemctl mask ipp-usb)
#       CUPS_QUEUES=HP7305=ipp://ipp-usb:60000/ipp/print
#    oppure una stampante di rete:
#       CUPS_QUEUES="UFFICIO=ipp://192.168.1.60/ipp/print"

# 4. avvio
docker compose up -d

# 5. leggi il codice monouso e scegli la password dell'amministratore "cups_orchestrator"
docker compose logs gateway | grep "FIRST RUN"
#    poi apri https://<server>:8631/admin/setup
```

Poi: crea utenti e gruppi nel portale (`https://<server>:8631/admin`); ogni utente crea una **chiave di stampa** in *Profilo* e
la usa come password quando un computer o un telefono chiede le credenziali (indirizzo della stampante
`ipps://<server>:8631/printers/<coda>`); i telefoni senza nulla di installato possono usare *Stampa* nel portale. Verifica l'installazione
con `curl -sk https://<server>:8631/healthz`. Per usare un certificato firmato da una CA metti `fullchain.pem` e `privkey.pem` in
`config/tls/` ed esegui `docker compose restart gateway` (per tenerne aggiornato uno rinnovato altrove: [certificati.md](docs/it/certificati.md)). Aggiorna con `scripts/update.sh` (prima fa un backup, torna indietro da solo se la nuova versione non parte; immagini per amd64 e arm64). Per provare senza stampante né RADIUS vedi la guida. Nella guida c'è anche
l'alternativa con installazione sull'host (systemd, modifica `/etc/cups`).

Guida completa: [docs/it/installazione.md](docs/it/installazione.md).

## Documentazione

| Argomento | Documento |
|---|---|
| **Installazione** (docker e host, stampanti USB/rete, TLS, aggiornamenti) | [installazione.md](docs/it/installazione.md) |
| **Risoluzione dei problemi** | [risoluzione-problemi.md](docs/it/risoluzione-problemi.md) |
| Architettura e tecnologie | [architettura.md](docs/it/architettura.md) |
| Come è fatta l'applicazione (ogni file sorgente, `.env`, script) | [funzionamento-applicazione.md](docs/it/funzionamento-applicazione.md) |
| Guida utente · Guida amministratore (CLI compresa) | [guida-utente.md](docs/it/guida-utente.md) · [guida-amministratore.md](docs/it/guida-amministratore.md) |
| Account, gruppi, chiavi di stampa | [account.md](docs/it/account.md) |
| Quote, richieste, concessioni | [quote.md](docs/it/quote.md) |
| Stampa e collegamento dei dispositivi | [stampa.md](docs/it/stampa.md) |
| Stampanti: panoramica, controlli, stampa di manutenzione | [stampanti.md](docs/it/stampanti.md) |
| Scansione | [scansione.md](docs/it/scansione.md) |
| Audit e archivio | [audit.md](docs/it/audit.md) |
| Backup e ripristino | [backup.md](docs/it/backup.md) |
| Certificati TLS: avvisi, file della CA, sincronizzazione automatica | [certificati.md](docs/it/certificati.md) |
| Protezione dei dati: nomi dei file, cifratura, retention | [protezione-dati.md](docs/it/protezione-dati.md) |
| Lingue e traduzioni | [lingue.md](docs/it/lingue.md) |
| Limiti noti | [limiti.md](docs/it/limiti.md) |

Tutto è disponibile anche in inglese (lingua principale): [docs/en](docs/en) · [docs/README.md](docs/README.md).

## Licenza

PrintMinder è rilasciato con la [licenza Apache 2.0](LICENSE). Puoi usarlo, modificarlo e distribuirlo, anche a scopo commerciale, purché mantieni
l'avviso di copyright e il file [NOTICE](NOTICE) (crediti ad Alessio Paccino) e indichi le modifiche che fai. Copyright 2026 Alessio Paccino.
