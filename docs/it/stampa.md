# Stampa e collegamento dei dispositivi

[Indice della documentazione](../README.md) · [English](../en/printing.md) · Italiano

Ci sono due modi di stampare: attraverso l'**indirizzo IPP del gateway** (computer e app) oppure dal **browser** (qualunque telefono,
senza installare nulla). Entrambi passano dalle stesse quote, audit e identità (`gw:<utente>`).

## 1. Stampare dal browser

*Stampa* nel menu (`/me/print`), con la sessione aperta, senza bisogno di chiave.

- File accettati: PDF, JPEG, PNG, GIF, testo semplice — riconosciuti dal loro **contenuto**, non dal nome o da ciò che dichiara il browser.
- Dimensione massima `CUPSPL_WEB_UPLOAD_MB` (predefinito 25); copie fino a `CUPSPL_WEB_MAX_COPIES` (predefinito 20).
- Le opzioni dipendono dalla stampante scelta: formato carta (solo quelli elencati dalla coda), orientamento, colore / bianco e nero
  (se la coda è a colori), **intervallo di pagine** (`1,5`, `2-4`, `3-`), copie e un **commento** (max 50 caratteri) mostrato sotto il
  nome del file nell'audit.
- **Orientamento.** *Automatico* segue il file: un PDF con pagine già larghe si stampa da solo in orizzontale. *Orizzontale* su un
  PDF con pagine verticali ruota ogni pagina di 90° e la rimpicciolisce per farla stare sullo stesso foglio (lo fa il portale, perché i
  filtri PDF di CUPS capovolgono la pagina verticale su alcune stampanti, per esempio le Brother). Non riorganizza il testo come fa
  LibreOffice quando cambi lo stile di pagina in orizzontale: per quello imposta l'orizzontale nel programma ed esporta di nuovo il PDF.
  Le foto le ruota CUPS. I file di testo semplice non si possono ruotare (il portale lo dice e non stampa nulla).
- Le pagine contate per il limite sono quelle scelte × copie; un intervallo oltre la fine del documento è rifiutato prima di riservare quota.
- Una stampante che non risponde non viene offerta; nemmeno una bloccata. L'ordine dell'elenco è descritto in [stampanti.md](stampanti.md).

## 2. Stampare con l'indirizzo IPP

Indirizzo: `ipps://<server>:8631/printers/<coda>`. Il client si autentica con HTTP Basic: **nome utente + chiave di stampa**
(creata in *Profilo*; vedi [account.md](account.md)). La password di dominio non stampa.

