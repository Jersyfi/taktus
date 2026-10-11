# DEC-0183 — The status file counted seventeen use cases in building

**Category:** DEFECT
**Raised in:** the pull request that records UC-1.9 as *building*
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`docs/status.md` §2 said that seventy-six use cases exist: four *built*, seventeen *building* and
fifty-five *specified*. The use case files say seventy-seven: four *built*, twenty-two *building*
and fifty-one *specified*. UC-4.13, UC-6.9, UC-13.5 and UC-13.6 had moved to *building* in the
pull requests that built them (#91, #94, #198) without the count following; UC-1.9 was added by
#258 and moves to *building* here.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4. DEC-0143 corrected the same count
the same way.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The file now says seventy-seven: four *built*, twenty-two *building* with the five named,
  fifty-one *specified*.
- `make usecases` prints the states from the files, which are the source.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0183" in an issue.

## Outcome

**Corrected:** 2026-10-12
**What was wrong:** the status file counted seventy-six use cases, seventeen of them *building* and fifty-five *specified*.
**Why it was wrong:** four pull requests that moved a use case to *building* did not update the count, and a use case was added since.
**What it now says:** seventy-seven use cases: four *built*, twenty-two *building*, fifty-one *specified*.
**What changed in substance:** nothing; the count follows the files.
**Recorded in:** the pull request that records UC-1.9 as *building*
