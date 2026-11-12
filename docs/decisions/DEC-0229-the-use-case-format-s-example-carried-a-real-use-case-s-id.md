# DEC-0229 — The use case format's example carried a real use case's id

**Category:** DEFECT
**Raised in:** the pull request of release 1.0 (DEC-0228), area platform
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`docs/usecases/README.md` shows the front matter of a use case as an example. The example said
`id: UC-4.10` with the title of deviation detection, a real use case whose own file says other
things — another state, another version. A search for the line `id: UC-4.10` under
`docs/usecases/` found two files, and a reader who counted use cases by their id line counted
UC-4.10 twice.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

The example now carries `UC-0.0`, the placeholder `TEMPLATE.md` already uses, which no use case
carries.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0229" in an issue.

## Outcome

**Corrected:** 2026-11-07
**What was wrong:** the format's example front matter named UC-4.10, a real use case.
**Why it was wrong:** the example was taken from a real use case and kept when its file changed.
**What it now says:** the placeholder `UC-0.0`.
**What changed in substance:** nothing.
**Recorded in:** the pull request of release 1.0 (DEC-0228)
