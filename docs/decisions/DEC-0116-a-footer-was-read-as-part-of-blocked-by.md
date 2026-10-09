# DEC-0116 — A footer was read as part of "Blocked by"

**Category:** DEFECT
**Raised in:** [#PRN](https://github.com/Jersyfi/taktus/pull/PRN), after making #90 ready showed the ready rule missing a blocker
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`docs/process/README.md` says a task is not ready while something it names under "Blocked by" is
open. The issue form's last section is "Blocked by", and issues written by sessions end with a
footer after a horizontal rule, naming the record or pull request they were written under. The
ready rule — one implementation, used by `make backlog` and by P-03's admission — read that footer
as part of "Blocked by". So the footer's references were read as blockers, and prose before them
that named a blocker in words was not caught, because the section already named records. #90 was
shown as merely "not labelled ready" while it said that it needed a decision request.

## 2. Why you are being asked

You are not. A gate's coverage had a hole, a finding under CLAUDE.md §11, and the fix makes the
rule do what `docs/process/README.md` says: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- A section now ends at the next heading or at a horizontal rule, whichever comes first. What
  follows the rule belongs to no section.
- A test shows a footer naming open records is not a blocker, and that prose naming no record is
  caught even when a footer follows it.
- The rule became stricter, not weaker.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0116" in an issue.

## Outcome

**Corrected:** 2026-10-09
**What was wrong:** the ready rule read an issue's footer as part of its "Blocked by" section.
**Why it was wrong:** a section ran to the next heading, and the footer has none.
**What it now says:** a section ends at a horizontal rule as well.
**What changed in substance:** the readiness of an issue with a footer is now judged on its form alone.
**Recorded in:** [#PRN](https://github.com/Jersyfi/taktus/pull/PRN)
