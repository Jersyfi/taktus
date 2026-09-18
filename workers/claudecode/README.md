# `claudecode` — the coding worker

A coding agent's command-line interface behind the worker contract v1. This directory is the
only place in the repository that names the agent; everywhere else it is a worker that offers
the capabilities `code.read`, `code.edit`, `code.test`, `shell.sandboxed` and `web.fetch`, and
a process names those, never the product (ADR-0003).

It passes the same conformance suite as the reference worker, faults included
(`tests/conformance/test_worker_v1_coding.py`), and it is the first worker that does something
useful: given a goal and an acceptance list, it changes code in a workspace and hands back the
change.

```
python3 workers/claudecode/worker.py --port 9010 --auth api-key
```

`--auth` is required: `api-key` or `session`. Neither is assumed. Its own image is
`Dockerfile` in this directory; the control plane reaches it through the execution port like
any worker (`docs/architecture/contracts.md` §2.4).

## What the agent does not do by itself, and what this worker does about it

### Boundaries

A coding agent does not emit step boundaries. This worker defines one: **every tool call the
agent completes is one step.** The agent's stream carries each call (`tool_use`) and its
result (`tool_result`); at the result, the worker commits the workspace, writes a checkpoint,
and emits `step.boundary`. The checkpoint is the agent's session identifier, the commit, the
step count and the artifacts announced so far, under `<state>/checkpoints/`. An assignment that
resumes from it continues the same session (`--resume`) in the same workspace and announces
no artifact it announced before (W-11).

A stop is real at that point: the worker waits for the running call's result, ends the agent,
and finishes `stopped` with that boundary's checkpoint (W-06). The agent may have started its
next call before it was ended; whatever it left in the workspace stays there uncommitted, and
the first step after the resume commits it — nothing is lost, and nothing is announced twice.
A step that does not reach its result within the stop's ceiling ends the agent anyway; the
last boundary is the checkpoint.

One more step exists that is not a tool call: before the agent starts, the hosts the task says
it needs (`task.inputs.hosts`) are held against the frame as a step of their own, so that a
refused host is visible and lands on a boundary (W-13); and at the end, the agent's summary is
a `report` step whose artifact is that text.

### Consumption

**Tokens come per step.** Every assistant message of the agent carries the tokens it used
(input, cache creation, cache read, output); the worker attributes them to the step the
message's tool call starts and reports `tokens_in` and `tokens_out` in `consumption.reported`
before the next step starts (W-04).

**Money comes only at the end.** The agent reports `total_cost_usd` once, with its final
result. The worker reports it as `currency` on the last step, after that step's boundary and
before `assignment.finished`. This is a real limitation, not a detail: admission control on a
currency limit works against the estimate, not against a running total — a run cannot be
stopped by its cost mid-assignment, only refused before it starts. Tokens are exact per step;
money is settled per assignment.

**Subscription quota is a proxy.** In `session` mode the worker declares consumption kind
`quota` with a five-hour window and the unit `turns`, and reports one unit per step. The agent
does not expose what the window actually counts; turns are what it reports. When the agent
reports the window as exhausted, the assignment ends `stopped` at the last boundary with that
cause — an exhausted window blocks, it does not cost more.

The estimate is rough and honest about it: `confidence: low`, the configured expectation of
one assignment (`--estimate-*`). The limits are checked against it before the agent starts
(W-10): a missing limit of the worker's kind, an estimate above it, too few `max_steps` or a
deadline before the estimated end all reject.

### Authentication

| `--auth` | The credential the assignment references | What the agent receives it as |
|---|---|---|
| `api-key` | `CODING_AGENT_API_KEY` (or `--credential NAME`) | its API key variable |
| `session` | `CODING_AGENT_SESSION` (or `--credential NAME`) | its long-lived subscription token, the one its `setup-token` command issues |

The value reaches the worker's environment under that name — injected by the execution
adapter at runtime, or put there by whoever starts an endpoint worker — and reaches the agent
under its own variable, and nothing else of the worker's environment does. The worker never
logs a value (W-08). An assignment that does not reference the credential, or a worker whose
environment does not carry it, rejects the assignment before the agent starts, naming what is
missing. A session that expires mid-run — the agent answers with an authentication error —
halts at the last boundary: `assignment.finished` with outcome `stopped`, the checkpoint, and
the cause. It is not retried, and it is not abandoned; once the credential works again, the
assignment resumes from that checkpoint.

