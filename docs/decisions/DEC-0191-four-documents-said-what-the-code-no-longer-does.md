# DEC-0191 — Four documents said what the code no longer does

**Category:** DEFECT
**Raised in:** the pull request that records the DevOps review of 2026-10-12 (DEC-0187)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The review found four statements that the code or the register had overtaken:

- `deploy/k8s/README.md` opened with "the cluster execution adapter and the install are not"
  built. The adapter has been built since 2026-10-08, and section 10 of the same file says the
  installed instance runs every worker step through it.
- Section 10 of the same file listed the backup on the installed instance under *Waits*. It has
  run there since 2026-10-12 (NEED-0025, `docs/status.md`).
- `docs/architecture/project-structure.md` named a directory `deploy/observability`, which does
  not exist, and left out `deploy/backup`, which does.
- `docs/architecture/platform.md` §4 said the run engine does not call `admit_capacity` yet.
  `execute_run.py` calls it before a worker step is admitted. The sentence was already untrue in
  the commit that wrote it.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

Each file now says what holds. The backup's own limit, that the artifacts are not in it, is
stated where the backup is, and its fix is #322.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0191" in an issue.

## Outcome

**Corrected:** 2026-10-12
**What was wrong:** the chart's guide said the cluster adapter and the install were not built and that the backup waits; the project structure named a directory that does not exist; the platform document said capacity admission is not wired.

**Why it was wrong:** the pull requests that built them (#65, #66, #67) and the one that wired the admission did not carry these sentences along.
**What it now says:** what the code does.
**What changed in substance:** nothing.
**Recorded in:** the pull request that records DEC-0187
