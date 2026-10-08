# DEC-0029 — Who reviews the legal-anchor catalogue, and when

**Category:** NON-BLOCKING
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
**Issue:** [#44](https://github.com/Jersyfi/taktus/issues/44)
**Needed by:** 2026-12-31

## 1. What this is about

Some acts must always stay with a person, whatever Taktus is otherwise allowed to do on its own:
signing, releasing a payment above a threshold, filing a tax return, terminating a contract,
notifying a data-protection authority, concluding a contract. Taktus calls these **legal anchors**.
It ships a catalogue of them as the default every organisation inherits; each organisation may add
to it and narrow it, never empty it.

The catalogue was written by the project, not by a lawyer. Whether it is complete and correct for a
given country is a legal question. The project definition asks who reviews it and when, and says
what kind of review it means: a professional one — tax advice for finance, labour law for
personnel — before a finance or personnel blueprint is put into production. It leaves open by whom
and when. It was carried as an open question in the definition's last chapter;
the vision layer now records it, and this request is where it is answered.

## 2. Why you are being asked

The catalogue is published as part of the product under the project's name, and an organisation
relying on it relies on a claim the project makes: entry M3.7 of
`docs/decisions/anchors.taktus.md`, *"Anything published under the project's name."* Who is
qualified to check a legal claim, and whether to pay for it, is also a purchase and a question of
liability that only you can weigh.

## 3. What you must decide

Who reviews the legal-anchor catalogue before a blueprint that depends on it is used in earnest, and
at which moments it is reviewed again.

## 4. What you need to know to decide

- **Where the catalogue is.** `docs/architecture/governance.md` §2 lists the classes of legal act;
  the shipped default (`docs/decisions/anchors.md`, entry M4.4) makes every one of them the owner's.
  Nothing in the product evaluates an anchor at run time yet; that is `0.2.0`.
- **When it starts to matter.** A blueprint for finance or personnel — invoicing, payroll, tax —
  runs exactly the acts the catalogue anchors. The definition makes finance the reference domain of
  the virtual agent business (UC-15.2) and requires the catalogue per domain and jurisdiction,
  configurable, never empty, and shown in the conformity evidence (UC-15.5). No such blueprint
  exists yet; the second domain on the roadmap is systems operation, not finance. The project's own repository has no legal anchor: it signs,
  pays and files nothing.
- **What a review cannot do.** It holds for a jurisdiction and a date. A catalogue reviewed for
  Germany says nothing about another country, and law changes.

## 5. Options

### Option A — qualified reviewers of the jurisdiction, before the first such blueprint, and at every change (recommended)

- **Meaning:** before any finance or personnel blueprint is used by a tenant, the catalogue is
  reviewed for that tenant's jurisdiction by a tax adviser for the finance acts and a labour-law
  specialist for the personnel acts, as the definition names them; the review is recorded with its date and
  jurisdiction; every change to the catalogue, and every new jurisdiction, is reviewed again. Until
  then the catalogue is marked as not legally reviewed wherever it is shown.
- **Consequence:** a cost per jurisdiction, and a date before which such blueprints cannot be used.
- **Effort:** a review per jurisdiction and domain; a session prepares the catalogue and the
  questions.
- **Reversibility:** cheap until a blueprint is live.
- **Why recommended:** it is the only option under which the project can state that the catalogue
  holds, and it costs nothing before it is needed.

### Option B — you review it yourself

- **Meaning:** you check the catalogue against your own knowledge before the first such blueprint.
- **Consequence:** no cost; the catalogue carries the review of a person who is not a lawyer.
- **Effort:** your time.
- **Reversibility:** cheap.

### Option C — each organisation reviews its own

- **Meaning:** the project never claims the catalogue is legally complete; it ships as a starting
  point, and every organisation has it checked by its own counsel before using such a blueprint.
- **Consequence:** no cost to the project; every organisation carries the cost and the risk.
- **Effort:** none for the project.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing until a finance or personnel blueprint is written; none is planned before `0.7.0`. The
provisional answer keeps the catalogue marked as unreviewed, which it is. The date is when you are
asked to look.

## 7. How to answer

"DEC-0029: Option A." — or B, or C — in issue
[#44](https://github.com/Jersyfi/taktus/issues/44). A free-text answer is read back as an
interpretation and confirmed before it is acted on.

## Outcome

**Decided:** 2026-10-08
**Answer:** Option A. Before any finance or personnel blueprint is used by a tenant, the legal-anchor catalogue is reviewed for that tenant's jurisdiction by qualified reviewers — a tax adviser for the finance acts, a labour-law specialist for the personnel acts — and the review is recorded with its date and jurisdiction; every change to the catalogue and every new jurisdiction is reviewed again. Until then the catalogue is marked as not legally reviewed wherever it is shown.
**Reasoning given:** none beyond accepting the recommendation, whose reason was that it is the only option under which the project can state that the catalogue holds, and it costs nothing before it is needed.
**Recorded in:** [#106](https://github.com/Jersyfi/taktus/pull/106); `docs/architecture/governance.md` §2
