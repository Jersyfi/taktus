# DEC-0227 — Package E: everything open built, the web app redesigned, and delivered

**Category:** NON-BLOCKING
**Mode entry:** M3.6 and M3.15 (how work lands and what holds a release back), DEC-0222 (concept mode)
**Raised in:** the session of 2026-11-03, by the owner's message in conversation
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-03
**Written after the answer:** the owner stated it in conversation on 2026-11-03; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The first customer waits for the software. The owner asks for every open issue outside the
milestone `2.0.0` to be worked through, the open security alerts closed, and the web app
redesigned, in one package.

## 2. Why you are being asked

How work lands and what is delivered are the owner's (M3.6, M3.15).

**Sources checked:** DEC-0222 (concept mode), DEC-0197 (tasks handed to Taktus), DEC-0225 (live
tests only for what the project uses itself).

## 3. What you must decide

The scope of the package, and how it lands.

## 4. What you need to know to decide

About thirty task issues are open outside `2.0.0`. Some of them depend on what only the owner or
the business can do.

## 5. Options

### Option A — the package as the owner described it (recommended)

### Option B — the issues one by one, as before

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-03
**Answer:** Option A, in the owner's words: "Außer Meilenstein 2.0 möchte ich, dass alle offenen
Issues und auch die Issues die nicht zugewiesen sind alle bearbeitet werden, damit wir fertig
werden und einen sauberen Stand hinbekommen. Der Kunde wartet auf die Software und wir wollen nun
liefern." Also: every open point under GitHub Security closed. The web app's UI/UX reviewed from
the roles that use Taktus and redesigned in the sense of the vision, creative and not ordinary,
its colours oriented on the design system of Jersyfi/hubtask, so that one design system serves
all of the owner's applications. A functional test, a short performance test, the logs read and
every bug found fixed. "Haluziniere nichts, fake nichts, erfinde nichts was es nicht gibt."
"Du kannst dieses im Konzeptmodus umsetzen, nur ein PR am Ende mit finalen CI Checks und mergen
ist erlaubt. Ich möchte Tempo in der Umsetzung."
**Reasoning given:** the customer waits for the software; the project wants to deliver.
**What it changes:**

1. **Package E is built in concept mode** on `concept/package-e` and lands in one pull request,
   which the session merges once its final CI checks are green.
2. **Every open task outside `2.0.0` is in scope.** This includes the issues labelled `to-taktus`
   (#325, #394), which DEC-0197 otherwise keeps from a session: the owner's "alle offenen Issues"
   names them. Decision requests and needs requests stay the owner's. A task whose remainder only
   the owner or the business can do is built as far as the product goes, and its remainder is
   stated, not faked.
3. **The web app** gets a design system whose colours follow Jersyfi/hubtask's tokens, and a
   design that serves each role of `docs/vision/personas.md` without losing the vision's idea of
   transparency fitted to the role (principle 7) and people at the centre (principle 14).
4. **Security:** the open Dependabot alerts are fixed by upgrades.
**Recorded in:** this pull request
