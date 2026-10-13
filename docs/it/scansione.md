# Scansione

[Indice della documentazione](../README.md) · [English](../en/scanning.md) · Italiano

La scansione usa **eSCL** (AirScan): `ipp-usb` lo serve sulla stessa porta di IPP, quindi stampa e scansione passano dallo stesso
dispositivo USB senza litigare — **ipp-usb è l'unico proprietario** (`ipp-usb` e SANE dell'host vanno fermati). Una stampa inviata durante
una scansione funziona. SANE in rete è stato scartato: non autentica per utente e riporterebbe il conflitto sul dispositivo; TWAIN Direct
è poco supportato.

## 1. Scoperta degli scanner

Gli scanner non si configurano uno per uno; si **trovano a runtime**:

- a ogni coda CUPS di rete (ipp-usb dà a ogni stampante USB la sua porta) si chiedono le capacità eSCL;
- più gli indirizzi elencati in `CUPSPL_SCAN_URL` (`nome=url`, separati da virgola; l'immagine preimposta `http://ipp-usb:60000`; vuoto =
  solo scoperta automatica).

Gli scanner rispondono a eSCL sulla porta IPP della coda o sulla 80; gli altri casi vanno in `CUPSPL_SCAN_URL`. Uno scanner scollegato
sparisce entro ~30 s. Il servizio `mdns` annuncia ogni scanner come `_uscans._tcp` (`rs` = `eSCL` per quello predefinito, `eSCL-<id>` per gli altri).

## 2. Scansionare dal portale

*Scansiona* (`/me/scan`): nulla da installare, funziona da qualunque telefono.

- Scelta dello **scanner** se ce n'è più di uno.
- **Sorgente**: *Automatica* (caricatore se lo scanner dichiara `ScannerAdfLoaded`, altrimenti vetro), *Vetro* o *Caricatore* (legge **tutti** i
  fogli fino a quando `NextDocument` risponde 404; massimo 100).
- Colore / grigi / bianco e nero; **qualità** e **formato carta** secondo ciò che lo scanner dichiara davvero per quella sorgente (per
  esempio vetro fino a 1200 dpi e caricatore solo fronte fino a 300).
- Uscita: **PDF** (più fogli uniti con pypdf) o **JPEG** (più fogli: ZIP); campo **nome del file**.
- Dove salvare: i browser Chromium aprono la scelta della cartella (File System Access API); gli altri salvano nella cartella dei
  download (un sito web non può scrivere in un percorso digitato a mano).
- La scansione gira come **attività di fondo del server**: puoi lasciare la pagina e scaricare dopo (il risultato resta **15 minuti in
  memoria**, visibile solo al proprietario; una scansione web alla volta). Se lo scanner risponde 409/503 (si sta svegliando) il
  gateway riprova 3 volte.

## 3. Scansione con client eSCL

Il gateway espone `/eSCL/...`. `ScannerCapabilities` e `ScannerStatus` sono pubblici (come la query di capacità IPP); tutto il resto
richiede HTTP Basic con **nome utente + chiave di stampa**, stessa autenticazione e stesso throttling della stampa. Percorsi ammessi:
`ScanJobs` (POST), `ScanJobs/<id>/NextDocument|ScanImageInfo` (GET), `ScanJobs/<id>` (DELETE); il resto è 404.

- Ogni scansione è una riga dell'audit con `kind=scan`; il dispositivo è la coda CUPS dello scanner. Stati: `accepted` → `completed`
  (1 pagina per `NextDocument`), `failed` (scanner occupato o che non risponde), `canceled` (solo se annullata prima di consegnare la pagina).
- Un utente non può leggere né annullare la scansione di un altro (404). `Location` è riscritto sull'indirizzo del gateway.
- Il job eSCL resta associato all'utente finché il client lo cancella con DELETE — è questo che libera lo scanner.
- **Client senza credenziali** (NAPS2 non sa inviarle): `CUPSPL_ESCL_ANONYMOUS=true` accetta scansioni senza login, registrate come
  l'account locale senza password `ospite-scansione` (non può entrare nel portale), con l'IP di chi chiama nelle opzioni dell'audit.
  Credenziali sbagliate restano 401. Finché l'opzione è spenta, una richiesta senza credenziali viene rifiutata (401) e compare come avviso nella campanella ([guida-amministratore.md](guida-amministratore.md)), al massimo una volta per intervallo e per fonte. **Predefinito spento**; chiunque nella rete raggiunga la porta 8631 potrebbe scansionare: usalo solo su
  rete fidata. NAPS2 non ha trovato l'annuncio mDNS: inserisci IP e porta a mano.

## 4. Note

- Una scansione consegnata sul client conta come completata anche se l'utente non salva il file.
- Se il caricatore dorme lo scanner può dichiararlo vuoto: in *Automatica* si finisce sul vetro (pagina bianca). Scegli *Caricatore*
  oppure togli e rimetti i fogli.
- La modalità manutenzione ferma anche la scansione ([stampanti.md](stampanti.md)).
- Non ancora provati: client eSCL nativi che sanno autenticarsi (sane-airscan, Image Capture).
