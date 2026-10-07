# DEC-0040 — A decision under the reversed default follows its source

**Category:** NON-BLOCKING
**Raised in:** the audit of the decision register, 2026-10-01; recorded in [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** none; the owner decided before a request was written, and this record is the question with his answer
**Needed by:** 2026-10-01
**Written after the answer:** the owner answered in the audit's brief of 2026-10-01; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Under DEC-0039 a situation that fits no anchor entry is decided by the session in the direction
the vision and the anchors point, and the record names the sources it checked. Naming a source is
not the same as following it. The audit found two records in which the session cited the right
source and still recommended the option the owner then rejected.

## 2. Why you are being asked

How the reversed default is applied decides what the session does without asking; that is the
owner's to set (`anchors.taktus.md`, *Neither list*, DEC-0039).

## 3. What you must decide

Whether a record under the reversed default must show how its decision follows the source it
cites, and which way to decide when two options are both consistent with the sources.

## 4. What you need to know to decide

- **The evidence.** In DEC-0014 and DEC-0021 the session found the right source and still
  recommended the option the owner rejected. In 4 of the 5 recommendations the owner rejected,
  he chose the stricter option; in the fifth, the one with less ceremony.
- **What a gate can see.** That a record states how the decision follows its source; not
  whether the reasoning holds. The substance is for review.

## 5. Options

### Option A — show how, and break ties strict in substance, sparing in ceremony (recommended)

- **Meaning:** the record states how the decision follows the source it cites; where two options
  are both consistent with the sources, the stricter in substance and the one with less ceremony
  is taken.
- **Consequence:** fewer recommendations the owner reverses.
- **Effort:** the anchor pages, the doctrine, the gate.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — naming the source is enough

- **Meaning:** as DEC-0039 left it.
- **Consequence:** the pattern the audit found continues.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0040: Option A." or "DEC-0040: Option B."

## Outcome

**Decided:** 2026-10-01
**Answer:** Option A, as the owner gave it: under the reversed "neither list" default, a session
decides according to the source it cites, and the record shows HOW the decision follows that
source — not merely that a source was named. Where two options are both consistent with the
sources: strict in substance, sparing in ceremony.
**Reasoning given:** in DEC-0014 and DEC-0021 the session found the right source and still
recommended the option the owner rejected. In 4 of 5 rejected recommendations the owner chose the
stricter option, and in the fifth the one with less ceremony.
**Recorded in:** [#52](https://github.com/Jersyfi/taktus/pull/52): `anchors.taktus.md` for this
tenant; `anchors.md` as a configurable default justified from principles 9 and 12; `CLAUDE.md`
§8; ADR-0017 §1a; `tools/check_decisions.py` (`**How it follows:**`).
