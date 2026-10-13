# Stampanti: panoramica, controlli, stampa di manutenzione

[Indice della documentazione](../README.md) · [English](../en/printers.md) · Italiano

La pagina **Stampanti** (`/admin/printers`, per gli amministratori) mostra ciò che ogni stampante dice di sé accanto a ciò che il gateway
ha registrato. Tutto si legge dal vivo e al meglio: una stampante che non offre una fonte semplicemente non ha quella sezione.

## 1. Cosa mostra la scheda di una stampante

- Stato e coda di ogni coda CUPS; per un dispositivo che non risponde, **NON RAGGIUNGIBILE** (e sparisce dal modulo di stampa e
  dall'annuncio mDNS). Il rilevamento può ritardare di ~30 s. Per le code di rete è una prova TCP (non può sapere che la carta è
  finita); le code `usb:` / `file:` si assumono presenti.
- **Inchiostro** rimasto (livelli e colori da CUPS).
- **Contatori della stampante** (a vita): pagine totali, bianco/nero, colore, fogli fronte singolo/fronte-retro, inceppamenti, mancate
  prese — letti dal servizio web incorporato HP (`/DevMgmt/ProductUsageDyn.xml`). Le altre marche mostrano solo i dati IPP.
- Numero di serie, firmware, velocità, carta pronta, avvisi (come li riporta il dispositivo).
- Stato e capacità dello **scanner** (eSCL), con un badge *MFP* per i multifunzione.
- Accanto, ciò che il gateway ha registrato: job, pagine, scansioni, ultimo job.

Le letture sono parallele, tolleranti ai guasti e in cache per `CUPSPL_PRINTERS_REFRESH_SECONDS` secondi (predefinito 15; 0 o un valore non
valido significa 15; minimo 5, massimo 3600 — più basso significa interrogare le stampanti più spesso). L'interruttore **Aggiornamento automatico**
sotto il titolo ricarica la pagina da solo ogni tanti secondi, così una stampante scollegata compare senza premere F5. Parte spento, lo ricorda il
browser e la pagina non si ricarica mentre c'è un popup aperto o si sta scrivendo. Nulla è legato a un modello: supporto al colore, nome,
inchiostri e contatori si leggono dal dispositivo. I testi che arrivano dal dispositivo (nomi degli inchiostri, firmware, avvisi) si
mostrano come ricevuti.

## 2. Stampanti USB nuove e scollegate

**Le stampanti nuove compaiono da sole.** Ogni `CUPSPL_DISCOVERY_INTERVAL` secondi (30) il gateway guarda il lato USB e crea la coda CUPS
di ogni dispositivo nuovo — entro circa un minuto dal collegamento. Due strade, in quest'ordine di priorità:

1. **ipp-usb** (preferita): una stampante con IPP-su-USB (la maggior parte delle recenti) è servita dal contenitore `ipp-usb` su una
   porta di `CUPSPL_USB_BRIDGE_PORTS`; la sua coda punta a `ipp://ipp-usb:<porta>/ipp/print` e non richiede driver.
2. **Backend usb di CUPS**: per le stampanti senza IPP-su-USB (molte laser vecchie, per esempio la Brother DCP-7055): la coda punta a
   `usb://Marca/Modello?serial=…` e a CUPS serve un driver. L'immagine include brlaser, gutenprint, splix e foo2zjs; se CUPS non ne ha
   uno per quel modello la pagina Stampanti lo dice ("trovata, ma CUPS non ha un driver"). Un dispositivo servito da ipp-usb non viene
   mai preso per questa strada.

Un dispositivo viene preso dal backend usb solo dopo essere rimasto non servito per due controlli di seguito (ipp-usb si riavvia per qualche secondo a ogni collegamento o scollegamento USB, e una stampante che serve lui non va presa in quel momento).

