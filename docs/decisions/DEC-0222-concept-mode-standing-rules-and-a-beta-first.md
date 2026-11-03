# DEC-0222 — Concept mode, two standing rules, and a beta first

**Category:** NON-BLOCKING
**Mode entry:** M3.6 and M3.15 (how work lands and what holds a release back), DEC-0197 (handing a task to Taktus)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-27, after its measurement of where the time went
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-28
**Written after the answer:** the owner answered in conversation on 2026-10-28; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Between 2026-10-13 and 2026-10-23 work happened in 50 of 256 hours. Throughput followed the
hours worked, and the long pauses were the session waiting for the owner's answer while ready
work lay in the backlog. Inside the work, waiting for CI and the pull requests a use case needed
of its own cost a further share. The owner asked for development in packages: a session builds a
whole milestone locally and lands it in one pull request.

## 2. Why you are being asked

How work lands on `main`, which acts need the owner each time, and what holds a release back
are the owner's (M3.6, M3.15, DEC-0197).

**Sources checked:** CLAUDE.md §8 and §9, `docs/decisions/anchors.taktus.md`, DEC-0197, DEC-0199,
`docs/roadmap.md`, and the owner's other repository's record of the same practice.

## 3. What you must decide

Five points: packages, installing release candidates, handing tasks to Taktus, what holds
`1.0.0` back, and a date.

## 4. What you need to know to decide

The measurement is in the session's report of 2026-10-23. CI after *ready* took a median 7.2
minutes; it was not the bottleneck.

## 5. Options

### Option A — the five points as proposed (recommended)

### Option B — keep working as before

## 6. What is blocked

Nothing; work went on while the owner decided.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-28
**Answer:** Option A, with the owner's refinements:

1. **Concept mode, not a new default.** "Das soll bitte nur soweit festgehalten werden, dass auf
   den Wunsch abgeweicht werden kann" (only so far that work may depart from the default on the
   owner's wish): one pull request per change stays the default; on the owner's word a session
   builds a milestone or a concept whole, on one branch, in one pull request. A new use case may
   be written beside its implementation there ("Passt für mich"). Open questions are still
   thought through and decided for Taktus wherever the project yields a worked solution; a
   strategic question, one that sets direction, is still presented to the owner.
2. **Installing a release candidate:** "Ja", as a standing rule once the upgrade test on its tag
   is green, reported afterwards.
3. **Handing tasks to Taktus:** "Ja", as a standing rule, again after a fix.
4. **A beta first.** The four weeks and the six stages describe how the business introduces
   Taktus, and must not keep the project from delivering a finished version: first a beta with
   every feature of `1.0.0`, which the business installs; its findings, fixes and requests are
   worked in after that. NEED-0028 was answered by the business; NEED-0029 was settled outside
   the repository.
5. **No date in the repository.** The pace comes from the way of working above.

**Reasoning given:** speed, while the bar stays: "wir müssen einmal einen Entwicklungsstand
hinbekommen, dass wir damit dann weiter testen können, ob das gesamtkonzept von Taktus
funktioniert" (the project must reach a state on which the whole concept can be tested).
**What it changes:**

- CLAUDE.md §9: concept mode beside the default of one pull request per change, and its
  exception for a new use case; §8: a strategic question is raised even where a source points one
  way.
- `tools/check_usecases.py`: on a branch `concept/<name>`, a new use case may change beside its
  implementation; a changed or removed one still may not. Two tests hold it.
- `docs/decisions/anchors.taktus.md`: M1.25 (installing a release candidate) and M1.26 (handing a
  task to Taktus); M3.15 names the exception.
- `docs/process/README.md`: a session may add `to-taktus`.
- `docs/roadmap.md`: `1.0.0-beta` and its four conditions; no milestone's completion waits for a
  stage of the second tenant; those issues move to the milestone `introduction`.
- `docs/usecases/AF-03-software-operations.md`: the stages are the business's introduction after
  the beta, and §9 no longer gates a release.
- NEED-0028 and NEED-0029: provided; their content stays outside the repository.

**Recorded in:** this pull request
