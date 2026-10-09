# DEC-0094 — The index was checked for a name, not for its table

**Category:** DEFECT
**Raised in:** [#141](https://github.com/Jersyfi/taktus/pull/141), after a notice was found listed among the decisions
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The register's index, `docs/decisions/README.md`, has three tables: needs, notices and decisions,
so that it can be read by kind. The decisions gate checked only that a record's file name appears
somewhere in the index. A notice, NTC-0072, had been filed in the table of decisions, and every
gate stayed green. A reader of the notices table would not have found it.

## 2. Why you are being asked

You are not. A gate's coverage had a hole, which CLAUDE.md §11 makes a finding, and the fix is
entry M1.4 of `docs/decisions/anchors.taktus.md`: the repository said something that was not so.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The row of NTC-0072 is moved into the notices table.
- `make gate-decisions` now checks each record in its own table: a decision under Decisions, a
  notice under Notices, a provided need under Needs. A test proves that a row moved into another
  table is found.
- The gate became stricter, not weaker; no notice is needed for that (M2.3 covers weakening).

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0094" in an issue.

## Outcome

**Corrected:** 2026-10-09
**What was wrong:** the gate accepted a record listed in any table of the index; a notice sat
among the decisions unnoticed.
**Why it was wrong:** the check searched the whole index for a file name.
**What it now says:** each record is checked in the table of its kind.
**What changed in substance:** nothing in the product; the gate and one row of the index.
**Recorded in:** [#141](https://github.com/Jersyfi/taktus/pull/141)
