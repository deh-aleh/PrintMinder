# Backup e ripristino

[Indice della documentazione](../README.md) · [English](../en/backup.md) · Italiano

Esistono due meccanismi indipendenti:

| | Backup integrati (portale) | `scripts/backup.sh` (lato host) |
|---|---|---|
| Chi | ogni amministratore, più uno *generale* | chi gestisce il server |
| Cosa | database (copia coerente mentre si stampa) e archivio audit; con la cifratura anche `gateway.env` e il certificato TLS | tutto questo **più** le code CUPS e `.env` |
| Quando | programmato, una volta al giorno | a mano |
| Serve per | la protezione di ogni giorno | **spostare la macchina** |

## 1. Backup integrati (menu *Backup*)

Ogni amministratore crea i **propri** backup programmati, con cartella, ora, numero di copie da tenere (ultime N giornaliere,
settimanali, mensili) e cifratura. Modifica ed elimina solo i propri; *Esegui ora* è disponibile a tutti. Il backup *Generale*
dell'installazione si mostra in sola lettura: si imposta in `config/gateway.env` (`CUPSPL_BACKUP_*`).

- Un backup è scritto in `.partial`, **riletto e verificato**, rinominato; solo dopo si tolgono le copie vecchie. *Esegui ora* aggiunge
  una copia senza cancellarne (la pulizia la fa la prossima esecuzione programmata).
