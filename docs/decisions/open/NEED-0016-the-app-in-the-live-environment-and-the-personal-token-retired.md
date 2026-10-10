# NEED-0016 — The app in the live environment, and the personal token retired

**Kind:** action
**Raised in:** [#108](https://github.com/Jersyfi/taktus/pull/108)
**Issue:** [#109](https://github.com/Jersyfi/taktus/issues/109)
**Needed by:** 2026-10-31
**Owner's answer:** 2026-10-10: the session does steps 1 and 2 and tells the owner when the token can be revoked; step 3 stays the owner's.
**Foreseeable since:** [#108](https://github.com/Jersyfi/taktus/pull/108), where the repository connector learned to act as Taktus's own app (ADR-0033) and the live test was moved onto it

## 1. What is needed

Three acts, all with what already exists; nothing new is created at the service.

1. **The app in the environment `live`.** The workflow `live` runs the repository connector's
   test against the real service once a month, as Taktus's own app, on the scratch repository
   (NEED-0013). It needs the app's identifier and private key as two secrets of that
   environment, and the scratch repository's name as a variable of it.
2. **The app on your workstation.** `tools/first_run.sh` acts as the app when your `.env` names
   the app's identifier and the file of its private key.
3. **The personal token retired.** Once the two steps above work, the token of NEED-0006 is
   used by nothing. It is revoked at the service and its file deleted.

## 2. Why

DEC-0058 decided that Taktus acts as an app of its own, not as you. Issue #99 built that into the
connector (pull request #108). Until these three acts are done, the live test runs nothing — the
job says so in a notice — and every pull request a run on your workstation opens still appears as
yours (issue #50). A personal token that nothing uses is a credential that can leak and buys
nothing.

## 3. By when

**2026-10-31**, before the workflow's next monthly run on 2026-11-01.

If it is not there by then: that run says "nothing ran", and the connector's interface to the
real service goes another month without a test. A half-done step 1 — the variable without the two
secrets — makes the run fail, on purpose: half a configuration is a fault, not a skip.

## 4. How to provide it

**Step 1 — the environment `live`.** In the repository's *Settings → Environments → live*, or
with the commands below from your workstation, where the key file is. Each value is read from
its file or typed at a prompt, never written on a command line.

| Kind | Name | Value |
|---|---|---|
| secret | `LIVE_APP_ID` | the app's identifier, from the app's settings page ("App ID"). It is not a secret; it is held as one so that the public log of the workflow masks it |
| secret | `LIVE_APP_PRIVATE_KEY` | the whole content of the app's private key file, the one the manifest flow wrote (NEED-0013) |
| variable | `TAKTUS_LIVE_REPOSITORY` | the scratch repository, as `owner/name` |

```sh
gh secret set LIVE_APP_ID --env live --repo Jersyfi/taktus            # prompts for the value
gh secret set LIVE_APP_PRIVATE_KEY --env live --repo Jersyfi/taktus < "<the app's key file>"
gh variable set TAKTUS_LIVE_REPOSITORY --env live --repo Jersyfi/taktus --body "<owner>/<name>"
```

A session may do step 1 on your word, as it did for NEED-0012: it uploads from the files without
printing them.

**Step 2 — your `.env`.** In the checkout's `.env`, with an editor:

```
TAKTUS_REPOSITORY_APP_ID=<the app's identifier>
TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE=<the path of the app's key file>
```

and remove the line `TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE=…`. The next `tools/first_run.sh`
prints "the connector acts as Taktus's own app".

**Step 3 — retire the token.** After the first green run of step 1 or step 2, revoke the token of
NEED-0006 in your account's token settings at the service, and delete the file that held it.

## 5. What it must never be

- **The key never pasted** into a chat, a session, an issue, a pull request or a command line,
  and never committed. It goes from its file into the environment's secret, and nowhere else.
- **Never a repository secret** and never in another environment: only the workflow `live`, on
  `main`, may read it (DEC-0048).
- **Never a second key.** The live test uses the app's one key; a rotation replaces it in the
  key file, in the cluster's secret and here, in one move (`CREDENTIALS.md`).
- **The personal token never kept "just in case".** A tenant without an app uses the token mode;
  this tenant has an app.

## 6. What happens next

Write in the issue: **"NEED-0016 is provided."** The next session records it first, dispatches
the workflow `live` once on `main` (`gh workflow run live.yml --ref main`), and records the
outcome. Afterwards the job runs on its own, on the first of every month.

## 7. How to confirm

Without revealing anything:

```sh
gh secret list --env live --repo Jersyfi/taktus      # lists LIVE_APP_ID and LIVE_APP_PRIVATE_KEY
gh variable list --env live --repo Jersyfi/taktus    # lists TAKTUS_LIVE_REPOSITORY
```

The dispatched run of the job `connector` is green, and its log carries `PASSED` for
`test_a_step_retried_after_a_restart_acts_once_on_the_real_service`, which as the app asserts
that the pull request it opened shows the app, not a person, as its author. Your account's token
list at the service no longer shows the token of NEED-0006.
