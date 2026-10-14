# Protezione dei dati: nomi dei file, cifratura e retention

[Indice della documentazione](../README.md) · [English](../en/data-protection.md) · Italiano

PrintMinder tiene un registro di chi ha stampato e scansionato cosa ([audit.md](audit.md)). Il **nome del file** («Licenziamento_Rossi.pdf»,
«Referto_medico.pdf») può dire molto di una persona, quindi va trattato come un dato personale. Questa pagina spiega cosa è protetto, cosa no, e
cosa puoi fare per ridurre i dati che il server conserva.

## 1. Cosa è protetto e cosa no

| Dato | Come è conservato |
|---|---|
| **Nome del file** stampato o scansionato | **Cifrato** nel database, nell'archivio audit (i file `.jsonl.gz`) e quindi anche nei backup |
| Password degli account locali | Solo l'impronta (hash argon2): la password non si può ricavare |
| Chiavi di stampa | Solo l'impronta (sha256) |
| Nome utente, gruppi, nomi delle stampanti, registro delle azioni degli amministratori, motivi delle richieste di quota, indirizzi IP | **In chiaro** nel database |
| Quantità (pagine, data, stato di ogni stampa) | In chiaro: servono alle quote |
| Il database come file | Non cifrato: chi copia il file legge tutto tranne i nomi dei file |
| I backup | Cifrati solo se scegli la cifratura nel menu *Backup* (consigliata) |

**Esempio.** Un ladro copia il file del database dal server. Vede chi ha stampato quante pagine e quando, ma al posto dei nomi dei file trova testo senza senso
(`enc1:Q3x…`). Se invece ruba il disco intero con la chiave in `.env`, può leggere tutto: per questo la misura principale è cifrare il disco (§5).

## 2. Il pulsante «Nomi dei file» (verde / rosso)

In *Amministrazione → Audit* (`/admin/jobs`), in alto a destra, c'è un pulsante con un pallino:

- **pallino verde — «Nomi dei file: salvati»**: ogni stampa e scansione registra il nome del file (è il comportamento normale);
- **pallino rosso — «Nomi dei file: non salvati»**: le nuove stampe e scansioni compaiono nell'audit **senza il nome del file**. Restano chi, quando, quante pagine, su quale stampante e com'è andata, quindi le quote funzionano come prima.

Cliccando per spegnerlo compare una domanda di conferma. I nomi **già salvati restano**; quelli nuovi non vengono più scritti. Cliccando di nuovo si torna a salvarli.
La scelta viene registrata nel registro delle azioni degli amministratori.

**Esempio.** In un ufficio legale gli avvocati non vogliono che si sappia quali documenti stampano. L'amministratore spegne il pulsante: da quel momento nell'audit si vede
«Mario, 12 pagine, ieri alle 15:03» ma non cosa.

## 3. Dimenticare i nomi vecchi: la retention

Se vuoi che i nomi spariscano dopo un po', accendi la retention in `.env` (poi `docker compose up -d`):

| Impostazione | Cosa | Predefinito |
|---|---|---|
| `CUPSPL_JOB_TITLE_RETENTION_ENABLED` | `true` accende la cancellazione dei nomi vecchi | `false`: **nessuna retention**, i nomi restano |
| `CUPSPL_JOB_TITLE_RETENTION_DAYS` | Dopo quanti giorni il nome viene cancellato | `90` |

Una volta al giorno il gateway cancella il nome dalle righe più vecchie del numero di giorni scelto. **La riga resta** (chi, quando, pagine, stato): servono alle quote e ai conteggi.

**Cosa non viene toccato.** I file dell'archivio audit già scritti sono immutabili (così si può dimostrare che non sono stati cambiati) e li lasciamo com'erano: i nomi che
contengono restano, cifrati. Da quando accendi la retention, i file nuovi dell'archivio non contengono più i nomi delle righe oltre il limite.

## 4. La chiave: non cambiare `CUPSPL_SECRET_KEY`

I nomi sono cifrati con una chiave ricavata da `CUPSPL_SECRET_KEY` (in `.env`, creata da `scripts/docker-init.sh`).

