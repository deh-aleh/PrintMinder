# Quote, richieste e concessioni

[Indice della documentazione](../README.md) · [English](../en/quotas.md) · Italiano

## 1. Limiti

Una **regola** dice: *questo utente o questo gruppo può stampare al massimo N **job** (o **pagine**) per **settimana** (o **mese**)*.

- Le regole appartengono a un gruppo, con **override per utente** facoltativi. Una regola utente sostituisce quella del gruppo per la
  stessa metrica.
- Metriche: **job** e **pagine**. Periodi: **settimanale** (lunedì–domenica) o **mensile** (mese di calendario), nel fuso
  `CUPSPL_TIMEZONE`, anche attraverso il cambio dell'ora legale.
- Nessuna regola = nessun limite.
- Dove si impostano: *Gruppi* → modifica (limiti del gruppo), *Utenti* → modifica (limiti personali), oppure la CLI:
  `cups-policy-admin group-limit staff 20 --period monthly`, `cups-policy-admin user-limit mario 5 --metric pages`
  (`none` toglie un limite).

### Cosa conta

Contano i job nello stato `accepted`, `completed` o `held`. **I job rifiutati, falliti e annullati prima della stampa non consumano
quota.** L'utente vede consumo e prossimo azzeramento in *Profilo*.

### Pagine contate prima di stampare

Quando a un utente si applica un limite di pagine, il gateway legge il documento **prima** di stamparlo (fino a 64 MB) e ne conta le pagine:
PDF (pypdf), JPEG/PNG/GIF = 1, URF dall'intestazione, PostScript da `%%Pages`, testo semplice ≈ 60 righe per pagina; poi moltiplica per
le copie e per l'intervallo di pagine scelto. Se `usate + pagine > limite` il job è **rifiutato subito**:

> `would be exceeded (used 90, this document 200, limit 100)`

Altrimenti le pagine sono registrate al momento, così i job simultanei le vedono. Dopo la stampa il riconciliatore sostituisce la stima
con le **pagine reali** lette da CUPS. Un job con pagine non ancora note vale almeno 1 pagina.

### Il limite morbido (importante)

Il limite pagine è **rigido** solo per i documenti che il gateway sa contare. È **morbido** in questi casi:

- formato sconosciuto, **PDF cifrato** o file oltre 64 MB: il job che supera il limite *viene stampato* e le sue pagine reali
  bloccano poi i successivi;
- un job inviato con `Create-Job` + `Send-Document`: le pagine si contano al `Send-Document`, quando il job è già stato accettato;
- un `Create-Job` senza documento libera la quota solo quando CUPS lo annulla (di default dopo 3 ore).

### Riserva atomica

Il controllo del limite e la registrazione del job avvengono sotto lock (thread + `BEGIN IMMEDIATE` su SQLite), quindi molti job simultanei non possono superare il limite. Le concessioni attive si sommano al limite **dentro** lo stesso controllo.

## 2. Richieste degli utenti

In *Profilo* un utente può chiedere:

1. **Più quota** — sceglie la metrica, la quantità, **temporanea** o **permanente**, e scrive un motivo. Può chiedere solo le metriche
   che hanno davvero un limite. Il **periodo non lo sceglie lui**: è quello della regola impostata dall'amministratore; il modulo lo
   mostra in sola lettura ("il tuo limite pagine è mensile: la deroga durerà fino al 1 novembre").
2. **Cambio di gruppo** — solo verso gruppi marcati *richiedibili*.

Freni: al massimo `CUPSPL_MAX_OPEN_REQUESTS` (3) richieste aperte per utente, il motivo è obbligatorio (sempre trattato come testo),
le richieste scadono dopo `CUPSPL_REQUEST_TTL_DAYS` (14). L'utente può annullare una richiesta in attesa.

## 3. Approvazione e concessioni

Gli amministratori vedono le richieste in attesa in **Richieste** (con un contatore nel menu) e possono **approvarle, modificarle o
rifiutarle**. Approvando possono cambiare quantità e tipo (anche trasformare una permanente in temporanea) e aggiungere una nota.

L'approvazione produce una **concessione** che si **somma** al limite:

`limite effettivo = regola + concessioni attive`

- Una concessione **temporanea** vale fino alla fine della finestra del periodo **in cui avviene l'approvazione** (non quella della
  richiesta: una richiesta fatta domenica sera e approvata lunedì non deve nascere già scaduta).
- Una concessione **permanente** si applica a ogni periodo successivo ("+20 pagine ogni mese") finché non viene revocata.
- Il cambio di gruppo sposta subito l'utente; da quel momento valgono i limiti del nuovo gruppo.
- L'approvazione è **idempotente**: un solo `UPDATE` condizionale, quindi due amministratori o un doppio clic concedono una volta sola.
- Le concessioni non toccano mai lo storico (`job_log` non viene modificato).

Gli amministratori possono anche concedere o revocare quota direttamente in **Concessioni**. Tutto finisce nell'audit degli
amministratori ([audit.md](audit.md)). L'elenco utenti mostra le concessioni attive come `+N` colorato.

## 4. Motivi mostrati agli utenti

Quando un job è rifiutato, il client IPP riceve il motivo in inglese più l'indirizzo del portale per chiedere una deroga. Il portale
mostra la stessa frase tradotta ([lingue.md](lingue.md)). L'audit conserva il motivo in inglese.
