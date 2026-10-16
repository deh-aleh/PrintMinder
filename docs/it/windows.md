# Stampare da Windows 11

[Indice della documentazione](../README.md) · [English](../en/windows.md) · Italiano

Guida passo passo per aggiungere una stampante del gateway a un PC Windows e stampare. Provata su Windows 11 Home 25H2: la stampante
è stata aggiunta al primo tentativo, Windows chiede le credenziali quando si stampa e ha una casella per ricordarle.

Servono tre cose: il **nome del server** (l'indirizzo del portale, per esempio `stampe.example.org`), il tuo **nome utente** e una
**chiave di stampa**. La chiave non è la password dell'account: è un testo lungo fatto solo per stampare.

## 1. Crea una chiave di stampa

1. Entra nel portale (`https://<server>:8631/`) e apri **Le mie chiavi di stampa** (`/me/keys`).
2. Crea una chiave. Scegli quanto dura e scrivi un'etichetta che dica per quale PC è (per esempio «PC ufficio»).
3. La pagina successiva mostra la chiave **una volta sola**: copiala in un posto sicuro (un gestore di password) prima di lasciare la
   pagina. Se la perdi, creane un'altra e revoca la vecchia.

## 2. Controlla che il PC si fidi del server

Il PC deve fidarsi del certificato del server. Se la tua organizzazione usa un certificato di un'autorità pubblica (per esempio
Let's Encrypt) non c'è nulla da fare. Con un'autorità privata o un certificato autofirmato, installa prima il file del certificato
(te lo dà l'amministratore): doppio clic → *Installa certificato* → *Computer locale* → *Colloca tutti i certificati nel seguente
archivio* → *Autorità di certificazione radice attendibili*. Senza questo passaggio Windows rifiuta la connessione prima di inviare
qualsiasi cosa e nel log del gateway non compare nulla.

## 3. Aggiungi la stampante

1. Apri *Impostazioni → Bluetooth e dispositivi → Stampanti e scanner → Aggiungi dispositivo*.
2. Dopo qualche secondo compaiono le stampanti del gateway, con il nome `<stampante> @ <nome del server>`. Clicca quella che vuoi e premi **Aggiungi**.
3. La stampante viene aggiunta e risulta pronta. Se Windows scrive «Sto connettendo…» per molto tempo, **aspetta fino a 3-4 minuti**.

Se non compare nessuna stampante:
- riavvia il PC;
- se non basta, in *Stampanti e scanner* trova *Modalità di stampa protetta di Windows*, attivala e disattivala, poi riprova;
- se non compaiono mai, di solito il PC e il server sono in reti diverse (VLAN) e l'annuncio non passa: chiedi all'amministratore un
  ripetitore mDNS, oppure aggiungi la stampante a mano (punto 6).

## 4. Stampa e inserisci le credenziali

1. Stampa da un programma qualsiasi, scegliendo la stampante aggiunta.
2. Windows chiede le credenziali:
   - **Nome utente**: il tuo nome utente del portale;
   - **Password**: la **chiave di stampa** del punto 1, non la password dell'account.
3. Spunta **Ricorda le credenziali**. Le stampe successive non chiedono più nulla.

Se non spunti la casella, Windows richiede le credenziali a ogni stampa.

## 5. Se la stampante non si collega

Se dopo 3-4 minuti la stampante non è ancora pronta, salva le credenziali prima di aggiungerla:

1. *Pannello di controllo → Account utente → Gestione credenziali → Credenziali Windows → Aggiungi credenziali Windows*.
2. **Indirizzo Internet o di rete**: lo stesso nome del server che usi per la stampante (per esempio `stampe.example.org`).
3. **Nome utente**: il tuo nome utente del portale. **Password**: la **chiave di stampa**.
4. Rimuovi la stampante dall'elenco in *Stampanti e scanner* e ripeti il punto 3.

## 6. Aggiunta a mano

Quando l'annuncio non arriva: *Aggiungi dispositivo → Aggiungi manualmente → Seleziona una stampante condivisa per nome* e incolla
`https://<server>:8631/printers/<coda>` (senza `:8631` se il server sta dietro a un proxy sulla porta 443). Windows sceglie da solo il
«Microsoft IPP Class Driver». Questa strada non è ancora stata provata fino alla stampa.

## 7. Dopo

- **Chiave scaduta o revocata**: le stampe vengono rifiutate con un errore di accesso. Crea una chiave nuova (punto 1) e sostituisci
  quella salvata: *Gestione credenziali → Credenziali Windows*, apri la voce, cambia la password. Da terminale: `cmdkey /list` elenca le
  voci e `cmdkey /delete:<voce>` ne toglie una.
- **Stampante rinominata dall'amministratore**: la vecchia voce smette di funzionare. Toglila e aggiungi quella nuova (punto 3).
- **Stampa rifiutata**: il portale ti dice perché nella campanella (`/me/notices`): quota raggiunta, stampante od orario non consentiti, e
  così via. Dal tuo profilo puoi chiedere più quota o un permesso ([guida-utente.md](guida-utente.md)).
