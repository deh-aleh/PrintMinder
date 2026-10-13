# Risoluzione dei problemi

[Indice della documentazione](../README.md) · [English](../en/troubleshooting.md) · Italiano

Prima di tutto, raccogli i fatti:

```sh
docker compose ps                                  # i servizi sono tutti su? cups è "healthy"?
docker compose logs --tail=100 gateway             # il log dell'applicazione
docker compose logs --tail=100 cups ipp-usb mdns
curl -sk https://<server>:8631/healthz             # 200 = gateway e database ok, 503 = no
```

Per più dettaglio metti `CUPSPL_LOG_LEVEL=DEBUG` in `config/gateway.env` e poi `docker compose up -d`.

## 1. Il gateway non parte

| Sintomo | Causa e rimedio |
|---|---|
| `refusing to start without TLS` | Manca il certificato. Esegui `scripts/docker-init.sh` o metti `fullchain.pem` + `privkey.pem` in `config/tls/`. |
| `refusing to start: set both CUPSPL_RADIUS_HOST and CUPSPL_RADIUS_SECRET, or neither` | RADIUS è configurato a metà. Compila entrambi o svuotali entrambi. |
| Permission denied su `config/tls/privkey.pem` | La chiave deve essere leggibile dall'utente `PUID:PGID` di `.env` (`chown`/`chmod 600`). |
| `Bind for 0.0.0.0:631 failed` | Un altro CUPS usa la 631. Tieni `GATEWAY_PORT=8631` oppure ferma l'altro servizio. |
| "archive folder not usable" | `data/audit-archive` deve essere scrivibile dall'utente del contenitore (stesso uid di `PUID`). |
| A ogni riavvio tutti escono dalle sessioni | `CUPSPL_SECRET_KEY` è vuota, quindi ne viene generata una casuale a ogni avvio. Impostala (lo fa `scripts/docker-init.sh`). |

## 2. Non riesco ad accedere

| Sintomo | Causa e rimedio |
|---|---|
| `docker compose logs gateway \| grep 'FIRST RUN'` non stampa nulla | Controlla in quest'ordine. **1.** `docker compose ps`: `gateway` deve essere *Up*; se si riavvia o si ferma, leggi `docker compose logs gateway \| tail -40`. **2.** La riga compare solo finché l'amministratore non ha una password. Se questa cartella è già stata usata, il database (il volume Docker `printgw_gateway-data`) ha ancora l'account con la vecchia password: il log dice allora *"administrator … already has a password"*; accedi su `https://<server>:8631/admin/login`, oppure imposta una password nuova con `docker compose exec -it gateway cups-policy-admin set-admin-password`. **3.** `CUPSPL_BOOTSTRAP_ADMIN=false` in `config/gateway.env` spegne l'account del primo avvio. Per ripartire davvero da zero (questo **cancella utenti, quote e audit**): `docker compose down -v`, poi `docker compose up -d`. |
| Bloccato dopo password sbagliate | 5 password *diverse* sbagliate in 5 minuti bloccano la coppia (utente, IP). Attendi 5 minuti o riavvia il gateway (il blocco è in memoria). |
| Un utente RADIUS non entra | RADIUS irraggiungibile ⇒ accesso negato (fail closed). Controlla `CUPSPL_RADIUS_*`, che questa macchina sia un *client* RADIUS con lo stesso secret, e il log. Un account locale con lo stesso nome **non** viene mai aperto dal RADIUS. |
| Obbligo di cambiare password | Normale per le password temporanee create o reimpostate da un amministratore. |
| Un utente disabilitato stampa ancora | Gli utenti locali sono bloccati subito. Per gli utenti RADIUS le chiavi di stampa smettono alla scadenza (`CUPSPL_KEY_TTL_DAYS_RADIUS`): revoca le loro chiavi nel portale per fermarli subito. |

## 3. Stampa

