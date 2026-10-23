# DEC-0220 — The cluster guide said the object store is not backed up

**Category:** DEFECT
**Raised in:** the pull request of #445, the administration guide a stranger can follow
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`deploy/k8s/README.md` §9 listed the artifact volume among what no backup covers. Since #322 the
chart's backup archives the object store beside the dump, by default (`backup.objects`), and §11
of the same file says so. The guide *Restoring* takes §9 as its last part, so a reader was told
both things.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

§9 now names only the execution state claim as not backed up.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0220" in an issue.

## Outcome

**Corrected:** 2026-10-23
**What was wrong:** §9 of the cluster guide said the artifact volume is not backed up.
**Why it was wrong:** the pull request of #322 changed §11 and the chart, and did not carry §9 along.
**What it now says:** what the backup covers.
**What changed in substance:** nothing.
**Recorded in:** the pull request of #445
