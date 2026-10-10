# NEED-0022 — A key for the second coding agent

**Kind:** credential
**Raised in:** [#PRNUM](https://github.com/Jersyfi/taktus/pull/PRNUM), for issue #154
**Issue:** [#NEEDISSUE](https://github.com/Jersyfi/taktus/issues/NEEDISSUE)
**Needed by:** 2026-11-06
**Foreseeable since:** [#PRNUM](https://github.com/Jersyfi/taktus/pull/PRNUM), which built the second coding worker against a stand-in for its agent

## 1. What is needed

An API key for the second coding agent — the one `workers/codex/` wraps, whose vendor is named
in that directory — **of its own for live tests**, in a project of that vendor's platform with a
monthly spend limit. It is stored as a secret of the **environment `live`** at the hosting
service, beside the first coding agent's key: a set of secrets and variables that only a job
naming it can read, and only on `main`. With it, a scheduled workflow can run the second coding
worker against the real agent instead of only against the stand-in that imitates the agent's
output.

## 2. Why

Taktus now has two coding workers, so that a coding step has an alternative adapter: when one is
removed, the other serves the step (issue #154). The second one is proven against a stand-in that
writes what the agent's documentation says it writes. That proves the worker's mechanics —
boundaries, tokens per step, the frame, stop and resume — and not that the real agent behaves
that way. The first coding worker's first live run found exactly such a gap (DEC-0038). The
second worker reads its tokens per step from a file the agent keeps for itself, which is not a
documented interface; only a run against the real agent shows that it works.

The live test this key is for is issue #208. It runs in the workflow `live`
(`.github/workflows/live.yml`), on the first of every month and by dispatch, on `main` only,
never on a pull request: the repository is public, and a key that costs money must not be
reachable from a pull request (DEC-0048, DEC-0058).

## 3. By when

**2026-11-06**, so that #208 can be built and run within `0.4.0`, before the second tenant's
first processes depend on a coding step.

If it is not there by then: nothing breaks. #208 waits, the second coding worker stays proven
against the stand-in only, and an instance should not rely on it for real work until its live
test has passed once.

## 4. How to provide it

1. **Create a project for live tests** on the platform of the vendor that `workers/codex/` names,
   in your organisation there, separate from any project that does real work, so that what the
   tests spend is visible and limited on its own.
2. **Set a monthly budget on that project with a hard limit**: the platform then answers
   requests with an error once it is reached. It is the backstop behind the cap per run of
   step 5. Its amount is yours; USD 10 a month is enough for a monthly run and a few dispatches.
3. **Create an API key in that project**, restricted to the project, named for what it is for —
   "taktus live tests, second coding agent".
4. **Add the key as a secret of the environment `live`**, named `SECOND_CODING_AGENT_API_KEY`:
   *Settings → Environments → live → Environment secrets → Add secret*. Paste it into that form
   only. Not as a repository secret: a repository secret is readable by every workflow.
5. **Keep the cap per run as it is.** The variable `LIVE_SPEND_CAP_USD` of the environment
   `live` (USD 0.50 today, DEC-0058) bounds this test's run as it bounds the first coding
   worker's. If you want a different cap for this test, say so in this issue: a cap is yours
   (M3.10).

Two ways exist to authenticate this agent: an API key, or the login of a subscription. **The API
key is recommended**: a subscription's usage is shared with your own interactive use, its
window is not published, and its login renews itself in a file the worker does not keep.

## 5. What it must never be

- **Never a key of a project that does real work.** A fault in a test must not spend from it or
  require revoking it.
- **Never your subscription's login file.** See section 4.
- **Never a repository secret**, and never in an environment that admits a branch other than
  `main`: only the workflow `live`, on `main`, may read it.
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. A
  session that receives it cannot un-receive it, and this repository is public.

Where it goes instead: the secret store of the environment `live`, under the name of step 4.

## 6. What happens next

Write in this issue: **"NEED-0022 is provided."** The next session records it first and takes up
#208: the second coding worker's image with its agent pinned, and its live test — one small
assignment against the real agent, under the cap, its tokens per step against the agent's own
total, its ledger kept as the run's evidence. After that pull request merges, the session starts
the workflow `live` once by hand on `main` and records what the run cost.

## 7. How to confirm

Without revealing anything: in the vendor's console, the live-test project lists the key with no
usage yet and shows the budget you set. In *Settings → Environments → live*, the secret
`SECOND_CODING_AGENT_API_KEY` is listed beside `CODING_AGENT_API_KEY`, and the branch rule reads
`main` and nothing else. After the first run, the project shows that run's usage and nothing
else.
