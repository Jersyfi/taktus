# DEC-0189 — Six working rules for the project's own records

**Category:** NON-BLOCKING
**Raised in:** the session of 2026-10-12 whose review analysed the project's own process from the register, 122 merged pull requests and 888 CI runs; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-12
**Written after the answer:** the owner answered in conversation on 2026-10-12; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The review measured the cost of how this repository records its work. The measurements are in
`docs/research/2026-10-12-devops-review.md`, P7.

- **Confirmed:**
  - the register is 13 % of all changed lines;
  - process gates stopped 41 of 132 branches, product gates 14;
  - 47 of 76 failures of the description check were a stale copy of the list of what is needed from the owner;
  - 24 of 53 requests were written in full after the owner had answered;
  - the owner granted every widening of the session's authority (10 of 10) and followed every recommendation on a use-case requirement (9 of 9);
  - no notice was overridden (0 of 106).
- **Refuted:**
  - the owner is not a bottleneck: the median answer came after one day;
  - process gates cost 1.5 % of CI time.

The session proposed six rules. They keep every control and remove repetition. This project
only: none of it is product (DEC-0188).

## 2. Why you are being asked

How work is done here is CLAUDE.md's. Moving a question from mode 3 to mode 2 changes the
owner's anchor page, and that is the owner's.

**Sources checked:** CLAUDE.md §8 and §9, `anchors.taktus.md` (M2.4, M2.7, M3.6, M3.15), DEC-0026,
DEC-0041, DEC-0042, DEC-0174, DEC-0179, DEC-0184. They set today's rules and do not answer
whether these should change.

## 3. What you must decide

Whether the six rules hold.

## 4. What you need to know to decide

1. **The list of what is needed from the owner in a pull request is generated**, not checked
   against a copy a person pasted. Built by #314; until then today's check stands.
2. **A behaviour change inside an agreed scope (M2.4) is a line in the pull request**, not a
   notice file. Built by #315; until then notices stand.
3. **An answer the owner gave in conversation is recorded short.** Each of the seven sections may
   be one line, plus the outcome and every change the answer causes. It is recorded first, as
   today.
4. **The session's standing authority is written once**, as entries of the anchor page instead of
   a request each time:
   - tagging release candidates (DEC-0184);
   - merging its own green pull request, with no more running in parallel than CI carries (DEC-0174);
   - acting on the instance with the deployment identity within DEC-0179's limits.
5. **A use-case requirement that follows from what the owner accepted becomes a notice** (M2.7)
   with a veto window of seven days. "What the owner accepted" means the owner's definition, a
   feature the owner accepted (M3.2) or an item of the roadmap. A requirement that follows from
   none of these stays a request (M3.15).
6. **Record numbers and the register's index are allocated at merge** or generated. Built by
   #316; until then numbers are taken from `main` as today.

## 5. Options

### Option A — all six (recommended)

- **Meaning:** rules 3, 4 and 5 hold from this pull request; 1, 2 and 6 hold once their issues
  land.
- **Consequence:** fewer files, fewer stopped pull requests, the same decisions with the owner.
- **Reversibility:** cheap; each rule is a line of CLAUDE.md or the anchor page.
- **Why recommended:** the owner's answer, below.

### Option B — none

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0189: Option A." or "DEC-0189: Option B."

## Outcome

**Decided:** 2026-10-12
**Answer:** Option A. The owner accepted the whole optimisation proposal, the six rules included: "From the Taktus optimisation proposal I want to adopt everything." (the owner's words, translated)
**Reasoning given:** none beyond the answer.
**What it does not change:** what is the owner's in mode 3 and 4; a requirement that is new beyond what the owner accepted stays M3.15; a release that is not a candidate stays M3.6; deploying stays ADR-0013 D.
**Recorded in:** this pull request:
- CLAUDE.md §9;
- `anchors.taktus.md` (M1.21 to M1.23, M2.7, M3.15 and their history);
- `docs/process/next-task.md`;
- the issues #314, #315 and #316.
