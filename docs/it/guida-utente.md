# Guida per l'utente

[Indice della documentazione](../README.md) · [English](../en/user-guide.md) · Italiano

Per chi stampa e scansiona. Tutto sta in `https://<server>:8631/me` (gli amministratori arrivano su `/admin`; il menu collega entrambe).

## 1. Accesso

Apri il portale ed entra con l'account che ti ha dato l'amministratore (password locale), oppure con le credenziali d'ufficio se
l'installazione usa RADIUS. Una password temporanea va cambiata al primo accesso.

## 2. Il mio profilo (`/me`)

- **Consumo**: job e pagine usati nella settimana o nel mese in corso, il tuo limite (compresa l'eventuale quota extra concessa) e
  quando si azzera.
- **Chiavi di stampa**: crea una chiave per ogni dispositivo (dagli un'etichetta). Si mostra **una volta**: copiala subito (pulsante
  copia). Usala come password quando il computer o il telefono chiede le credenziali; il nome utente è il tuo. Una chiave serve solo a
  stampare e scansionare — non apre mai il portale e la tua password di dominio non serve mai su un dispositivo. Revoca una chiave (o
  tutte) in *Le mie chiavi* se perdi un dispositivo. Quando la crei scegli per quanto tempo vale (da 1 mese a 2 anni, o una sola stampa); gli utenti RADIUS hanno un massimo più corto e la rinnovano rifacendo il login nel portale. La campanella in alto ti dice quando un amministratore revoca, disattiva o prolunga una tua chiave.
- **Richieste**: chiedi più quota (temporanea o permanente), il cambio di gruppo o un permesso (vedi sotto), con un motivo. L'amministratore approva, modifica o
  rifiuta. Puoi avere fino a 3 richieste aperte e annullarle.

- **I tuoi permessi**: se puoi stampare a colori e solo fronte, su quali stampanti e in quali orari. Se non puoi stampare a colori, le tue
  stampe escono in bianco e nero; se non puoi stampare solo fronte, escono in fronte-retro. La scansione non cambia.
  Accanto a ciò che ti manca c'è il link **Chiedi** (e **Chiedi un'altra stampante**): scegli cosa ti serve, scrivi perché, e un
  amministratore risponde. Finché la richiesta aspetta, al posto del link c'è «(richiesta in attesa)». La risposta può essere per sempre o fino a una data; la campanella ti dice quando la richiesta è approvata,
  rifiutata o finita, e il riquadro mostra i permessi che ti sono stati concessi e fino a quando.

Se una stampa viene rifiutata per la quota, il messaggio contiene il link per chiedere una deroga. Se viene rifiutata per i tuoi
permessi (una stampante che non puoi usare, un'ora fuori dai tuoi orari, oppure colore / solo fronte quando l'installazione rifiuta
invece di correggere), il messaggio rimanda a questa pagina, e la campanella ti dice cos'è successo e cosa cambiare. Anche quando una
stampa esce in bianco e nero o in fronte-retro a causa dei tuoi permessi, la campanella te lo dice.

## 3. Stampa (`/me/print`)

Carica un PDF, una foto (JPEG, PNG, GIF) o un testo. Scegli la stampante (compaiono solo quelle che puoi usare), il formato carta, l'orientamento, colore o bianco e nero (solo se puoi stampare a colori), solo fronte o fronte-retro (solo se puoi stampare solo fronte e la stampante ha l'unità fronte-retro), un intervallo
di pagine (`1,5` o `2-4`), le copie e un commento facoltativo (50 caratteri, visibile agli amministratori accanto al nome del file).
Stessa quota e stesso audit di ogni altra stampa. Funziona da un telefono senza installare nulla. Per collegare un computer vedi
[stampa.md](stampa.md).

## 4. Scansione (`/me/scan`)

Scegli lo scanner (se ce n'è più di uno), la sorgente (automatica, vetro o caricatore per tutti i fogli), il colore, la qualità, il
formato carta, il formato di uscita (PDF o JPEG) e un nome per il file. Puoi lasciare la pagina mentre scansiona e tornare a scaricare
il file entro 15 minuti. Vedi [scansione.md](scansione.md).

## 5. Impostazioni (clic sul tuo nome, in alto a destra)

- **Tema**: chiaro, scuro o automatico.
- **Lingua**: English, Italiano, Español, Русский, 中文. Salvata con il tuo account.
- Intervallo di **aggiornamento automatico** della pagina Audit (amministratori); le pagine Audit e Stampanti hanno anche un interruttore *Aggiornamento automatico*.
- **Cambio password** (account locali).

## 6. Da sapere

- La quota conta i job accettati, completati e trattenuti; quelli rifiutati, falliti e annullati prima di stampare non costano nulla.
- Il limite pagine si controlla prima di stampare: un documento che non ci sta viene rifiutato subito.
- Le stampanti che non rispondono, o sono bloccate, non vengono offerte. Non vengono offerte nemmeno quelle che non puoi usare.
- Se i tuoi orari sono limitati e sei fuori orario, la pagina Stampa dice quando puoi stampare, e un lavoro inviato lo stesso viene rifiutato.
