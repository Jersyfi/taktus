# DEC-0048 — Live tests with a credential run scheduled, capped, on main

**Category:** NON-BLOCKING
**Raised in:** NEED-0011 and NEED-0012, raised in [#52](https://github.com/Jersyfi/taktus/pull/52); recorded in PRNUM
**Issue:** none; the owner answered in the brief of 2026-10-07 before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-07
**Written after the answer:** the owner answered in the brief of 2026-10-07; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Two tests need a credential: the repository connector against the real hosting service, and the
coding worker against its real agent. NEED-0011 and NEED-0012 asked the owner for a credential
each, to be stored as a repository secret and used by the pipeline that runs on every pull
request.

The repository is public. A coding-agent key in that pipeline costs money on every run. And a
repository secret is readable by every workflow of the repository that names it.

## 2. Why you are being asked

How often a test may spend, and how much, is a limit (M3.10 of `anchors.taktus.md`). Where a
secret may be read is the owner's to set before the owner provides it.

**Sources checked:** the vision (principle 8, cost control; principle 12, production-ready), the
ADRs (ADR-0005 on limits, ADR-0028 on needs), both anchor pages (M3.10) and the register
(NEED-0011, NEED-0012, NTC-0018). None says on which events a credentialed test may run.

## 3. What you must decide

On which events the live tests run, under which limit, and where their secrets sit.

## 4. What you need to know to decide

- **A pull request's pipeline** runs on every push to every pull request. A test there runs dozens
  of times a day.
- **An environment** is a named set of secrets at the hosting service that only a job naming it
  can read, and only from the branches the environment admits.
- **A fork** is a copy of the repository under someone else's account; its workflows must never
  reach these secrets.

## 5. Options

### Option A — scheduled, capped, on main, in an environment (recommended)

- **Meaning:** live tests that need a credential do not run on pull requests. They run on a
  schedule and on manual dispatch, on `main` only, never for a fork. Each run carries a spend cap,
  and its consumption is recorded like any other run's. The secrets sit in an environment only
  those workflows can use.
- **Consequence:** a change that breaks the real service is found within a week, not before
  merge. Spend is bounded per run and per week.
- **Effort:** a workflow of its own, a check that no other workflow names the environment, and
  both needs rewritten.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — on every pull request, as NEED-0011 and NEED-0012 said

- **Meaning:** the secrets are repository secrets read by the pull request pipeline.
- **Consequence:** spend grows with every push, and every workflow can reach the secrets.
- **Effort:** none beyond the needs as written.
- **Reversibility:** the secrets would have to be rotated.

## 6. What is blocked

NEED-0011 and NEED-0012: they are rewritten before the owner provides them.

## 7. How to answer

"DEC-0048: Option A." or "DEC-0048: Option B."

## Outcome

**Decided:** 2026-10-07
**Answer:** Option A, as the owner gave it. NEED-0011 and NEED-0012 are redesigned before they are
provided. Live tests needing a credential do not run on pull requests: they run on a schedule and
on manual dispatch, on `main` only, never for a fork. Each run carries a spend cap; its
consumption is recorded like any other run. The secrets sit in an environment only those
workflows can use. Both needs are rewritten with steps that match, so that the owner provides
them once, correctly.
**Reasoning given:** the repository is public. A coding-agent key in CI costs money on every run
and is a secret every workflow able to read it can reach.
**Recorded in:** PRNUM: `.github/workflows/live.yml` and its check
`tests/tools/test_live_workflow.py`; the live connector step removed from `ci.yml`; NEED-0011 and
NEED-0012 rewritten. As built, the cap is the variable `LIVE_SPEND_CAP_USD` of the environment,
set by the owner when the owner provides the first credential: a job that spends refuses to start
without it. The connector test spends no money at the hosting service; its run is bounded by the
job's time limit, and its consumption — the calls it made — is kept as the run's evidence, as
every scheduled run's is.
