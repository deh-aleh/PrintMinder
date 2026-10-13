# Limiti noti

[Indice della documentazione](../README.md) · [English](../en/limitations.md) · Italiano

Ciò che PrintMinder **non** fa (ancora) o fa con delle riserve. La versione breve è nel
[README](../../README.it.md#limiti).

## 1. Installazione

- Serve un **host Linux** per le stampanti USB e per mDNS (il passaggio USB e la rete `host` non esistono su Docker Desktop per
  Windows/macOS: lì funzionano solo le stampanti di rete e non si annuncia nulla).
- Un gateway per stampante USB (`ipp-usb` la vuole in esclusiva). Il suo contenitore vede tutti i dispositivi USB dell'host (necessario per il collegamento a caldo).
- Un gateway per database SQLite; nessuna alta disponibilità.
- Le immagini pubblicate esistono solo per amd64 e arm64 (niente ARM a 32 bit).
- `scripts/update.sh` aggiorna le immagini e aggiunge le opzioni nuove a `.env` e `config/gateway.env`; le modifiche a `docker-compose.yml` e agli script arrivano con `git pull`.
- Il pulsante *Aggiorna* del portale richiede il contenitore facoltativo `updater`, che tiene il socket di Docker (root sull'host): è spento di default. Aggiorna solo dentro la stessa versione maggiore.
- Backup su una condivisione di rete: i permessi li decide il montaggio (usa la cifratura) e una condivisione smontata è rilevata solo se è spuntata l'opzione «scrivi solo se montato».
- Tornare a una versione precedente dopo una migrazione del database richiede il ripristino di un backup.
- Le migrazioni sono provate solo su SQLite; con PostgreSQL vanno verificate (i tipi enum condivisi fra tabelle richiedono attenzione).
- Il database non è cifrato e contiene i nomi dei file stampati: proteggilo come dato personale.
- Certificati: i dispositivi devono fidarsi della CA aziendale; l'annuncio usa l'IP, quindi il certificato deve elencarlo.

## 2. Quota

- Il **limite pagine è morbido** per i file di cui non si possono contare le pagine: formati sconosciuti, PDF cifrati, file oltre 64 MB.
  Il job che supera il limite viene stampato; le sue pagine reali bloccano poi i successivi.
- Con `Create-Job` + `Send-Document` il conteggio arriva dopo l'accettazione del job.
- Un `Create-Job` senza documento libera la quota solo quando CUPS lo annulla (di default 3 h).
- Il conteggio delle pagine vale solo se esiste un limite di pagine e il documento è leggibile.
- Se RADIUS distingue `Mario` da `mario`, per il gateway sono la stessa persona (stessa quota).
- I limiti per funzionalità (colore, fronte-retro, formato carta, per stampante) non esistono ancora.

## 3. Client

- **Il servizio di stampa di sistema di Android non sa autenticarsi**: usa Mopria Print Service oppure stampa dal browser.
- Android conserva le credenziali per stampante e per sessione; il gateway può solo revocare la chiave.
- iPhone/iPad, Windows e macOS **non sono stati provati**; non è verificato se da lì il nome del file arrivi in `job-name`.
- Le chiavi di stampa dei client Linux/CUPS finiscono comunque salvate sul client (revocabili e inutili altrove).
- Le stampanti annunciate compaiono anche ai desktop Linux (Avahi) senza chiave; non fanno nulla finché la coda non è aggiunta con la chiave.

## 4. Stampanti e scanner

- Rilevamento USB automatico: una stampante servita da `ipp-usb` non viene mai presa dal backend usb di CUPS. Le stampanti senza IPP-su-USB richiedono un driver presente nell'immagine `cups` (inclusi brlaser, gutenprint, splix, foo2zjs). La convivenza fra backend usb di CUPS e `ipp-usb` sullo stesso bus con più stampanti è provata solo con un dispositivo alla volta.
- Le code USB irraggiungibili da 8 h (configurabile) vengono tolte da sole; quelle di rete mai.

- Il rilevamento di un dispositivo scollegato ritarda fino a ~30 s; per le code di rete è una prova TCP (nessuna informazione sulla carta).
- Gli scanner si trovano da soli solo se rispondono a eSCL sulla porta IPP della coda o sulla 80; altrimenti `CUPSPL_SCAN_URL`.
- I contatori a vita vengono solo dal servizio web HP; le altre marche mostrano i dati IPP.
- Una scansione consegnata sul client conta come completata anche se l'utente non salva il file.
- Un caricatore addormentato può essere dichiarato vuoto: in *Automatica* si usa il vetro (pagina bianca).
- Non provati i client eSCL nativi che sanno autenticarsi (sane-airscan, Image Capture).
- Le pagine stampate dal gateway (prova, manutenzione) sono sempre in inglese; russo/cinese richiedono un font incorporato.
- Se il gateway è spento, un intervallo di manutenzione perso non si recupera: la pagina parte appena riparte.

## 5. Backup e sicurezza

- Backup integrati: solo SQLite; code CUPS non incluse (sono in `scripts/backup.sh`); i file di configurazione si ripristinano a mano;
  nessuna destinazione remota diretta; la passphrase non è recuperabile. `scripts/backup.sh restore` è provato solo a mano.
- Il blocco dei login è in memoria e si azzera al riavvio.
- L'audit e il database non sono cifrati.

## 6. Lingue

- Spagnolo, russo e cinese scritti senza revisione di un madrelingua.
- Date e numeri non seguono la lingua.
- Il testo dell'audit conservato e i log del server restano in inglese.

## 7. Stato delle funzionalità

Lo stato di ogni funzionalità è nel [README](../../README.it.md#funzionalità-e-stato).
