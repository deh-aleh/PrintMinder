# Guida per l'amministratore

[Indice della documentazione](../README.md) · [English](../en/admin-guide.md) · Italiano

Per chi gestisce l'installazione. Il portale è su `https://<server>:8631/admin`. Il menu in alto:

| Menu | Pagina | Cosa ci fai |
|---|---|---|
| **Audit** | `/admin/jobs` | Chi ha stampato o scansionato cosa; filtri, CSV, annullare job in coda → [audit.md](audit.md) |
| **Utenti** | `/admin/users` | Crea utenti locali o RADIUS, modifica, reimposta la password, revoca le chiavi, elimina |
| **Gruppi** | `/admin/groups` | Crea, rinomina, limiti, "richiedibile", elimina |
| **Richieste** | `/admin/requests` | Approva, modifica o rifiuta le richieste di quota e di gruppo (contatore = in attesa) → [quote.md](quote.md) |
| **Concessioni** | `/admin/grants` | Dai o revochi quota extra direttamente |
| **Azioni** | `/admin/actions` | Chi ha fatto cosa nel portale |
| **Stampanti** | `/admin/printers` | Stato, inchiostro, contatori; blocco, nascondimento, rinomina, sposta su/giù (il tuo ordine), stampanti di prova, stampa periodica e di prova → [stampanti.md](stampanti.md) |
| **Backup** | `/admin/backups` | I tuoi backup programmati → [backup.md](backup.md) |
| **Archivio** | `/admin/archive` | Audit vecchio compresso, consultabile e scaricabile |
| **Stampa / Scansiona / Profilo** | `/me…` | Le stesse pagine degli utenti → [guida-utente.md](guida-utente.md) |
| **Logo, nome e (utente)** | `/me/settings` | Il blocco in alto a sinistra apre le impostazioni: tema, lingua, aggiornamento |
| **Campanella** (solo amministratori) | `/admin/notices` | Cose che il gateway ha notato (il numero indica quelle aperte), vedi «Avvisi» sotto |
| **Manutenzione** (chiave inglese rossa) | — | Ferma stampa e scansione per tutti tranne gli amministratori |
| **Porta con freccia** | — | Esci |

## 1. Primi passi