La coda prende il nome dal modello, accorciato (al massimo 24 caratteri): si tolgono le parole inutili come "series", "printer", "MFP" e un
codice tra parentesi quadre, "Hewlett-Packard" diventa "HP", e un nome ancora troppo lungo tiene la marca e le parole con una cifra —
`HP Smart Tank 7300 series [A7E76E]` diventa `HP_Smart_Tank_7300`, `Brother DCP-7055` diventa `Brother_DCP-7055`. Il modello è quello che la
stampante dichiara da sé (per la serie 7300 di HP dice "Smart Tank 7300 series", non il nome commerciale né lo SKU), quindi il gateway non
può conoscere un nome più preciso. Ogni stampante collegata via USB mostra un badge accanto al nome: **IPP-USB** (servita dal ponte
ipp-usb) oppure **USB** (pilotata direttamente da CUPS). Il pulsante **Cerca ora** nella pagina Stampanti esegue subito una ricerca.
`CUPSPL_AUTO_DISCOVER=false` spegne tutto; `CUPSPL_USB_DIRECT=false` salta la strada 2.

**Stampanti scollegate.** Una coda sopravvive al cavo, quindi la scheda mostra **NON RAGGIUNGIBILE**, un avviso rosso e:

- un pulsante **Elimina coda** (qualunque stampante che non risponde, USB o di rete; chiede conferma; una stampante che risponde non
  si può eliminare da qui). Blocco, impostazioni della stampa di manutenzione e posizione nell'elenco della coda vengono dimenticati;
- per le **code USB** (ipp-usb o `usb://`), un **conto alla rovescia** ("verrà rimossa automaticamente tra 7:41:23 (2026-10-13 04:12) se
  la stampante non torna"). A zero il gateway elimina la coda da solo e scrive `printer.auto_remove` nell'audit degli amministratori
  (autore `system`); i dispositivi nuovi sono registrati come `printer.auto_add`. Se la stampante risponde di nuovo prima della fine il
  conto alla rovescia sparisce. L'attesa è `CUPSPL_OFFLINE_REMOVE_HOURS` (predefinito 8; `0` = mai).
- **le code di rete non vengono mai rimosse da sole**: una stampante spenta per il fine settimana deve ritrovarsi com'era.

Se la stampante viene ricollegata più tardi, viene semplicemente aggiunta di nuovo come stampante nuova.

## 3. Ordine dell'elenco

In **Stampanti**, nel modulo di stampa di `/me/print` e dovunque compaiano le code: **prima le stampanti fisiche, in ordine di
collegamento** (la più vecchia in alto); in fondo le **virtuali / di prova** (CUPS-PDF, `debugprinter0`…), anch'esse dalla più vecchia.

**Spostare le stampanti.** Ogni scheda ha una freccia su e una giù accanto agli altri pulsanti. Spostano la stampante di un posto nel **tuo**
elenco: ogni amministratore ha il proprio ordine, quindi se tu metti la stampante A prima della B un altro amministratore può continuare a
vedere la B prima della A. Lo stesso ordine vale nel tuo modulo di stampa (*Stampa*). Un pulsante è grigio e non cliccabile quando la
stampante è già a quel capo. Una stampante si muove solo dentro il suo gruppo: le fisiche restano sopra le virtuali. Dopo che hai spostato
una stampante il suo posto nel tuo elenco è fisso; una stampante collegata dopo va dopo quelle che hai già sistemato (nel suo gruppo). Gli
spostamenti sono registrati nell'audit degli amministratori (`printer.move`). Una stampante che non hai mai spostato segue l'ordine
predefinito descritto sotto.

**Rinominare una coda.** Il pulsante con la matita apre una finestra con il nome della coda (l'ultima parte dell'indirizzo,
`…/printers/<nome>`; lettere, cifre e `. _ @ + -`). CUPS non sa rinominare una coda, quindi il gateway crea la nuova sullo stesso dispositivo
— stesso driver (stampanti IPP: senza driver; USB: il driver che CUPS ha per quel modello; virtuali: CUPS-PDF), stessa descrizione e
posizione — e solo dopo toglie la vecchia; se qualcosa fallisce la vecchia resta. Blocco, nascondimento da mDNS, impostazioni della stampa di
manutenzione, conto alla rovescia e posizione negli elenchi seguono la coda; l'audit conserva il vecchio nome per ciò che è già successo.
Cliccando *Rinomina* si chiede conferma e si avverte che **i computer e i telefoni configurati a mano con il vecchio indirizzo smetteranno di
stampare** finché non vengono configurati di nuovo. Si rifiuta una coda con job in attesa, un nome già in uso o una coda di cui il gateway
non può conoscere il driver (per esempio una coda `socket://`). Le opzioni impostate a mano in CUPS (carta predefinita, …) non vengono
riportate. Registrata come `printer.rename`.

CUPS non dice quando una coda è stata creata: il gateway annota la **prima volta che la vede** (controlla ogni minuto, quindi una
stampante collegata e mai aperta in nessuna pagina viene comunque registrata entro un minuto). Le code già presenti quando la funzione è
stata introdotta risultano viste tutte nello stesso istante e restano in ordine alfabetico fra loro; una coda eliminata perde il posto
(una nuova con lo stesso nome va in fondo). L'annuncio mDNS non ha un database e resta alfabetico.

## 4. Stampa periodica di manutenzione (solo stampanti fisiche)

Una stampante ferma per settimane asciuga l'inchiostro e incolla i rullini. Il gateway può stampare da solo una piccola pagina di
manutenzione a intervalli regolari. Pulsante con la stampante e il timer, in alto a destra su ogni scheda (assente per le virtuali; il
server rifiuta comunque la richiesta).

- **Un'impostazione per stampante, uguale per tutti gli amministratori.**
- Il popup ha: un **interruttore di attivazione** accanto al titolo (agisce subito), l'**intervallo** (numero + ore/giorni, da 1 ora a 90
  giorni; suggerito 1 settimana, con scorciatoie), la **stampa a colori** (solo se la stampante dichiara il colore) e **Salva**, che
  registra i parametri **senza** attivare o disattivare il programma. La ✕ chiude senza cambiare nulla.
