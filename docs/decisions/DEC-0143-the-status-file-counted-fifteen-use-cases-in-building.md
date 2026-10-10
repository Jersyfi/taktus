# DEC-0143 — The status file counted fifteen use cases in building

**Category:** DEFECT
**Raised in:** issue [#104](https://github.com/Jersyfi/taktus/issues/104), in the pull request that closes it
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`docs/status.md` §1 said that seventy-five use cases exist: three *built*, fifteen *building*
and fifty-eight *specified*. The use case files said seventy-six: four *built*, sixteen
*building* and fifty-six *specified*. UC-4.14, a process starts on what happens in a tool, was
*built* and missing from its list. UC-6.11, the owner-facing channel, was *building* and missing
from its list. The pull request that closes #104 moves UC-6.10 to *building*, which showed the
gap while the count was updated.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The file now says seventy-six use cases: four *built*, with UC-4.14 named; seventeen
  *building*, with UC-6.10 and UC-6.11 named; fifty-five *specified*.
- `make usecases` prints the states from the files, which are the source.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0143" in an issue.

## Outcome

**Corrected:** 2026-10-10
**What was wrong:** the status file counted seventy-five use cases and left UC-4.14 out of the *built* ones and UC-6.11 out of the *building* ones.
**Why it was wrong:** the changes that moved them did not update the counts.
**What it now says:** seventy-six use cases: four *built*, seventeen *building*, fifty-five *specified*.
**What changed in substance:** nothing; the count follows the files.
**Recorded in:** issue [#104](https://github.com/Jersyfi/taktus/issues/104), in the pull request that closes it