- Se un backup è fallito, o l'ultimo ha più di 48 h, la pagina lo mostra in rosso.
- La rotazione riguarda solo i file con il nome dello stesso gateway e della stessa destinazione.
- Ogni file è `printgw-<istanza>-t<destinazione>-<ora UTC>.tar.gz` (più `.enc` se cifrato) con un `MANIFEST.json` (sha256 e dimensione
  di ogni parte, versione dell'app, revisione dello schema).
- Senza cifratura il file **non contiene segreti** (chiave TLS, `SECRET_KEY`, segreto RADIUS).

### Dove

Solo dentro `data/backups` (`BACKUP_DIR`, montata su `/backups`); un amministratore sceglie una sottocartella (lettere, cifre, spazio,
`. _ -` e `/`, al massimo 4 livelli) e non può uscirne (`..`, percorsi assoluti e link simbolici sono rifiutati). Per un NAS o un disco
USB montalo sul server **dentro quella cartella prima di avviare il gateway** (un montaggio fatto dopo richiede il riavvio del gateway, vedi sotto).

### Salvare su un disco di rete (NAS, SMB/CIFS, NFS) o su un disco USB

1. **Montalo sul server, dentro `data/backups`** (la cartella indicata da `BACKUP_DIR`). Usa `/etc/fstab` perché torni al riavvio, per esempio:

   ```
   # SMB/CIFS: uid/gid = PUID/PGID di .env, così il gateway può scrivere. La password in un file leggibile solo da root.
   //nas.lan/backups  /srv/printminder/data/backups/nas  cifs  credentials=/root/.nas-cred,uid=1000,gid=1000,vers=3.0,_netdev,nofail,x-systemd.automount  0 0
   # NFS: la cartella esportata deve essere scrivibile da quell'id utente (controlla "root squash" sul NAS)
   nas.lan:/export/backups  /srv/printminder/data/backups/nas  nfs  _netdev,nofail,x-systemd.automount,soft,timeo=100  0 0
   ```
2. Montalo **prima** di avviare il gateway. Un montaggio fatto dopo non è visto da un contenitore già in esecuzione: riavvialo
   (`docker compose restart gateway`).
3. Nel modulo del backup scrivi la sottocartella (`nas/...`) e spunta **«La cartella è un disco di rete o USB: scrivi solo se è montato»**
   *mentre il disco è montato*. Il gateway mette un piccolo file `.printminder-destination` e da quel momento **rifiuta il backup se il
   file non c'è**. Senza questo, un disco che non si monta lascia una cartella vuota sul disco del server e i backup la riempiono in silenzio
   (e non sono affatto fuori dalla macchina). Per il backup Generale usa `CUPSPL_BACKUP_REQUIRE_MARKER=true` e crea il file a mano una
   volta: `touch data/backups/nas/<cartella>/.printminder-destination`.

Comportamento del gateway con un disco di rete:

- Disco che non risponde: la pagina *Backup* si carica in circa 6 secondi e mostra il problema; un backup fallisce dopo 20 secondi
  con «Il disco dei backup non ha risposto…». Al massimo 4 richieste aspettano insieme su un disco morto; il resto del portale non ne risente.
- Con l'opzione del marker attiva, un disco non montato non riceve mai un file; il backup fallisce con «Il file segnaposto manca…».
- Un disco montato dopo l'avvio del gateway di default non viene visto. Riavvia il gateway, oppure monta la cartella con
  `bind: {propagation: rslave}` in `docker-compose.yml` (la cartella deve stare su un mount condiviso, che è il default con systemd).
- Su SMB/CIFS e in alcune configurazioni NFS i permessi dei file li decidono le opzioni di montaggio, **non** il gateway: il solito
  `chmod 600` non ha effetto e chiunque legga la condivisione legge i file. **Usa la cifratura** per i backup su una condivisione.
- Usa montaggi `soft` (NFS: `soft,timeo=100`; CIFS: `soft`), mai `hard`, così un NAS morto non blocca il server.
- Il backup è «fuori dalla macchina» solo se la condivisione sta su un'altra macchina. Un disco USB attaccato al server protegge da un disco rotto, non da un incendio.

### Cifratura

- **Passphrase** (consigliata; **non** la password dell'account: il gateway non la conosce, cambia, e per RADIUS non è dell'utente),
- **chiave di recupero** creata sul server (`cups-policy-admin backup-key`: la passphrase non passa dal portale),
- oppure **nessuna**.

Come funziona: si crea una sola volta una coppia di chiavi. La metà pubblica cifra ogni file (X25519 effimera + HKDF + AES-256-GCM a
blocchi di 1 MiB, ultimo blocco marcato); la metà privata è conservata **avvolta** da scrypt della passphrase e copiata
nell'intestazione del file, quindi *file + passphrase* bastano. Il gateway non conserva mai la passphrase: **senza di lei le copie non
si aprono**, nemmeno da un altro amministratore. La passphrase non è mai scritta nell'audit. Un nuovo file cifrato viene riletto con la
chiave appena usata.

## 2. Ripristino

```sh
docker compose stop gateway mdns
docker compose run --rm -it --no-deps gateway cups-policy-admin backup-restore /backups/<cartella>/<file>
docker compose up -d
```

Il vecchio database resta accanto come `gateway.db.before-restore-…`; i file di configurazione finiscono in `/data/restored-config` (da
copiare in `./config` su una macchina nuova). `backup-verify <file>` controlla un file senza ripristinarlo; `backup-run [--id N]` lancia
i backup a mano. Il ripristino è la via di ritorno dopo un aggiornamento che vuoi annullare.

## 3. Backup completo dal lato host

```sh
scripts/backup.sh backup [CARTELLA]        # scrive CARTELLA/printgw-AAAAMMGG-HHMMSS.tar.gz  (predefinito ./backups)
scripts/backup.sh restore FILE.tar.gz      # ferma prima il gateway e chiede conferma
```

Include il database (con la chiamata di backup di SQLite), `config/` (segreti compresi), `.env`, l'archivio audit e la configurazione
di CUPS (le code). Non include le immagini né lo spool dei job in corso. L'archivio contiene segreti: tienilo riservato quanto il server.
`restore` è provato solo a mano.

## 4. Limiti

Solo SQLite (con un altro database usa il suo strumento di dump); i backup integrati non includono le code CUPS (si ricreano da
`CUPS_QUEUES`, oppure si usa `scripts/backup.sh`); i file di configurazione non si ripristinano da soli (il contenitore li ha in sola
lettura); nessuna destinazione remota diretta (SSH/S3): si monta sul server; la passphrase non è recuperabile.
