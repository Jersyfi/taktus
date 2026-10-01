# DEC-0039 — What fits no entry: a question, or a decision in the direction of the vision

**Category:** NON-BLOCKING
**Raised in:** the owner's brief of 2026-10-01, which decided it; recorded in [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** none; the owner decided before a request was written, and this record is the question with his answer
**Needed by:** 2026-10-01

## 1. What this is about

Every question a session meets is tested against a list of entries that say who decides it: the
session alone, the session with a recorded notice, or the owner. A situation that fit no entry
was, until now, sent to the owner as a non-blocking question that proposed which entry it
belongs in, and the work went on meanwhile on a provisional answer. In a young project almost
every situation is new, so that rule generated questions by design. A non-blocking question
costs the session nothing and the owner reading time.

## 2. Why you are being asked

The rule for what fits no entry is the rule by which the owner's anchors are applied; changing
it changes what reaches the owner, which is the owner's (`anchors.taktus.md`, the page's own
*Neither list*). The owner raised it himself.

## 3. What you must decide

Whether a situation that fits no entry is asked of the owner, or decided by the session in the
direction the vision points and recorded.

## 4. What you need to know to decide

- **What stays as it is.** Entries of mode 3 and mode 4 — what the owner decides, with or
  without a worked opinion — are untouched either way.
- **What a notice is.** A record in the register of what a session decided alone, on what
  evidence, what it considered, and which entry permits it. Nobody approves it; the owner can
  read it and overrule it with a decision.
- **The record so far.** Of six requests the owner had answered by 2026-10-01, five took the
  recommended option.

## 5. Options

### Option A — decide in the direction of the vision, and record it (recommended)

- **Meaning:** a situation that fits no entry is decided by the session in the direction the
  vision and the existing anchors point, recorded as a notice that proposes its entry; a
  question is raised only where the vision gives no direction.
- **Consequence:** fewer questions; more notices for the owner to read after the fact.
- **Effort:** the anchor pages, the doctrine, the decision mechanism and the gate.
- **Reversibility:** cheap.
- **Why recommended:** the owner's reason, below.

### Option B — ask, as before

- **Meaning:** every situation that fits no entry becomes a non-blocking question.
- **Consequence:** the owner is asked about every new situation.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0039: Option A." or "DEC-0039: Option B."

## Outcome

**Decided:** 2026-10-01
**Answer:** Option A, with four parts the owner decided together:
(1) **the reversed default** — a situation that fits no entry is decided by the session in the
direction the vision and the existing anchors point, recorded as a notice (mode 2, the new entry
M2.6, kind `unlisted`) with the entry it proposes; a question is raised only where the vision
gives no direction; mode 3 and mode 4 are untouched;
(2) **the derivability test** — before raising any request, the session checks `docs/vision/`,
the ADRs, the anchor pages and the register, and the request names the sources checked and why
none answers it; a request that does not is returned;
(3) **the register as precedent** — a question an earlier decision answers is not a question;
the session applies the precedent and cites it;
(4) **the acceptance rate, measured continuously** — for every answered request, did the owner
choose the recommended option; for every notice, did the owner later override it; both shown in
`make status`.
The owner also asked to consider a gate that fails a pull request description holding an action
for the owner without a linked NEED or DEC, and to say so if it cannot be done reliably. It
cannot, and it was not built: the most plausible check — a sentence naming the owner, with a
word of obligation, and no `NEED-` or `DEC-` — run over all 27 pull request descriptions to
2026-10-01 found three sentences, of which one was an owner action written as a note (#3, a
label left to the owner) and two described what the owner had provided. The owner actions that
were written as notes elsewhere used other words and were not found. A check that misses most of
what it is for and raises false alarms on the rest would teach the reader to ignore it.
**Reasoning given:** the rule that sends every unlisted situation to the owner generates
questions by design in a young project, and a project that develops itself cannot spend its time
asking. A rate near 100 % means too much is asked; many overridden notices mean too much is
decided alone — the balance becomes visible in both directions.
**Recorded in:** [#52](https://github.com/Jersyfi/taktus/pull/52). `anchors.taktus.md` (*Neither list*, M2.6, the test of a question),
`anchors.md` §1 and §4–§5, `CLAUDE.md` §8 and §9, ADR-0017 §1a and §9, `tools/check_decisions.py`
(the derivability test from this number on, the `unlisted` section, `**Overridden by:**`) and
`tools/check_status.py` (the acceptance line of `make status`).
