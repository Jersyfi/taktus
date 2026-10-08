# NEED-0011 — A repository token for the live test in CI

**Kind:** credential
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52); rewritten in [#59](https://github.com/Jersyfi/taktus/pull/59) for scheduled, main-only live tests (DEC-0048), before it was provided
**Issue:** [#55](https://github.com/Jersyfi/taktus/issues/55)
**Needed by:** 2026-10-20
**Foreseeable since:** [#13](https://github.com/Jersyfi/taktus/pull/13), which wrote the live test of the repository connector to run only where a token is set; raised on 2026-10-01, after the audit of the register found that local runs have one and CI does not

## 1. What is needed

A token for a **scratch repository** that exists for this test alone, and that repository's
name, both stored in an **environment named `live`** at the hosting service — a set of secrets
that only a job naming it can read, and only on `main`. With them, a scheduled workflow runs the
one test that cannot run today: the repository connector against the real hosting service
(`tests/adapters/connectors/test_repository_live.py`).

## 2. Why

Every other test of the repository connector runs against a fake of the hosting service. A fake
proves the connector's mechanics; only the real service proves that its interface still keeps
what the connector relies on — one open pull request per branch, a mark in a body, a reference
that exists once. The live test checks exactly that, each step twice across two connectors with
no memory of each other.

Today it runs only when a person runs it on their own machine. A change that breaks the
connector against the real service merges unnoticed. With the token, the workflow `live`
(`.github/workflows/live.yml`) runs the test every Monday and whenever someone starts it by hand.

It never runs on a pull request (DEC-0048). The repository is public: a secret a pull request's
pipeline can read is reachable from every workflow that names it. A break is therefore found
within a week of the merge, not before it.

## 3. By when

**2026-10-20**, before the deployment pull request, which is the next change to touch the
connector's wiring.

If it is not there by then: nothing breaks, and nothing changes from today. The workflow `live`
runs, says in a notice that the scratch repository is not configured, and runs nothing. The
connector's promise against the real service is checked only when someone runs the test by hand.

## 4. How to provide it

1. **Create a scratch repository** under your account, private, with nothing in it but a README.
   The test creates a branch, a pull request, a comment and a label there on every run, and
   removes the branch and closes the pull request afterwards. **Never this repository**: the
   test acts in whatever repository it is given.
2. **Create a fine-grained token restricted to that one repository**, with these permissions
   and no others: contents read and write, pull requests read and write, issues read and write
   (the labels), metadata read. Give it an expiry; the renewal is raised as its own needs request
   one week before (CREDENTIALS.md).
3. **Create the environment `live`** in this repository, unless NEED-0012 created it already:
   Settings → Environments → New environment, name `live`. Under *Deployment branches and tags*
   choose *Selected branches and tags* and add the rule `main`, and nothing else. Leave
   *Required reviewers* off: the runs are scheduled and nobody is there to approve them.
4. **Add the token as a secret of that environment**, named `LIVE_REPOSITORY_TOKEN`: in the
   environment `live`, *Environment secrets* → *Add secret*. Paste it into that form only. Not as
   a repository secret: a repository secret is readable by every workflow.
5. **Add the scratch repository's name as a variable of that environment**, named
   `TAKTUS_LIVE_REPOSITORY`, in the form `owner/name`: in the same environment,
   *Environment variables* → *Add variable*.

This test spends no money: the hosting service does not charge for these calls. Its run is
bounded by the job's time limit of ten minutes. `LIVE_SPEND_CAP_USD`, the cap NEED-0012 asks
for, is not needed for it.

## 5. What it must never be

- **Never a token for this repository**, nor for any repository other than the scratch one.
- **Never the token NEED-0002 provided**, which acts for the requesting identity in this
  repository. This one is its own, for one repository, with an expiry.
- **Never a repository secret**, and never in an environment that admits a branch other than
  `main`: only the workflow `live`, on `main`, may read it.
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. A
  session that receives it cannot un-receive it, and this repository is public.

Where it goes instead: the secret store of the environment `live`, under the names of steps 4
and 5.

## 6. What happens next

Write in the issue: **"NEED-0011 is provided."** The next session records it first, starts the
workflow `live` once by hand on `main`, and records the outcome here. From then on the workflow
runs every Monday at 07:00 UTC on its own.

## 7. How to confirm

Without revealing anything: in this repository's *Actions*, the workflow `live` has a run whose
job `connector` passed its step `live connector test`, and the artifact `live-connector-<run>`
lists the tests of `test_repository_live.py` as passed, not skipped. In the scratch repository,
the closed pull requests list the ones the test opened. In *Settings → Environments → live*, the
branch rule reads `main` and nothing else.

## Outcome

**Provided:** 2026-10-08
**How:** **superseded, not provided.** The owner accepted the proposal and judged weekly runs
excessive; the session, deciding how Taktus connects to the repository service, chose an app of
its own (DEC-0058). The scratch repository becomes one more installation of that app, so no
personal token is needed for it, and the live tests run monthly. NEED-0013 asks for the app.
**Superseded by:** NEED-0013
**Confirmed by:** nothing to confirm: no token was created.
**Recorded in:** [#97](https://github.com/Jersyfi/taktus/pull/97)
