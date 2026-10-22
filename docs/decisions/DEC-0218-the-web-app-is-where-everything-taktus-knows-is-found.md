# DEC-0218 — The web app is where everything Taktus knows is found

**Category:** NON-BLOCKING
**Mode entry:** M3.15 (what a use case requires); DEC-0185 (the web app's direction)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-22, from the owner's feedback on an alert
**Issue:** none; the owner stated it in conversation
**Needed by:** 2026-10-22
**Written after the answer:** the owner stated it in conversation on 2026-10-22; left out of the acceptance rate (DEC-0042).

## 1. What this is about

On 2026-10-22 the instance's first alert of a missing backup (#323) reached the owner in the chat. Its link, `https://<instance>/owner/reports/<id>`, is a route of the HTTP surface that asks for a key: the owner, signed in to the web app, got `401 Unauthorized`. The web app's own pages link to no report. Since #308 (2026-10-12) nothing that was built has reached the web app: alerts, incidents, signals and their corridors, backups, correction rates, findings, tenants, model routes.

## 2. Why you are being asked

What the web app must show is what its use cases require (M3.15). DEC-0185 set its look, not what it must hold.

**Sources checked:** UC-6.10, UC-6.11, DEC-0055, DEC-0185, the anchor pages.

## 3. What you must decide

Whether the web app is the one place where everything Taktus knows can be found, whatever channel or connector carried a message.

## 4. What you need to know to decide

Every message a channel carries already has a report or a record behind it. The web app could open each by its identifier, under the reader's own sign-in.

## 5. Options

### Option A — the web app holds and links everything; every message links into it (recommended)

### Option B — the channels stay the place, and the web app shows runs only

## 6. What is blocked

Nothing; the work starts on the answer.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-22
**Answer:** Option A. "Ich bin mir unsicher, ob Taktus bewusst ist, dass das Dashboard alle Informationen immer bereitstellen soll und darüber griffbereit machen muss egal wohin es dann am Ende geht oder welche Connectoren verwendet werden. Taktus ist hier bei Kunden der zentrale Drehpunkt und muss sorge dafür Tragen dass alles Transparent aufgezeigt ist und man als Anwender alles wiederfindet und schnell erreicht bzw alles ersichtlich ist was man wissen muss." and "ich möchte, dass Taktus sich hier weiter entwickelt und man mal was sieht." (the owner's words: the dashboard must always provide every piece of information and keep it at hand, whatever channel or connector it goes through; Taktus is the customer's central pivot and must make everything transparent, so that a user finds everything again, reaches it quickly, and sees what they need to know; the owner wants Taktus to develop here, visibly.)
**Reasoning given:** Taktus is the customer's central pivot; transparency fitted to the role (principle 7).
**What it changes:**

- Every link a channel carries opens a page of the web app under the reader's sign-in, never a route that asks for a key.
- The web app shows, for its reader's role, what Taktus holds: reports and alerts, decision requests and needs, incidents, signals and their corridors, backups, findings, correction rates and levels, tenants for an administrator, and runs as before; each reachable from its start page.
- Its look keeps developing in DEC-0185's direction, mode 1 (M1.20), and the progress is visible on the instance with each release.
- The use cases that require it are brought to this (UC-6.10, UC-6.11), in pull requests of their own, and the work becomes issues in `0.4.0`.

**Recorded in:** this pull request