| Dispositivo | Come collegarlo | Stato |
|---|---|---|
| **Linux** (KDE, GNOME, CUPS) | Dopo aver creato una chiave la pagina del profilo mostra l'indirizzo `ipps://utente:chiave@server/printers/coda` e un comando `lpadmin` già pronto; in alternativa `scripts/add-printer-linux.sh <server> <coda> <utente>`. La chiave resta nell'indirizzo della coda (`/etc/cups/printers.conf`, leggibile solo da root e dal gruppo `cups`) e il computer non la chiede più. | ✅ provato |
| **Qualunque dispositivo con browser** | `/me/print` | ✅ provato su Android |
| **Android + Mopria Print Service** | Vede le stampanti annunciate, chiede nome e chiave per ogni stampante e li ricorda. | ✅ provato (Android 13) |
| **Servizio di stampa di sistema di Android** | Vede le stampanti ma non sa chiedere le credenziali: davanti al 401 rinuncia. L'aggiunta manuale accetta solo un IP, quindi la chiave non si può mettere nell'indirizzo. | ❌ non utilizzabile — usa Mopria o il browser |
| **iPhone / iPad** | L'annuncio porta il sottotipo AirPrint e `air=username,password`; non è noto se iOS invii le credenziali. | ⬜ non provato |
| **Windows 11** | «Aggiungi dispositivo» trova le stampanti annunciate; la password si inserisce alla prima stampa. Procedura nel paragrafo [Windows 11](#windows-11) qui sotto. | 🟡 provato su Windows 11 25H2 |
| **macOS** | Aggiungi una stampante di rete con l'indirizzo IPP e inserisci nome utente + chiave; "ricorda". | ⬜ non provato |

Il dispositivo deve fidarsi del certificato del server. Le stampanti annunciate da mDNS compaiono anche sui desktop Linux (Avahi) senza
chiave: usarle non produce nulla finché la coda non viene aggiunta con la chiave nell'indirizzo.

Script: `scripts/print-test.sh [coda] [utente]` invia una pagina di testo (consuma un foglio).

### Windows 11

Provato su Windows 11 Home 25H2, con un server dal certificato attendibile e con un nome che il PC risolve. Il PC deve fidarsi del
certificato del server (vedi [certificati.md](certificati.md)): con un certificato autofirmato non installato Windows rifiuta la
connessione prima ancora di inviare la richiesta, e nel log del gateway non compare nulla.

1. Apri *Impostazioni → Bluetooth e dispositivi → Stampanti e scanner → Aggiungi dispositivo*. Dopo qualche secondo compaiono le
   stampanti annunciate, con il nome `<stampante> @ <nome del server>`.
   - Se non compare nessuna stampante, riavvia il PC. Se non basta, nella stessa pagina (*Stampanti e scanner*) trovi
     *Modalità di stampa protetta di Windows*: attivala e disattivala, poi riprova.
   - Se le stampanti non compaiono mai, di solito il PC e il server sono in reti diverse (VLAN) e l'annuncio mDNS non passa: serve un
     ripetitore mDNS (per esempio l'opzione «mDNS repeater» di molti router) oppure l'aggiunta a mano, qui sotto.
2. Clicca la stampante e premi *Aggiungi*. Windows scrive «Sto connettendo…»: **aspetta fino a 3-4 minuti**. Alla fine la stampante
   risulta pronta.
3. Alla prima stampa Windows chiede nome utente e **chiave di stampa** (non la password dell'account). Spunta «Ricorda le credenziali»:
   le stampe successive non chiedono più nulla.
4. Se dopo 3-4 minuti la stampante non si collega, salva le credenziali in anticipo:
   *Pannello di controllo → Account utente → Gestione credenziali → Gestione credenziali Windows → Aggiungi credenziali Windows*.
   - Indirizzo di rete: lo stesso nome del server che usi per la stampante (per esempio `stampe.example.org`).
   - Nome utente: il tuo nome utente del portale.
   - Password: la **chiave di stampa**, non la password dell'account.

   Poi rimuovi la stampante dall'elenco e ripeti dal punto 1.

**Aggiunta a mano**, quando l'annuncio non arriva: *Aggiungi dispositivo → Aggiungi manualmente → Seleziona una stampante condivisa tramite
nome* e incolla `https://<server>:8631/printers/<coda>` (senza `:8631` se il server sta dietro a un proxy sulla porta 443). Windows
sceglie da solo il driver «Microsoft IPP Class Driver». Questa strada non è ancora stata provata fino alla stampa.

Se rinomini una coda dal portale, il PC non lo sa: la voce vecchia smette di funzionare e la nuova va aggiunta come sopra.
Le credenziali salvate si vedono e si tolgono con `cmdkey /list` e `cmdkey /delete:<voce>`.

## 3. Cosa fa il gateway con ogni operazione IPP

Consentite: stampare (`Print-Job`, `Create-Job` + `Send-Document`), annullare, vedere job e stampanti, query di capacità. Vietate a
tutti: le operazioni amministrative di CUPS, `Print-URI`, `Send-URI` (rischio SSRF). Le query di capacità (`Get-Printer-Attributes` e `Validate-Job`,
corpi piccoli) ricevono risposta **senza credenziali** perché i client le fanno prima di averne (`CUPSPL_ANONYMOUS_DISCOVERY=true`):
non creano utenti né righe di audit e non inoltrano nulla. Il percorso completo è in
[architettura.md](architettura.md#4-percorso-di-una-richiesta-ipp).

Il gateway dichiara ai client `uri-security-supported=tls` e `uri-authentication-supported=basic` (CUPS direbbe `none`): senza,
Mopria non invia le credenziali.

## 4. Annuncio sulla rete (DNS-SD)

Il servizio `mdns` annuncia ogni coda come `_ipps._tcp` con il sottotipo `_universal` (AirPrint) e i record TXT `rp`, `pdl`, `URF`,
`Color`, `Duplex`, `TLS`, `air`, aggiornati ogni `CUPSPL_MDNS_INTERVAL` secondi. Il nome del server annunciato è `<nome>.local`
(Android risolve per multicast solo quei nomi) e il suo indirizzo deve stare nel certificato TLS. Le stampanti bloccate-nascoste, i
dispositivi irraggiungibili e la modalità manutenzione ritirano l'annuncio. Gli scanner sono annunciati come `_uscans._tcp`
([scansione.md](scansione.md)).

## 5. Job rifiutati, annullamento e stati

Se un job è rifiutato il client riceve un errore IPP con il motivo e l'indirizzo del portale. Un utente può annullare i propri job;
un amministratore può annullare i job in coda dall'audit ("Annulla") usando l'identità del proprietario (nessun privilegio CUPS in più).
Gli stati e il loro significato sono spiegati nella pagina *Audit* ([audit.md](audit.md)).
