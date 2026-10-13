# DEC-0194 — CI checks what changed before a merge, and everything after it

**Category:** NON-BLOCKING
**Raised in:** a session of 2026-10-13 that reviewed CI as a DevOps expert at the owner's request; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-13
**Written after the answer:** the owner answered in conversation on 2026-10-13; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

CI takes 26–27 minutes per run and runs during half the time a pull request is open. The owner
wants sessions and Taktus's own processes through as fast as possible, with no loss of quality
and with Taktus's self-development proven to work after every change. The evidence is in
`docs/research/2026-10-13-ci-review.md`; the method is ADR-0096.

## 2. Why you are being asked

How work is done here is CLAUDE.md's. The owner holds the ruleset of the repository. Dropping
"branches must be up to date" weakens a gate.

**Sources checked:** CLAUDE.md §9 and §11, ADR-0013 C and D, DEC-0026, DEC-0027, DEC-0189,
`anchors.taktus.md` M1.22 and both anchor pages. They set how pull requests merge today, and
none of them settles the method.

## 3. What you must decide

- **C1:** the method of five rings.
- **C2:** whether the ruleset stops requiring an up-to-date branch, behind a guard for `main`.
- **C3:** whether a draft is verified locally, with CI starting at *ready*.

## 4. What you need to know to decide

| Target | Today | After |
|---|---|---|
| A pull request that changes documentation only | 26–27 min | about 1.5 min |
| A typical change of code | 26–27 min | about 8–10 min |
| CI minutes spent re-checking a caught-up branch | 44 % | only real conflicts |
| From *ready* to merge | 52 min median | about 15 min |

The targets are measured after each phase, not promised.

## 5. Options

### Option A — all three (recommended)
- **C1:** all four phases.
- **C2:** the owner switches the ruleset once the guard and the automaton exist.
- **C3:** a draft is verified locally, enforced by a hook.

### Option B — phases 1 and 2 only, `strict` kept

## 6. What is blocked

Nothing.

## 7. How to answer

"CI-Methode: C1 A, C2 A, C3 A."

## Outcome

**Decided:** 2026-10-13
**Answer:** Option A: "CI-Methode: C1 A, C2 A, C3 A." (the owner's words)
**Reasoning given:** none beyond the answer.
**What it does not change:**
- what a gate checks: every check still runs, after the merge if not before it;
- that Taktus never deploys itself (ADR-0013 D);
- M1.22: the session merges its own green pull request;
- who changes the ruleset: the owner.
**Recorded in:** this pull request:
- ADR-0096;
- `docs/research/2026-10-13-ci-review.md`;
- CLAUDE.md §9;
- `docs/process/next-task.md`;
- `docs/roadmap.md`;
- `docs/status.md`;
- the issues of the four phases.
