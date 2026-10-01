# NEED-0012 — A coding agent key for CI

**Kind:** credential
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** [#57](https://github.com/Jersyfi/taktus/issues/57)
**Needed by:** 2026-10-20
**Foreseeable since:** [#10](https://github.com/Jersyfi/taktus/pull/10), which built the coding worker and listed "a live run of the coding worker against its real agent in CI" as needing a credential; the status file called it "a decision not yet raised" until the audit of 2026-10-01 found it

## 1. What is needed

An API key for the coding agent, **of its own for CI**, in a workspace with a low monthly spend
limit, given to the repository's CI as a secret. With it, CI can run the coding worker against
the real agent instead of only against the stand-in that imitates the agent's output.

## 2. Why

The coding worker's suite runs against a fake agent. That proves the worker's mechanics —
boundaries, consumption per step, refusal, stop and resume — and not that the real agent still
behaves the way the worker reads it. The first live run found such a gap: the real agent's
stream differed from the stand-in's, and the worker undercounted its tokens (DEC-0038). Today
only a person running `tools/first_run.sh` with their own key can find the next one.

The live test this key is for does not exist yet. The suite's description said it did; that is
corrected as DEC-0046. It is written in the pull request that wires this key, because it cannot
be run without one.

## 3. By when

**2026-10-20**, with the other needs of the deployment, so that the agent's behaviour is checked
before Taktus runs its coding steps on the platform.

If it is not there by then: nothing breaks, and nothing changes from today — CI proves the
worker against the stand-in, and a change in the real agent is found by the next person who runs
a live run, or by a run that fails.

## 4. How to provide it

1. **Create a workspace for CI** in the coding agent provider's console, separate from the one
   NEED-0001's key lives in, so that what CI spends is visible and limited on its own.
2. **Set a monthly spend limit on that workspace.** A live test runs one small assignment —
   one file in an empty workspace — and costs cents per run; the limit is what stops a fault from
   costing more. Its amount is yours; the pull request that wires the test states its estimate
   per run and asks how often it may run (a limit, M3.10).
3. **Create an API key** in that workspace, named for what it is for — "taktus ci".
4. **Add it to this repository's CI** as a repository secret named `CODING_AGENT_API_KEY`
   (Settings → Secrets and variables → Actions → Secrets). Paste it into that form only.

## 5. What it must never be

- **Never NEED-0001's key.** That one runs real work; a fault in CI must not spend from it or
  require revoking it.
- **Never a subscription token.** A subscription's usage is shared with your own interactive use
  and expires mid-run (`CREDENTIALS.md`, coding agent subscription token).
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. A
  session that receives it cannot un-receive it, and this repository is public.

Where it goes instead: the CI service's secret store, under the name of step 4.

## 6. What happens next

Tell the session: **"NEED-0012 is provided."** The next pull request writes the live test — the
coding worker with the real agent, one small assignment, its tokens against its estimate — and a
CI step that runs it with the secret in that step's environment alone. It asks how often the
step may run, and states the cost per run.

## 7. How to confirm

Without revealing anything: in the CI workspace of the provider's console, the key is listed
with no usage yet, and the workspace shows the spend limit you set. After the next pull request,
the same page shows the usage of its runs, and nothing else.
