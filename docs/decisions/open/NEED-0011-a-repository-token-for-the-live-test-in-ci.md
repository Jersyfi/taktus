# NEED-0011 — A repository token for the live test in CI

**Kind:** credential
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** [#55](https://github.com/Jersyfi/taktus/issues/55)
**Needed by:** 2026-10-20
**Foreseeable since:** [#13](https://github.com/Jersyfi/taktus/pull/13), which wrote the live test of the repository connector to run only where a token is set; raised on 2026-10-01, after the audit of the register found that local runs have one and CI does not

## 1. What is needed

A token for a **scratch repository** that exists for this test alone, and that repository's
name, both given to the repository's CI as a secret and a variable. With them, CI runs the one
test that skips there today: the repository connector against the real hosting service
(`tests/adapters/connectors/test_repository_live.py`).

## 2. Why

Every other test of the repository connector runs against a fake of the hosting service. A fake
proves the connector's mechanics; only the real service proves that its interface still keeps
what the connector relies on — one open pull request per branch, a mark in a body, a reference
that exists once. The live test checks exactly that, each step twice across two connectors with
no memory of each other.

Today it runs only when a person runs it on their own machine. A change that breaks the
connector against the real service merges with every check green, because the check that would
fail is skipped.

## 3. By when

**2026-10-20**, before the deployment pull request, which is the next change to touch the
connector's wiring.

If it is not there by then: nothing breaks, and nothing changes from today — the live test
skips in CI and says why, and the connector's promise against the real service is checked only
when someone runs it by hand.

## 4. How to provide it

1. **Create a scratch repository** under your account, private, with nothing in it but a README.
   The test creates a branch, a pull request, a comment and a label there on every CI run, and
   removes the branch and closes the pull request afterwards. **Never this repository**: the
   test acts in whatever repository it is given.
2. **Create a fine-grained token restricted to that one repository**, with these permissions
   and no others: contents read and write, pull requests read and write, issues read and write
   (the labels), metadata read. Give it an expiry; the renewal is raised as its own needs request
   one week before (CREDENTIALS.md).
3. **Add it to this repository's CI** as a repository secret named `LIVE_REPOSITORY_TOKEN`
   (Settings → Secrets and variables → Actions → Secrets). Paste it into that form only.
4. **Add the scratch repository's name** as a repository variable named
   `TAKTUS_LIVE_REPOSITORY`, in the form `owner/name` (the same page, Variables).

The workflow already reads both, in a step of its own that runs only this test, so that the
token is in no other test's environment (`.github/workflows/ci.yml`, step `live connector test`).
Without the variable the step is skipped, as the test is today.

## 5. What it must never be

- **Never a token for this repository**, nor for any repository other than the scratch one.
- **Never the token NEED-0002 provided**, which acts for the requesting identity in this
  repository. This one is its own, for one repository, with an expiry.
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. A
  session that receives it cannot un-receive it, and this repository is public.

Where it goes instead: the CI service's secret store, under the name of step 3.

## 6. What happens next

Tell the session: **"NEED-0011 is provided."** The next CI run of any pull request runs the step
`live connector test` instead of skipping it. Pull requests opened
by a dependency bot receive no repository secrets from the CI service, and the test skips on
them as before.

## 7. How to confirm

Without revealing anything: in the next CI run, the step `live connector test` has run and
passed, and its log shows the tests of `test_repository_live.py` as passed, not skipped. In the scratch
repository, the closed pull requests list the ones the test opened.
