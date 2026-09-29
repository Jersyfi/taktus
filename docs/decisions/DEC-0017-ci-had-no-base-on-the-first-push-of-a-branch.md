# DEC-0017 — CI had no base on the first push of a branch

**Category:** DEFECT
**Raised in:** [#22](https://github.com/Jersyfi/taktus/pull/22), which adds the needs request and the status report
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

When Taktus implements an issue, it puts the change on a branch named `taktus/<issue>` and
reads the verdict of the repository's pipeline on that branch before it opens the pull request.
For that to work, the pipeline must run on a plain push to such a branch, and the repository
says it does: the pipeline's own configuration names `taktus/**` among the branches it runs
on, and the record of the first run says "CI runs on a plain push".

One gate in that pipeline — the check that a change touched its documentation — compares the
push with what the branch was before it. The first push of a new branch has no "before": the
hosting service sends a placeholder made of zeros, which no comparison can use. The gate then
stops with "base not found" and fails. Every first push of a `taktus/**` branch would therefore
have failed the pipeline, and Taktus would have read a red verdict for a change that was fine.
The status gate added in the same pull request would have inherited the same fault.

Nobody had seen it, because no push to a `taktus/**` branch has ever happened: the only such
branch so far was opened by a test through a pull request, which compares with the pull
request's base and has no such gap.

## 2. Why you are being asked

You are not. The repository said the pipeline runs on a push to `taktus/**` and it would have
failed on the first one — a contradiction between what is documented and what the pipeline
did. Entry M1.4 of `docs/decisions/anchors.taktus.md` makes the correction the session's,
recorded here. The gate is made correct, not weaker (M2.3's last sentence): it compares with
`main` where before it compared with nothing.

## 3. What you must decide

Nothing. The correction is made; the record keeps the precedent findable.

## 4. What you need to know to decide

- The comparison base of the documentation gate and the status gate: on a pull request, the
  pull request's base branch; on a push to `main`, the commit `main` was at before the push;
  on the first push of any other branch, now `main` — which is what a `taktus/**` branch was
  cut from.
- A pull request that follows the push compares with its base as before; nothing changes for
  the checks a reviewer sees.
- The fault could not be seen locally: `make gates` on a developer's machine compares with
  `origin/main`, which exists.

## 5. Options

None for the owner. What the session did: gave both gates a base that exists on the first push
of a branch, in the pipeline's configuration, with the reason in a comment beside it.

## 6. What is blocked

Nothing. The first live run's pipeline verdict, which this would have broken, is still waiting
on NEED-0001 to NEED-0003.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0017" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-21
**What was wrong:** `.github/workflows/ci.yml` runs on pushes to `taktus/**` so that P-03 can
read a verdict, and gave `make gate-docs` the push's "before" commit as its base; on the first
push of a branch that value is the null sha, the gate cannot resolve it, and fails. The status
gate was about to be wired the same way.
**Why it was wrong:** the pipeline's verdict on the branch P-03 creates is the one verdict the
process reads before opening a pull request; a verdict that is red for every new branch
regardless of its content is not a verdict. `docs/runs/2026-09-19-the-run-that-stopped.md` §4 said the push runs the same
gates as a pull request, and it would not have.
**What it now says:** the base is the pull request's base branch on a pull request, the
previous commit on a push to `main`, and `origin/main` on any other push, for `make gate-docs`
and for `tools/check_status.py`, with the reason beside each.
**What changed in substance:** nothing in the software; one expression in the pipeline. The
first push of a `taktus/**` branch now compares with `main`.
**Recorded in:** [#22](https://github.com/Jersyfi/taktus/pull/22)