| Sintomo | Causa e rimedio |
|---|---|
| Il client chiede sempre la password | La **password di dominio non vale per stampare**: serve una chiave di stampa da *Profilo* (`CUPSPL_IPP_AUTH=keys`). Oppure la coppia (utente, IP) è bloccata. |
| `Forbidden` / HTML 426 da CUPS | La policy di CUPS non è quella del gateway: serve `docker/stack/cups/cupsd.conf` (`DefaultAuthType None`). |
| 502 dal gateway | CUPS fermo o `CUPSPL_CUPS_URL` errato. `docker compose logs cups`. |
| Job rifiutato con un messaggio di quota | L'utente ha raggiunto un limite; il messaggio contiene il link al portale per chiederne altra. Vedi [quote.md](quote.md). |
| "printer disabled…" / "gateway in maintenance…" | Un amministratore ha bloccato la stampante o ha attivato la manutenzione ([stampanti.md](stampanti.md)). Durante la manutenzione gli amministratori possono comunque stampare. |
| Un job resta `accepted` per sempre | Il riconciliatore non raggiunge CUPS: cerca `reconcile:` nel log. |
| La stampante risulta NON RAGGIUNGIBILE e manca nel modulo di stampa | Il dispositivo non risponde (spento, scollegato, USB in sospensione). Il rilevamento può ritardare fino a ~30 s. Per le code di rete è una prova TCP: non sa se manca la carta. |
| `:60000` non risponde | `ipp-usb` non gira o la stampante non è vista: `docker compose logs ipp-usb`; ricollega l'USB; assicurati che `ipp-usb`/SANE **dell'host** siano fermati e mascherati. |
| Una stampante USB nuova non compare | Attendi fino a un minuto o premi **Cerca ora** in Stampanti. Controlla `docker compose logs gateway \| grep discovery`. Se la pagina dice "CUPS non ha un driver", il modello non ha driver nell'immagine `cups` (aggiungine uno in `docker/stack/cups/Dockerfile`). Assicurati che `ipp-usb`/SANE **dell'host** siano fermati e che `CUPSPL_AUTO_DISCOVER` non sia `false`. |
| Una stampante scollegata è ancora in elenco | Mostra NON RAGGIUNGIBILE con un conto alla rovescia (code USB, `CUPSPL_OFFLINE_REMOVE_HOURS`, default 8 h) e un pulsante **Elimina coda**. Le code di rete non vengono mai tolte da sole. |
| La coda non è stata creata | `CUPS_QUEUES` è sbagliato o la stampante ha risposto tardi. L'entrypoint riprova per 5 minuti; altrimenti `docker compose exec cups lpadmin -p NOME -E -v URI -m everywhere`. |
| Un "Create-Job" senza documento tiene la quota | La quota si libera solo quando CUPS lo annulla (di default dopo 3 h). |
| Limite pagine superato di un file | Il limite è *morbido* per i file di cui non si contano le pagine (formato sconosciuto, PDF cifrato, oltre 64 MB): vedi [limiti.md](limiti.md). |
| Stampa da browser: "file non supportato" | Si accettano solo PDF, JPEG, PNG, GIF e testo semplice, riconosciuti dal contenuto e non dal nome del file. |
| Stampa da browser: "più grande di N MB" | `CUPSPL_WEB_UPLOAD_MB` (predefinito 25). |

## 4. Telefoni e computer

| Sintomo | Causa e rimedio |
|---|---|
| Avviso sul certificato, o il dispositivo rifiuta di collegarsi | Il dispositivo non si fida del certificato. Installa la CA, oppure usa un certificato firmato da una CA in `config/tls/`. Il nome o l'IP usato deve stare nel certificato. |
| Le stampanti non compaiono sul telefono | `mdns` deve girare con la rete host sulla stessa LAN; `docker compose logs mdns`. Imposta `CUPSPL_MDNS_ADDRESSES` se la macchina ha più schede di rete e `CUPSPL_MDNS_HOSTNAME` con un nome presente nel certificato. Docker Desktop non può farlo. Una stampante nascosta, irraggiungibile, o la modalità manutenzione, tolgono anche l'annuncio. |
| Android: il servizio di sistema vede la stampante ma fallisce | Non sa autenticarsi. Installa **Mopria Print Service** o stampa dal portale. |
| Il desktop Linux mostra le stampanti ma non stampa | Le stampanti annunciate non hanno la chiave finché non aggiungi la coda con la chiave nell'indirizzo (pagina del profilo o `scripts/add-printer-linux.sh`). |
| Windows / macOS / iPhone | Non provati dal progetto. Prova `ipps://<server>:8631/printers/<coda>`, nome utente + chiave di stampa, e segnala cosa succede. |

## 5. Scansione

