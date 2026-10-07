# NEED-0012 — A coding agent key for CI

**Kind:** credential
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52); rewritten in [#59](https://github.com/Jersyfi/taktus/pull/59) for scheduled, capped, main-only live tests (DEC-0048), before it was provided
**Issue:** [#57](https://github.com/Jersyfi/taktus/issues/57)
**Needed by:** 2026-10-20
**Foreseeable since:** [#10](https://github.com/Jersyfi/taktus/pull/10), which built the coding worker and listed "a live run of the coding worker against its real agent in CI" as needing a credential; the status file called it "a decision not yet raised" until the audit of 2026-10-01 found it

## 1. What is needed

An API key for the coding agent, **of its own for live tests**, in a workspace with a low monthly
spend limit, and the most one run may spend. Both are stored in the **environment named `live`**
at the hosting service — a set of secrets and variables that only a job naming it can read, and
only on `main`. With them, a scheduled workflow can run the coding worker against the real agent
instead of only against the stand-in that imitates the agent's output.

## 2. Why

The coding worker's suite runs against a fake agent. That proves the worker's mechanics —
boundaries, consumption per step, refusal, stop and resume — and not that the real agent still
behaves the way the worker reads it. The first live run found such a gap: the real agent's
stream differed from the stand-in's, and the worker undercounted its tokens (DEC-0038). Today
only a person running `tools/first_run.sh` with their own key can find the next one.

The live test this key is for does not exist yet (DEC-0046). It is written in the pull request
that follows this need, as a job of the workflow `live` (`.github/workflows/live.yml`). That
workflow never runs on a pull request (DEC-0048): the repository is public, and a key that costs
money would spend on every push and be reachable from every workflow that names it. It runs every
Monday and whenever someone starts it by hand, on `main` only.

## 3. By when

**2026-10-20**, with the other needs of the deployment, so that the agent's behaviour is checked
before Taktus runs its coding steps on the platform.

If it is not there by then: nothing breaks, and nothing changes from today. The worker is proven
against the stand-in, and a change in the real agent is found by the next person who runs a live
run, or by a run that fails.

## 4. How to provide it

1. **Create a workspace for live tests** in the coding agent provider's console, separate from
   the one NEED-0001's key lives in, so that what the tests spend is visible and limited on its
   own.
2. **Set a monthly spend limit on that workspace.** It is the backstop behind the cap of step 6:
   whatever a fault in the workflow does, the provider stops at it. Its amount is yours.
3. **Create an API key** in that workspace, named for what it is for — "taktus live tests".
4. **Create the environment `live`** in this repository, unless NEED-0011 created it already:
   Settings → Environments → New environment, name `live`. Under *Deployment branches and tags*
   choose *Selected branches and tags* and add the rule `main`, and nothing else. Leave
   *Required reviewers* off: the runs are scheduled and nobody is there to approve them.
5. **Add the key as a secret of that environment**, named `CODING_AGENT_API_KEY`: in the
   environment `live`, *Environment secrets* → *Add secret*. Paste it into that form only. Not as
   a repository secret: a repository secret is readable by every workflow.
6. **Add the cap per run as a variable of that environment**, named `LIVE_SPEND_CAP_USD`: the
   most one run may spend, in US dollars, as a number such as `0.50`. It is a limit and yours
   (M3.10). For orientation: the first live run's coding step cost $6.09 over eight attempts at a
   real change, about $0.76 an attempt (`docs/runs/first-run.md`); the live test's assignment is
   one file in an empty workspace and is smaller. The run receives the cap as its budget, and the
   worker halts at its next boundary before crossing it. A job that spends refuses to start when
   the variable is not set.

## 5. What it must never be

- **Never NEED-0001's key.** That one runs real work; a fault in a test must not spend from it or
  require revoking it.
- **Never a subscription token.** A subscription's usage is shared with your own interactive use
  and expires mid-run (`CREDENTIALS.md`, coding agent subscription token).
- **Never a repository secret**, and never in an environment that admits a branch other than
  `main`: only the workflow `live`, on `main`, may read it.
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. A
  session that receives it cannot un-receive it, and this repository is public.

Where it goes instead: the secret store of the environment `live`, under the names of steps 5
and 6.

## 6. What happens next

Write in the issue: **"NEED-0012 is provided."** The next session records it first and takes up
the backlog issue that writes the live test: the coding worker with the real agent, one small
assignment, under the cap, its tokens against its estimate, its ledger kept as the run's evidence
like any other run's. After that pull request merges, the session starts the workflow `live` once
by hand on `main` and records what the run cost.

## 7. How to confirm

Without revealing anything: in the provider's console, the live-test workspace lists the key with
no usage yet and shows the spend limit you set. In *Settings → Environments → live*, the secret
`CODING_AGENT_API_KEY` and the variable `LIVE_SPEND_CAP_USD` are listed, and the branch rule reads
`main` and nothing else. After the first run, the workspace shows that run's usage and nothing
else.
