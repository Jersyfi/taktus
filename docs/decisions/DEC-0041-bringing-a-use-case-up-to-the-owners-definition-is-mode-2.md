# DEC-0041 — Bringing a use case up to the owner's definition is mode 2

**Category:** NON-BLOCKING
**Raised in:** the audit of the decision register, 2026-10-01; recorded in [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** none; the owner decided before a request was written, and this record is the question with his answer
**Needed by:** 2026-10-01
**Written after the answer:** the owner answered in the audit's brief of 2026-10-01; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

What a use case requires — its outcome, its verification condition, its boundary — is the
owner's to decide (M3.15). Some amendments add nothing new: they restore what the vision and the
owner's own project definition already require, where a use case fell short of it. DEC-0030 asked
the owner about four such amendments together with thirteen genuinely new conditions.

## 2. Why you are being asked

It moves part of M3.15, an entry of mode 3, to mode 2; moving an entry is the owner's.

## 3. What you must decide

Whether an amendment that only restores what the vision and the project definition already
require is decided by the session and recorded as a notice.

## 4. What you need to know to decide

- **What stays the owner's.** A new requirement — one the vision and the definition do not
  already contain — stays mode 3.
- **What a notice is.** A record of what the session decided, on what evidence, which the owner
  can read and override.

## 5. Options

### Option A — mode 2 for restoring, mode 3 for new (recommended)

- **Meaning:** a new mode-2 entry for amendments that only restore what the vision and the owner's
  definition already require; new requirements stay M3.15.
- **Consequence:** DEC-0030 narrows to its genuinely new conditions.
- **Effort:** the anchor pages, the doctrine, four notices.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — everything a use case requires stays mode 3

- **Meaning:** as before.
- **Consequence:** the owner reads restorations of his own definition as questions.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

DEC-0030's four amendments, until this is answered.

## 7. How to answer

"DEC-0041: Option A." or "DEC-0041: Option B."

## Outcome

**Decided:** 2026-10-01
**Answer:** Option A, as the owner gave it: bringing a use case up to the owner's own definition is
mode 2. An amendment that only restores what docs/vision and the owner's project definition
already require is not a new requirement: decide, record a notice. New requirements stay mode 3.
**Reasoning given:** such an amendment is not a new requirement.
**Recorded in:** [#52](https://github.com/Jersyfi/taktus/pull/52): entry M2.7 in
`anchors.taktus.md`, a configurable default in `anchors.md`, `CLAUDE.md` §9, ADR-0017 §1a; the
four amendments of DEC-0030 as notices NTC-0014 to NTC-0017, and DEC-0030 narrowed.