The agent's own configuration directory is under the worker's state (`<state>/agent`), so that
its sessions outlive a job and nothing of the machine's own login is used.

### The frame

The agent is given every tool this worker maps (`--tools`), may use exactly those the frame
allows (`--allowedTools`, in its don't-ask permission mode), and is denied the rest by its own
permission system at the moment of the call. The worker sees the attempt in the stream, emits
`tool.called` with `refused: true`, ends the agent and finishes the assignment `failed` (W-07).
Hosts the same way: a `web.fetch` names the URL's host, and a host outside `allowed_hosts` is
refused (W-13); with no allowed host, fetching is not approved at all. What the agent runs in
a shell can reach whatever the network allows — the container adapter's allowlist is the wall,
the worker's refusal is the record.

| Capability | The agent's tools |
|---|---|
| `code.read` | Read, Grep, Glob |
| `code.edit` | Edit, Write, MultiEdit, NotebookEdit |
| `shell.sandboxed` | Bash |
| `code.test` | Bash, for a command that runs tests (`pytest`, `npm test`, `make test`, …) — without `shell.sandboxed`, any other command is refused |
| `web.fetch` | WebFetch, when the frame allows at least one host |

## What an assignment does

`context.workspace` of kind `git` with a `location` is cloned into `<state>/workspaces/<id>`
(the branch `ref` if given); any other kind starts empty. The workspace is made a repository if
it is not one, and a baseline commit is made. The task's goal, acceptance and inputs become the
agent's prompt. Every completed tool call that changed the workspace is committed and announced
as an artifact `change-N` of kind `patch`; the final summary is the artifact `summary`.

## What it cannot do

- **Stop inside a tool call.** A boundary lies after a call's result; a shell command that runs
  for an hour is one step, and a stop waits for it up to the ceiling.
- **Cost per step.** See *Consumption*: money is known at the end only.
- **Guarantee a resumable session after a hard kill.** A session ended inside a call may leave
  the agent's transcript with a call and no result; the agent's `--resume` may then refuse it,
  and the assignment fails with the agent's reason. A stop through the contract never does
  this.
- **Choose its tools by judgement.** The frame chooses; the agent is denied, never persuaded.

## Fault injection

`--fault NAME` makes the worker violate exactly one conformance check; `--list-faults` prints
the table (the same checks as the reference worker's, W-12 excepted). The meta-test in
`tests/conformance/test_worker_v1_coding.py` runs every fault and asserts that the suite fails
on that check and only on that check.

## The fake agent

The gate runs this worker against `fake_agent.py`: a stand-in that takes the same options,
reads the same authentication variables, writes the same stream, and really performs its fixed
plan of tool calls in the workspace. It proves the worker's mechanics without a subscription
and deterministically; it does not think. `FAKE_AGENT_EXPIRE_AFTER=N` makes it fail with an
authentication error after N tool results, `FAKE_AGENT_WINDOW_AFTER=N` makes it report an
exhausted window; `--agent-env` passes those through. The real agent is run with
`--agent claude` (the default), and a live run needs a credential the operator supplies.

## Configuration

| Option | Variable | Meaning |
|---|---|---|
| `--auth` | `CODING_AGENT_AUTH` | `api-key` or `session`; required |
| `--credential` | `CODING_AGENT_CREDENTIAL` | the credential's name; default per mode above |
| `--agent` | `CODING_AGENT_COMMAND` | the agent's command line; default `claude` |
| `--model` | `CODING_AGENT_MODEL` | passed to the agent as `--model` |
| `--agent-env` | `CODING_AGENT_ENV` | names of variables passed on to the agent |
| `--max-turns` | | the agent's turn limit per assignment (default 50) |
| `--estimate-tokens-in`, `--estimate-tokens-out`, `--estimate-currency`, `--estimate-steps`, `--estimate-wall-seconds` | | the estimate |
| `--port`, `--state-dir` | `TAKTUS_UNIT_PORT`, `TAKTUS_UNIT_STATE_DIR` | the launch convention |
