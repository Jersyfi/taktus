# `codex` — the second coding worker

A second vendor's coding agent behind the worker contract v1. This directory is the only place
in the repository that names the agent. Everywhere else it is a worker that offers the
capabilities `code.read`, `code.edit`, `code.test` and `shell.sandboxed`, and a process names
those, never the product (ADR-0003).

It exists so that a coding step has an alternative adapter (#154). The first coding worker,
[`claudecode/`](../claudecode/README.md), offers the same four capabilities, and a step that
requires them is served by either. With both in one worker pool, the removal test withholds
either one and the verdict is *changed*: the other serves the step
(`tests/integration/test_two_coding_workers.py`). It passes the same conformance suite as the
first, in both authentication modes, faults included
(`tests/conformance/test_worker_v1_second_coding.py`).

```
python3 workers/codex/worker.py --port 9011 --auth api-key
```

`--auth` is required: `api-key` or `session`. Neither is assumed. The worker imports nothing
from `src/taktus` and nothing from the first coding worker: removing one must not touch the
other.

## How it drives the agent

The agent runs in its documented non-interactive mode, `exec --json`, one process per
assignment, in the workspace. A resumed assignment runs `exec … resume <thread>` with the thread
its checkpoint names. The agent's stream is JSON lines: `thread.started` names the thread,
`item.started` and `item.completed` carry what the agent does, and `turn.completed` carries the
turn's usage.

### Boundaries

**Every item that acts is one step**: a command the agent runs (`command_execution`), a change
it makes to files (`file_change`), and a call of any other tool. When the item completes, the
worker commits the workspace, writes a checkpoint — the agent's thread, the commit, the step
count and the artifacts so far — and emits `step.boundary`. A stop lands there: the worker ends
the agent, and the assignment finishes `stopped` with that checkpoint (W-06). Items that do not
act — the agent's reasoning, its plan, its messages — are no steps.

Before the agent starts, the hosts the task says it needs (`task.inputs.hosts`) are held against
the frame as a step of their own (W-13). The agent reaches a host from a command it runs, so
the step's tool is `shell.sandboxed`. At the end, the agent's last message is the `report`
step, whose artifacts are the `summary` and the `changeset`, as the first coding worker's are.

### Consumption

**Tokens come per step, from the agent's session file.** The agent's stream carries tokens only
for the whole turn. Its session file, under `CODEX_HOME/sessions/`, carries the running total
after every model response, written before the agent acts on that response. When a step starts,
the worker reads that total and reports the difference to the total it read before: the tokens
of the response that started the step. The closing message's tokens go to the `report` step,
and so does anything the session file did not show: the `report` step settles the difference
to the agent's own total for the turn. The sum over the steps is therefore never less than what
the agent says it used. The split between steps rests on timing: the worker reads the total when
an item appears, and the agent's next response takes a model's round trip. A response written
before the worker read the item would be counted with that item's step, and the total would
still be right.

Every report carries `tokens_in` and `tokens_out`, and `tokens_by_model` by price kind —
uncached input, cache read, cache write, output — for the model the session file names (or
`--model`). **The agent reports no money.** In `api-key` mode the worker declares consumption in
currency and estimates it (`--estimate-currency`), and the money follows from the tokens and a
price table (`docs/architecture/accounting.md` §5a). A currency limit is held against the
estimate before the start; a budget that must hold while the agent runs is given in tokens.

**The limits are the ceiling while the agent runs.** At every boundary the running total is
held against `limits.tokens` and, in `session` mode, `limits.quota` in steps. Once one is
reached, the agent is ended there, and the assignment ends `stopped` with the checkpoint and
`limit` naming the kind (W-14).

**Subscription quota is a proxy.** In `session` mode the worker declares consumption kind
`quota` with a five-hour window and the unit `steps`, and reports one unit per step. When the
agent reports its usage limit as reached, the assignment ends `stopped` at the last boundary:
an exhausted window blocks, it does not cost more.

The session file is not a documented interface. If a version of the agent stops writing the
running total there, every step reports zero and the `report` step settles the whole turn: the
total stays right, and a token limit can then no longer halt the agent while it runs. The live
test (#208) checks that the tokens per step add up to the agent's own total.

### Authentication

| `--auth` | The credential the assignment references | What the agent receives it as |
|---|---|---|
| `api-key` | `CODING_AGENT_API_KEY` (or `--credential NAME`) | its API key variable, `CODEX_API_KEY` |
| `session` | `CODING_AGENT_SESSION` (or `--credential NAME`) | its login file, `auth.json` in its home, the one its `login` command writes |

The names are the first coding worker's, so that a process runs unchanged on either; each
worker receives the value for its own agent. The value reaches the worker's environment under
that name and reaches the agent as the table says, and nothing else of the worker's environment
does. The worker never logs a value (W-08). In `session` mode the login file is written into the
agent's home, readable by the worker's user alone, while an assignment runs, and removed when the
last one ends. The agent may renew the tokens in that file while it runs; the worker does not
keep the renewed file. When the login no longer works — the agent answers with an authentication
error — the assignment halts at the last boundary with the cause, and resumes from that
checkpoint once a working login is supplied.

The agent's home is under the worker's state (`<state>/agent`, `CODEX_HOME`), so that its threads
outlive a job and nothing of the machine's own login is used.

### The frame

**The agent asks no permission per call** in its non-interactive mode. The worker holds the frame
in two ways:

1. **The sandbox.** The frame chooses the agent's sandbox: `workspace-write` when it allows
   anything that changes the workspace (`code.edit`, `code.test`, `shell.sandboxed`),
   `read-only` otherwise. Network access is granted only when the frame allows a host; the unit's
   egress allowlist is the wall around which hosts. `--sandbox none` runs the agent without a
   sandbox of its own, for a unit where that sandbox cannot work; the unit is then the only
   isolation.
2. **The record.** Every item is held against the frame when it appears. An item outside it is
   emitted as `tool.called` with `refused: true`, the agent is ended, the workspace is reset to
   the last boundary, and the assignment fails (W-07). A command may already have begun when the
   worker sees it; the reset is what keeps anything it did from surviving.

| Capability | The agent's items |
|---|---|
| `code.read` | a command that only reads: `cat`, `head`, `tail`, `ls`, `rg`, `grep`, `wc`, `nl`, `pwd`, `stat`, `tree`, `sed -n`, without redirection into a file |
| `code.edit` | a change to files (`file_change`) |
| `code.test` | a command that runs tests (`pytest`, `npm test`, `make test`, …), when the frame allows `code.test` |
| `shell.sandboxed` | any other command |

A call of another tool — a tool server's, a web search — is outside every frame this worker
can be given, and is refused.

## What an assignment does

As the first coding worker's: the workspace is cloned or started empty under
`<state>/workspaces/<id>`, a baseline is committed and tagged, the task becomes the agent's
prompt, every completed item that changed the workspace is committed and announced as an
artifact `change-N` of kind `patch`, and at the end the `summary` and the `changeset` are
published. A task that names `after` gains one last step: the worker — not the agent — runs its
command in the workspace without a shell and without a credential, and publishes its standard
output as the artifact the task names (W-18).

## What it cannot do

- **Stop inside an item.** A boundary lies after an item completes.
- **Refuse a command before it starts.** See *The frame*: it is refused when it appears, and its
  effect is reset.
- **Report money.** See *Consumption*.
- **Fetch from the web as a tool of its own.** It does not offer `web.fetch`.

## Fault injection

`--fault NAME` makes the worker violate exactly one conformance check; `--list-faults` prints
the table (the same checks as the first coding worker's, W-12 excepted). The meta-test in
`tests/conformance/test_worker_v1_second_coding.py` runs every fault and asserts that the suite
fails on that check and only on that check.

## The fake agent

The gate runs this worker against `fake_agent.py`: a stand-in that takes the same options, reads
the same authentication, writes the same stream and the same session file, and really performs
its fixed plan of items in the workspace. It proves the worker's mechanics without an account
and deterministically; it does not think. `FAKE_AGENT_EXPIRE_AFTER=N` fails the turn with an
authentication error after N items, `FAKE_AGENT_WINDOW_AFTER=N` reports the usage limit as
reached; `--agent-env` passes those through. Its usage overruns the worker's default estimate,
so that the suite's `tight` run can show the halt at a limit; `FAKE_AGENT_USAGE_FACTOR` scales
every count. The real agent is run with `--agent codex` (the default), and a live run needs a
credential the operator supplies.

## Not yet

The image, the agent pinned to one exact version, and the live test against the real agent in
the workflow `live` are #208, which waits for a credential (NEED-0022). An instance reads one
worker today (`TAKTUS_WORKER`); configuring both coding workers on one instance is #209.
