# DEC-0042 — The override rate is reviewed, not only shown

**Category:** NON-BLOCKING
**Raised in:** the audit of the decision register, 2026-10-02; recorded in [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** none; the owner decided before a request was written, and this record is the question with his answer
**Needed by:** 2026-10-02

## 1. What this is about

Under DEC-0039, `make status` shows how often a later decision overrode a notice. A figure that is
shown is not necessarily read. The reversed default rests on the owner reviewing what the session
decided alone.

## 2. Why you are being asked

When the owner is asked about the balance of deciding alone is the owner's to set (DEC-0039).

## 3. What you must decide

Whether the override rate is put to the owner as a question after a number of notices.

## 4. What you need to know to decide

- **The rate.** The share of notices under the reversed default that a later decision overrode.
- **What "automatically" means here.** The gate fails the register once the count is reached and
  no request carrying the rate exists, so that the request is raised by whoever meets it first.

## 5. Options

### Option A — a request after twenty notices (recommended)

- **Meaning:** after twenty notices under the reversed default, a decision request is raised to
  the owner automatically, carrying the rate at which he overrode them.
- **Consequence:** the balance is reviewed, not only displayed.
- **Effort:** the gate, the anchor pages.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — shown only

- **Meaning:** as DEC-0039 left it.
- **Consequence:** the figure may go unread.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0042: Option A." or "DEC-0042: Option B."

## Outcome

**Decided:** 2026-10-02
**Answer:** Option A, as the owner gave it: the override rate is reviewed, not only shown. After
twenty notices under the reversed default, raise a decision request to the owner automatically,
carrying the rate at which he overrode them.
**Reasoning given:** none beyond the answer.
**Recorded in:** [#52](https://github.com/Jersyfi/taktus/pull/52): `anchors.taktus.md`,
`anchors.md` (a configurable count), `CLAUDE.md` §8, ADR-0017 §9; `tools/check_decisions.py`
fails the register at twenty `unlisted` notices without a review request, and `make status`
shows the count towards it.