- Il conto parte dall'attivazione e poi dall'ultima pagina di manutenzione **riuscita**; le stampe normali degli utenti non lo azzerano.
- Se la stampante non risponde si riprova appena torna raggiungibile; se CUPS rifiuta il job si riprova dopo un'ora e l'errore resta
  visibile sulla scheda. Se il gateway era spento, la pagina parte appena riparte (l'intervallo perso non si recupera).
- La pagina va a CUPS con l'identità `gw:maintenance`: **non consuma quota**, **non compare nell'audit delle stampe** e **ignora il
  blocco della stampante e la modalità manutenzione** (serve alla salute dell'hardware). Chi accende, spegne o salva è nell'audit degli
  amministratori (`printer.keepalive_on/off/save`).

## 5. Stampa di prova con le statistiche

Pulsante con l'insetto: chiede conferma con **Annulla**, **Stampa bianco e nero**, **Stampa a colori** (disabilitato se la stampante non
ha il colore) e stampa le stesse statistiche della scheda (stato, inchiostro, contatori, dati del gateway, dettagli, scanner).
Registrata come `printer.test_print`. La pagina è A4 (il driver la adatta alla carta caricata). Le pagine che il gateway stampa da sé sono
sempre in inglese ([lingue.md](lingue.md)).

## 6. Blocco, nascondimento, manutenzione

- **Blocca una stampante** — non accetta job da nessuno, **amministratori compresi** (guasta o riservata). Per coda.
- **Nascondi da mDNS** — la stampante non viene più annunciata sulla rete; resta usabile con l'indirizzo.
- **Manutenzione del gateway** (pulsante rosso con la chiave inglese, in alto) — ferma stampa **e scansione** per tutti tranne gli amministratori e ritira ogni
  annuncio mDNS. Un banner rosso mostra lo stato su ogni pagina.

L'annunciatore mDNS interroga il gateway (`/mdns/policy`, autenticato da un codice derivato da `CUPSPL_SECRET_KEY`).

## 7. Stampanti di prova

In **Stampanti** un amministratore può creare ed eliminare **stampanti di prova** (`debugprinter0`, `1`, …): code CUPS-PDF che scrivono
PDF e non usano carta. Per quote e audit si comportano come una stampante — utile per provare il sistema — e stanno in fondo
all'elenco. Non hanno i pulsanti di manutenzione né di stampa di prova.

Una coda chiamata `virtual` si crea con `CUPS_VIRTUAL_QUEUE=1` per lo stesso scopo.