1. Imposta la password di `cups_orchestrator` con il codice monouso ([installazione.md](installazione.md#36-primo-amministratore)).
2. Crea il **tuo** account amministratore (Utenti → crea → amministratore) e usa quello ogni giorno; tieni `cups_orchestrator` per le emergenze.
3. Modifica i limiti del gruppo **default** (Gruppi) e crea gruppi per chi ha bisogno di limiti diversi.
4. Crea gli utenti, o lascia entrare quelli RADIUS. Di' a tutti di creare una chiave di stampa ([guida-utente.md](guida-utente.md)).
5. Imposta un backup ([backup.md](backup.md)).

## 2. Utenti

L'elenco è in sola lettura: limite proprio o ereditato (in corsivo), concessioni attive come `+N` colorato, consumo e chiavi attive.
**Modifica** apre la pagina con tutti i campi, **origine** compresa (locale ↔ RADIUS), ed **Elimina** (scrivi il nome per confermare).

- Crea **locale**: si mostra una password temporanea una volta; l'utente la cambia al primo accesso.
- Crea **RADIUS**: scegli il gruppo; la persona entra con la password d'ufficio.
- **Reimposta password** (locale): nuova password temporanea, mostrata una volta.
- **Revoca chiavi**: blocca subito la stampa da ogni dispositivo di quell'utente; l'elenco delle chiavi per utente è in `/admin/users/<id>/keys`.
- **Flag admin**: la promozione sposta l'utente nel gruppo `administrator`, il declassamento in `default`.
- Protetti: non puoi disattivare, declassare o eliminare te stesso, l'account di emergenza o l'ultimo amministratore.

Eliminare conserva lo storico ([account.md](account.md#7-eliminare-un-utente)).

## 3. Gruppi e limiti

Un gruppo ha dei limiti (job / pagine, settimanali / mensili) e un flag **richiedibile**. I gruppi di sistema `default` e `administrator`
non si eliminano; eliminare un altro gruppo sposta i suoi utenti in `default`. I limiti personali si impostano nella pagina di modifica
dell'utente. Dettagli in [quote.md](quote.md).

## 4. Richieste e concessioni

Esamina le richieste (modifica quantità o tipo prima di approvare, aggiungi una nota). L'approvazione è idempotente. In **Concessioni**
vedi quelle attive e le revochi; puoi crearne una direttamente con un motivo. Tutto viene registrato.

## 5. Stampanti

Blocca una stampante (nessuno stampa, amministratori compresi), nascondila da mDNS, crea stampanti di prova, imposta la stampa periodica
di manutenzione, invia una stampa di prova con le statistiche, attiva la **manutenzione del gateway** (pulsante rosso con la chiave inglese). Vedi
[stampanti.md](stampanti.md).

## 6. Audit e archivio

Usa i filtri e l'esportazione CSV; annulla i job in coda; leggi i file archiviati; verifica la loro integrità. Nulla si può cancellare
([audit.md](audit.md)).

## 7. Riga di comando (`cups-policy-admin`)

Dentro il contenitore: `docker compose exec gateway cups-policy-admin <comando>` (aggiungi `-it` quando chiede una password).

| Comando | Scopo |
|---|---|
| `set-admin-password [utente]` | crea o aggiorna un amministratore **locale** (predefinito `cups_orchestrator`) e ne imposta la password |
| `make-admin <utente>` | concede i diritti di amministratore (crea l'utente se serve) |
| `set-group <utente> <gruppo>` | sposta un utente in un gruppo (lo crea) |
| `group-limit <gruppo> <limite\|none> [--period weekly\|monthly] [--metric jobs\|pages]` | imposta un limite di gruppo; `none` lo toglie |
| `user-limit <utente> <limite\|none> [--period …] [--metric …]` | imposta un limite personale |
| `jobs [-n N]` | mostra le ultime righe dell'audit (e avvisa se esistono archivi) |
| `audit-archive [--force]` | archivia subito le righe vecchie dell'audit |
| `backup-key` | crea una chiave di recupero dei backup da una passphrase |
| `backup-run [--id N]` | esegue subito i backup abilitati |
| `backup-verify <file>` | controlla un file di backup |
| `backup-restore <file>` | ripristina database e file dell'audit (ferma prima il gateway) |

## 7b. Avvisi (la campanella)

La campanella nella barra in alto (solo amministratori) elenca ciò che il gateway ha notato e nessuno ha chiesto. Ogni avviso mostra
l'ultima volta, la fonte e quante volte è successo; *Chiudi* lo chiude (la chiusura resta registrata in *Azioni*).
Oggi esiste un solo tipo: una richiesta di scansione senza nome utente e password rifiutata perché `CUPSPL_ESCL_ANONYMOUS` è spento.

Perché un client che riprova 100 volte non riempia l'elenco, lo stesso avviso dalla stessa fonte viene scritto di nuovo solo dopo un
intervallo; le ripetizioni nel frattempo vengono contate. L'intervallo dipende da `CUPSPL_LOG_LEVEL` e lo stesso testo viene scritto
nel log del container con lo stesso limite:

| `CUPSPL_LOG_LEVEL` | Stesso avviso, stessa fonte, segnalato di nuovo dopo |
|---|---|
| `DEBUG` | 1 minuto |
| `INFO` (predefinito) | 1 giorno |
| `WARNING` | 3 giorni |
| `ERROR` | 7 giorni |

`CUPSPL_NOTICE_INTERVAL` (secondi) sostituisce la tabella. Si tengono al massimo 200 avvisi aperti per tipo; quelli chiusi vengono rimossi dopo 90 giorni.

## 8. Operatività

- Salute: `GET /healthz` → 200 o 503, corpo `{"status":"ok"}`. Non richiede login. `CUPSPL_HEALTHZ_INFO=version,printers` aggiunge la versione e il numero di code (usb / rete / virtuali / totale); il predefinito è solo lo stato. Log: `docker compose logs gateway`.
- Le migrazioni partono da sole all'avvio. Fai un backup prima di aggiornare un database importante.
- Aggiornamenti: in cima al portale compare un avviso quando esiste una release più nuova. Aggiorna con `scripts/update.sh`, oppure con il pulsante *Aggiorna* nel menu *Backup* quando gira il contenitore facoltativo updater e c'è un backup programmato funzionante ([installazione.md](installazione.md#aggiornamenti)).
- Non lasciare account o stampanti di prova su un'installazione vera.
- Proteggi `config/`, `.env`, `data/` e il volume: contengono segreti e dati personali.