| Sintomo | Causa e rimedio |
|---|---|
| Nessuno scanner nel portale | Gli scanner si trovano se rispondono a eSCL sulla porta IPP della coda o sulla 80. Altrimenti aggiungi `CUPSPL_SCAN_URL=nome=http://host:porta`. Uno scanner scollegato sparisce in ~30 s. |
| "scanner occupato" | Un'altra scansione è in corso, o il client non ha cancellato il job eSCL precedente. Il gateway riprova 3 volte se il dispositivo si sta svegliando. |
| Pagina bianca dal caricatore | Il caricatore dormiva e si dichiarava vuoto, quindi *Automatico* ha usato il vetro. Scegli *Caricatore* esplicitamente o rimetti i fogli. |
| NAPS2 riceve 401 senza finestra | Non sa inviare le credenziali. Imposta `CUPSPL_ESCL_ANONYMOUS=true` (solo su reti fidate) e inserisci IP e porta a mano. |
| Il risultato della scansione è sparito | I risultati restano 15 minuti in memoria, solo per il proprietario. |

## 6. Backup e audit

| Sintomo | Causa e rimedio |
|---|---|
| Il backup è rosso | È fallito o l'ultimo ha più di 48 h. Apri la pagina per il motivo; di solito la cartella non è scrivibile o il disco è pieno. |
| "Folder name not valid…", "Folder is outside the backup root", "Folder … is not writable by the gateway" | La cartella di un backup deve essere una sottocartella di `/backups` (sull'host `data/backups`) e scrivibile dall'utente `PUID`. Un disco USB o una cartella di rete va montata sull'host *dentro* quella cartella **prima** di avviare il gateway (riavvia il gateway dopo il montaggio). |
| Passphrase persa | I backup cifrati non si aprono senza (non esiste un reset). Crea una nuova chiave di recupero (`backup-key`) per i backup futuri. |
| Ripristino | Ferma `gateway` e `mdns`, poi `docker compose run --rm -it --no-deps gateway cups-policy-admin backup-restore /backups/<cartella>/<file>`, poi `docker compose up -d`. Controlla prima il file con `backup-verify`. |
| Il database è grande | L'audit non si cancella mai: viene archiviato in `data/audit-archive` quando supera `CUPSPL_AUDIT_MAX_MB`. Abbassa il valore per archiviare prima. |

## 7. Lingua del portale

| Sintomo | Causa e rimedio |
|---|---|
| Le pagine sono in inglese ma ti aspettavi l'italiano | L'ordine è: scelta dell'utente → lingua del browser → `CUPSPL_LANGUAGE` → inglese. Imposta `CUPSPL_LANGUAGE=it` o scegli la lingua in *Impostazioni*. |
| Qualche testo non è tradotto | I testi che arrivano dalla stampante (nomi degli inchiostri, firmware, avvisi del dispositivo) o da CUPS si mostrano come arrivano. I motivi nell'audit sono in inglese di proposito. |
| I caratteri cinesi sono quadratini | Sul computer *del browser* manca un font CJK. |
| Le pagine di prova o di manutenzione stampate sono in inglese | È voluto: russo e cinese richiederebbero un font PDF incorporato ([lingue.md](lingue.md)). |

## 7b. Aggiornamenti

| Sintomo | Causa e rimedio |
|---|---|
| `scripts/env-sync.sh` scrive `No module named app.envsync` | Lo script è partito dentro un'immagine del gateway costruita prima che questa cartella ricevesse il codice nuovo (l'immagine non contiene `app/envsync.py`). Gli script recenti usano il Python della cartella se c'è `python3`; se lo vedi ancora, esegui `docker compose build gateway` (o `scripts/update.sh` per le immagini pubblicate) e riprova. |
| Dopo `git pull` le opzioni nuove non sono in `.env` o `gateway.env` | Un pull cambia la cartella, non i tuoi due file. Esegui `scripts/env-sync.sh` (prima con `--check` per vedere cosa verrebbe aggiunto). |
| `scripts/update.sh` dice `PRINTGW_REGISTRY is empty` | Le immagini si costruiscono da questa cartella: aggiorna con `git pull && docker compose up -d --build`, poi `scripts/env-sync.sh`. |

## 8. Ancora bloccato

Prima di chiedere aiuto raccogli `docker compose logs gateway`, `docker compose ps`, l'esito di `/healthz`, la versione del gateway
(`PRINTGW_VERSION` o il commit) e ciò che mostrava la pagina. Non incollare mai `config/gateway.env`, `.env` o la chiave TLS.