> **Se cambi o perdi `CUPSPL_SECRET_KEY`, i nomi già salvati non si leggono più**: al loro posto il portale mostra `[encrypted]`. Il resto continua a funzionare
> (le sessioni si azzerano e tutti rifanno il login). Ripristinando la vecchia chiave i nomi tornano leggibili.

- I backup **cifrati** includono `.env`, quindi anche la chiave; quelli non cifrati no (e senza la chiave i nomi che contengono non si leggono: è voluto).
- Se la chiave è vuota il gateway non cifra niente (e avvisa nel log), perché una chiave diversa a ogni avvio renderebbe i nomi illeggibili al riavvio dopo.
- Se prima avevi dei nomi in chiaro, al primo avvio con la chiave il gateway li cifra da solo, a pezzi, senza fermarsi.

**La ricerca per nome file** nell'audit guarda nelle ultime 5.000 azioni che rispettano gli altri filtri (i nomi sono cifrati: per cercare si aprono uno a uno). La
ricerca per utente non ha questo limite.

## 5. Cifrare il disco (la misura principale)

Cifrare i nomi dei file protegge un database copiato da solo. Per proteggere **tutto** (utenti, gruppi, audit, chiavi, certificato) il modo giusto è cifrare il disco del server:
se qualcuno porta via il computer, senza la password di sblocco vede solo dati senza senso. Lo fa il sistema operativo, non PrintMinder (dentro un contenitore non può farlo).

**Il modo più semplice: cifrare tutto il disco quando installi Linux.** Gli installer di Ubuntu e Debian hanno una casella *«Cifra la nuova installazione»* / *«Encrypt the new installation»* (usa LUKS, lo standard di Linux).
Si sceglie una password. Ricordati che a ogni accensione il server la chiede: un server senza tastiera né schermo ha bisogno di un modo per inserirla.

**Se il server è già installato e non puoi reinstallarlo:** la cifratura va fatta su un disco o una partizione vuoti, con `cryptsetup`. Attenzione: `luksFormat` **cancella tutto** quello che c'è
sul disco indicato. Sono tre posti da mettere sul disco cifrato:

| Cosa | Dove sta | Perché |
|---|---|---|
| Il database | nel volume Docker `gateway-data`, dentro la cartella dei dati di Docker (di solito `/var/lib/docker`) | contiene utenti, gruppi, quote, audit |
| `data/` | nella cartella di PrintMinder | archivio audit e backup |
| `config/` e `.env` | nella cartella di PrintMinder | chiave TLS e segreti |

Per spostare la cartella dei dati di Docker sul disco cifrato (`data-root` in `/etc/docker/daemon.json`) e per far partire Docker solo dopo lo sblocco ci vuole un po' di pratica di Linux:
se non l'hai mai fatto, preferisci la reinstallazione con il disco cifrato.

**I backup.** Cifrali sempre (passphrase o chiave di recupero, menu *Backup*): un backup non cifrato contiene l'intero database, e finisce spesso su un disco di rete non protetto.

## 6. Un'ultima cosa: la cronologia di CUPS

Oltre all'audit di PrintMinder, **CUPS** (il programma di stampa che sta dietro) tiene da parte la cronologia degli ultimi job (fino a 2.000, impostazione `MaxJobs`),
con il nome del documento, nel volume Docker `printgw_cups-spool`. Non conserva il contenuto dei documenti (`PreserveJobFiles No`), ma conserva i nomi.
Il pulsante e la retention di questa pagina **non** toccano quella cronologia: i nomi più vecchi spariscono da soli quando i job superano il limite. Se ti serve
cancellarli subito, ferma lo stack, elimina quel volume e riavvia:

```sh
docker compose down
docker volume rm printgw_cups-spool
docker compose up -d
```

Le code delle stampanti non si perdono (stanno nel volume `cups-config`). Se hai più installazioni o hai dato un altro nome al progetto compose, il nome del volume cambia: controllalo con `docker volume ls`.
