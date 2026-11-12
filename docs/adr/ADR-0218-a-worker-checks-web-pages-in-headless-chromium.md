# ADR-0218 — A worker checks web pages in headless Chromium

**Status:** accepted · builds on ADR-0007 (the worker contract) and ADR-0115 (an estimate as a
rule) · UC-03 B-7.07, B-7.08, B-7.09, DEC-0228

## Context

Three rows of UC-03 look at the business's web application the way a person does: friction in
a flow clicked through (B-7.07), the day's acceptance of the end-to-end flows after a merge
(B-7.08), and a penetration test from a fresh context, as an outside attacker would (B-7.09).
UC-03 §8 names the capability they need, a browser for synthetic flows, as a worker, not built.

An HTTP check (`httpcheck`, B-1.06) reads a status and a body. It runs no script, types into
no field and follows no click. A page of a modern web application is what its scripts make of
it.

## Decision

### 1. A worker of its own, `workers/browser/`

The worker drives headless Chromium through Playwright, the browser automation library most
widely used for this (ADR-0150). A step names the capability `browser.check` and gives the
worker its checks in `task.inputs.checks`. A check names a URL, the steps done on the page —
click, fill, press, go to, wait — the texts the page must show and those it must not, and the
status it must answer with.

Each check is one step of the assignment, with a boundary and a checkpoint after it. The step's
artifact `check-N` is its report: what was found against what was asked, the console's errors,
the failed and refused requests, the digest of the visible text and of a screenshot, and
`passed`. A last step gathers every report into the artifact `report`, with the count that
passed and the names of those that failed. A check that does not hold is a finding, read by the
process's rules; the step fails only where the browser could not run.

### 2. The contract around the steps is the reference worker's

The worker loads `workers/script/worker.py` and gives it other steps, another tool and its own
estimator: a step per check at a fixed number of compute seconds, `per_item` over `checks`. The
event stream, consumption, boundaries, stop, handover, steering, the outbound binding, the
limits and the faults stay in one file. The image copies that file beside the worker's own two.

### 3. The frame holds inside the browser

Every host a check's URL names, and every host the task declares, is held against
`allowed_hosts` before the browser starts (W-13). Inside the browser every request to any other
host is aborted and named in the report. A credential arrives by its name; a `fill` step names
it by `value_env`, and the browser types its value. No event, artifact or log carries it.

### 4. Its driver is pinned

The extra `browser` of `pyproject.toml` pins Playwright, and `workers/browser/requirements.txt`
pins the same version and its closure for the image, which installs the headless Chromium of
that release. The tests run with the extra, as they do with `mlbench`.

## Alternatives

- **The HTTP check with a script engine.** It would be a browser written again, less well.
- **A browser inside the coding worker.** A coding agent may use one for itself; a process step
  that checks a flow is a step of its own, with its own frame and its own report.
- **A browser as a connector.** A connector calls an outward API with an effect it declares. A
  browser runs foreign scripts in a sandbox for a while: that is what a worker is for.
- **A worker of its own contract code.** It would be a second copy of the contract to keep.

## Consequences

- `workers/browser/`: `worker.py`, `browse.py`, `Dockerfile`, `requirements.txt`, its README.
- `pyproject.toml`: the extra `browser`; `uv.lock`.
- `.github/workflows/images.yml`: the image `taktus-worker-browser`.
- `tests/conformance/test_worker_v1_browser.py`, `tests/workers/test_browser_worker.py`.
- `blueprints/software-operations`: B-7.07, B-7.08 and B-7.09 use it.

## Where this promise ends

- A check reads what Chromium shows. A layout that is wrong but carries the expected texts
  passes; the screenshot's digest says only that something changed, not what.
- The tests that run the browser need Chromium on the machine. Where it is missing they are
  skipped with the command that installs it; CI runs them only where its runner has it.
- The worker does not run on an accelerator, and one check is planned at a fixed number of
  compute seconds; a slow page that takes longer is halted at the limit, as any step is.
- A penetration test by this worker is what its checks state. It finds what a check asks for —
  another user's data shown, an admin route answered — and nothing it was not asked to try.
- The removal test of the worker is pending, so it is not *verified*.
