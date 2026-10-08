# DEC-0049 — A session may spend up to one dollar per task to derive

**Category:** NON-BLOCKING
**Raised in:** NTC-0018, recorded in [#52](https://github.com/Jersyfi/taktus/pull/52), which proposed the entry M2.8; recorded in [#59](https://github.com/Jersyfi/taktus/pull/59)
**Issue:** none; the owner answered in the brief of 2026-10-07 before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-07
**Written after the answer:** the owner answered in the brief of 2026-10-07; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

On 2026-10-01 a session measured how the model endpoint handles an output limit, instead of
asking the owner. It used the key the owner had provided and spent under one cent. The notice
NTC-0018 recorded it, because it was a precedent, and proposed a standing entry: a session may
spend on a credential the owner provided, within the purpose it was provided for, to derive a fact
instead of asking — bounded at one euro per derivation.

## 2. Why you are being asked

A notice under *Neither list* proposes an entry; the owner accepts or overrides it (DEC-0039). A
spend is also a limit (M3.10 of `anchors.taktus.md`).

**Sources checked:** the vision (principle 8, cost control), the ADRs (ADR-0005 on limits), both
anchor pages (no entry on a session's own spend) and the register (NTC-0018, DEC-0039). They
permit the precedent; none sets the amount.

## 3. What you must decide

Whether M2.8 becomes an entry, and with which cap.

## 4. What you need to know to decide

- **A derivation** is a call made to learn a fact the work needs — a measurement, a check, a
  rehearsal call — instead of putting the question to the owner.
- **A task** is one issue of the backlog, worked in one pull request.

## 5. Options

### Option A — accept M2.8, capped at USD 1 per task (recommended)

- **Meaning:** a session may spend on the owner's credential to derive or verify a fact instead
  of asking, up to USD 1 per task, recorded as a notice. Beyond that it is a request.
- **Consequence:** small measurements stop costing the owner reading time; larger spend is still
  asked.
- **Effort:** the anchor page and the kind vocabulary.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — no entry; every spend is asked

- **Meaning:** NTC-0018 stays a single precedent.
- **Consequence:** each measurement of under a cent becomes a question.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0049: Option A." or "DEC-0049: Option B."

## Outcome

**Decided:** 2026-10-07
**Answer:** Option A, as the owner gave it. M2.8 is accepted with a cap: a session may spend on
the owner's credential to derive or verify a fact instead of asking, up to USD 1 per task,
recorded as a notice. Beyond that it is a request.
**Reasoning given:** a limit is a limit, for a session as for a run.
**Recorded in:** [#59](https://github.com/Jersyfi/taktus/pull/59): `anchors.taktus.md` gains M2.8, kind `spend`; `anchors.md` gains the kind
`spend` in its vocabulary; NTC-0018 names the entry it led to. The cap is per task, not per
derivation as NTC-0018 proposed, and in US dollars, not euros.
