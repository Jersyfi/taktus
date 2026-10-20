# DEC-0214 — Five tasks go to Taktus again, and findings must leave through the one app

**Category:** NON-BLOCKING
**Mode entry:** DEC-0197 (handing a task to Taktus); ADR-0028 (a needs request is the owner's to provide)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-18
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-20
**Written after the answer:** the owner answered in conversation on 2026-10-20; left out of the acceptance rate (DEC-0042).

## 1. What this is about

- P-03 gave back #325, #326, #327 and #394 because its worker reworded the template's headings. Version 20 copies them (#519).
- It gave back #317 because its change failed the repository's checks: a test pins the newest migration.
- NEED-0031 (#533) asked the owner for a second GitHub app, through which the business's instance raises its findings here (ADR-0112).

## 2. Why you are being asked

Handing a task to Taktus is the owner's (DEC-0197). What a needs request asks of the owner is the owner's to accept (ADR-0028).

**Sources checked:** DEC-0197, DEC-0205, DEC-0213, ADR-0112, NEED-0031.

## 3. What you must decide

Whether the five tasks go to Taktus again, and whether findings may leave through a second app.

## 4. What you need to know to decide

A task handed again is claimed by P-03 version 20. The branch of the failed attempt is deleted first, because no pull request is open (DEC-0205).

## 5. Options

### Option A — hand the five again; a second app for findings (recommended)

### Option B — hand the five again; findings find another way

## 6. What is blocked

The five tasks, and findings from the business's instance.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-20
**Answer:** Option B. "Zu 1, ja. Zu 2. entschiede du was hier sinnvoller ist. Von mir aus übergebe es erneut an Taktus." and "Zu 4. das finde ich nicht gut, da ich finde, das Taktus in GitHub nur eine App sein sollte die man einrichtet und Taktus den rest dann selber steuern kann." and "Das sollte über eine App funktionieren und Taktus muss einen Weg finden. Präsentiere mir dafür eine neue Lösung in dieser Session und warte auf meine Freigabe bevor wir es in irgendein Issue einarbeiten oder es lösen." (The owner's words: to 1, yes; on #317 the session decides, and handing it to Taktus again is fine; a second app is rejected; Taktus in GitHub is one app that is set up once, and Taktus steers the rest; a new solution is presented in the session, and nothing is worked into an issue or built before the owner approves it.)
**Reasoning given:** an operator sets up one app, as for every comparable product; a product that needs several accounts for one app is not acceptable.
**What it changes:**

- #325, #326, #327 and #394 are handed to Taktus again, after their failed attempts' branches are deleted (DEC-0205).
- #317 goes to Taktus again too, on the session's judgement. Its failure was a check its change missed, and P-03 runs the repository's checks before it opens a pull request.
- NEED-0031's second app is rejected. NEED-0031 and #533 stay as they are until the owner approves a solution with one app; nothing of it is built before then.

**Recorded in:** this pull request
