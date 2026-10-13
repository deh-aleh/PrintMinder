# Account, gruppi e chiavi di stampa

[Indice della documentazione](../README.md) · [English](../en/accounts.md) · Italiano

## 1. Chi è chi

Ogni persona è **una riga** nella tabella `user` con un *provider*:

- **local** — la password (argon2id) sta nel database del gateway e si gestisce dal portale;
- **RADIUS** (facoltativo) — la password la verifica il server RADIUS d'ufficio; il gateway non la conserva.

**I nomi utente sono unici fra tutte le origini.** A CUPS e all'audit arriva solo `gw:<nome>`: due persone con lo stesso nome
condividerebbero identità e quota. Il metodo di accesso lo decide la *riga*, mai chi risponde "sì": un account locale non può essere
aperto dal RADIUS nemmeno se il RADIUS conosce lo stesso nome. Un utente RADIUS sconosciuto viene creato al primo accesso al portale
(nel gruppo predefinito) se `CUPSPL_AUTO_CREATE_USERS=true`; se il nome è già locale, no.

RADIUS è facoltativo. Con `CUPSPL_RADIUS_HOST` e `CUPSPL_RADIUS_SECRET` vuoti esistono solo account locali. Se il RADIUS non risponde,
l'accesso è negato (fail closed). I nomi RADIUS si confrontano senza distinguere maiuscole: `Mario` e `mario` sono la stessa persona.

## 2. Il primo amministratore

`cups_orchestrator` esiste senza password. Al primo avvio il gateway scrive nei log un **codice monouso**
(`docker compose logs gateway | grep "FIRST RUN"`); `/admin/setup` lo chiede insieme alla nuova password e poi si disattiva.
Il codice è protetto da throttling. In alternativa: `cups-policy-admin set-admin-password`. Di proposito non esiste una pagina aperta
a tutti per diventare amministratore.

L'account di emergenza non si può disattivare, declassare, eliminare né cambiargli origine. Nessuno può disattivare, declassare o
eliminare se stesso, né l'ultimo amministratore.

## 3. Password (account locali)

Minimo 12 caratteri, diversa dal nome utente. Una password creata o reimpostata da un amministratore è **temporanea**: si mostra una
volta e l'utente deve cambiarla al primo accesso. Cambiare password chiude le altre sessioni dell'utente. Il login spende sempre il costo
di un hash, anche per nomi inesistenti, e non rivela se il nome esiste.

## 4. Gruppi

I limiti di quota si impostano per **gruppo**, con override facoltativi per utente ([quote.md](quote.md)). Esistono sempre due gruppi di
sistema, che non si eliminano:

- `default` — dove partono tutti e dove vanno gli utenti quando il loro gruppo viene eliminato o smettono di essere amministratori;
- `administrator` — solo per gli amministratori. La promozione sposta l'utente lì; il declassamento lo riporta in `default`. Un
  non amministratore non può esservi spostato a mano.

Un gruppo si può marcare **richiedibile**: gli utenti possono allora chiedere di entrarvi ([quote.md](quote.md)). I gruppi amministrativi non lo sono mai.

## 5. Chiavi di stampa

I sistemi operativi tengono le password di stampa in chiaro (per esempio `printers.conf` su Linux). Perciò i client **non usano mai** la
password di dominio: usano una **chiave di stampa personale**.

- La crea l'utente in *Profilo → Crea una chiave* (con un'etichetta per dispositivo). Si mostra **una volta**; si conserva solo
  come hash sha256 di 192 bit casuali.
- Vale **solo per stampare e scansionare** (gli endpoint IPP ed eSCL); non apre mai il portale.
- Ha una scadenza: di default 90 giorni per gli utenti RADIUS, 365 per i locali. Un utente RADIUS la rinnova rifacendo il login nel
  portale — così chi lascia l'azienda smette di stampare alla scadenza. L'amministratore può revocare le chiavi in qualsiasi momento.
- L'ultimo uso (ora e IP) è annotato al massimo una volta al minuto.
- Si revoca una chiave, o tutte, in *Le mie chiavi* (`/me/keys`) oppure, per un amministratore, in `/admin/users/<id>/keys`.

`CUPSPL_IPP_AUTH=keys` (predefinito) accetta per stampare solo le chiavi. `keys+radius` accetta anche la password RADIUS per gli utenti
RADIUS durante una transizione (mai per gli account locali): incoraggia a salvare la password di dominio sui client, quindi usala solo
temporaneamente.

## 6. Protezione dei login

- 5 password *diverse* sbagliate in 5 minuti per la stessa coppia (utente, IP) bloccano quella coppia; c'è anche un tetto per IP. La
  stessa password sbagliata ripetuta da un client conta una volta (libcups riprova 3–5 volte) e un estraneo non può bloccare un altro utente.
- Il blocco è in memoria: un riavvio lo azzera. Blocca la coppia (utente, IP) per 5 minuti e **non** disattiva l'account: lo stesso utente da un altro
  indirizzo non è toccato. Durante il blocco la pagina di accesso risponde "Troppi tentativi falliti, riprova più tardi" anche se poi la password è giusta.
  Per vederlo prova sei password *diverse* sbagliate; ripetere sempre la stessa non blocca mai.
- Disabilitare un utente nel portale blocca subito login e chiavi.
- Sessioni del portale: firmate, 8 ore, token CSRF su ogni POST, cookie `Secure` + `SameSite=strict`. Le pagine che mostrano un segreto
  sono inviate con `Cache-Control: no-store`.

## 7. Eliminare un utente

Rimuove account, chiavi, richieste, concessioni e limiti personali, ma **non lo storico**: le righe di audit conservano il nome utente e
perdono solo il legame con l'id; le righe dell'audit amministrativo conservano già il nome di chi ha agito. L'amministratore scrive il
nome dell'utente per confermare.

## 8. Cambiare l'origine di un account

Dalla pagina di modifica dell'utente: locale → RADIUS cancella la password salvata; RADIUS → locale genera una password temporanea
mostrata una volta. L'account di emergenza resta locale.
