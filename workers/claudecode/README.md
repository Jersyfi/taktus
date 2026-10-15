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
(input, cache creation, cache read, output) and names its model; the worker attributes them to
the step the message's tool call starts and reports `tokens_in`, `tokens_out` and
`tokens_by_model` — per model as the agent names it, per price kind — in `consumption.reported`
before the next step starts (W-04). The agent streams one message in several lines. Each line
carries the message's usage so far, and the output grows from line to line. A message is
counted once, at its highest count: what a later line adds goes to the step the line belongs to.
When a line carries text and the call comes in a later line, the tokens wait for the call. A
message that calls no tool — the closing summary — gives its tokens to the `report` step. So
does whatever the session total in the agent's final line holds beyond what the stream showed.
Until this was so, a message whose text came before its call was reported with zero tokens. In
the live run of #74 the worker counted each message at its first line and reported a twentieth
of the output its agent used (#278). An assignment that ends before the final line — stopped
at a limit, a window or a stop — has only the stream's count.

**Money comes per step, at the worker's price table** (DEC-0202). The agent reports money only
once, `total_cost_usd` with its final result, and an assignment that ends otherwise reported
none: the run for #277 used about USD 10 against a limit of USD 5. So in `api-key` mode the
worker prices every step's tokens itself, per model and price kind, at its price table, and
reports the money as `currency` with the step. The table is `prices.json` in this directory, in
the shape of `contracts/model/v1`'s `PriceTable`: the provider's published prices, a cache write
at the one-hour lifetime the agent uses (twice the input price), so that a step is priced at
most at what it costs. A model the table names with or without its snapshot date is priced at
its prices; one it does not name, at the dearest price of each kind in the table — unpriced is
never free, and a limit then halts early rather than late. The operator replaces the table with
`--price-table` (`CODING_AGENT_PRICE_TABLE`, a file or the table as JSON); a new price is a new
table version, and the worker's log names the version at its start. A table in another currency
than the worker reports stops the worker at its start. When the agent's final result arrives,
what its own total holds beyond the priced steps is reported on the last step, after its
boundary and before `assignment.finished`; that holds for an assignment that ends `stopped` or
`failed` with a result, too. A total below the priced steps reports nothing more: the steps'
money stands.

**The limits are the ceiling while the agent runs.** At every boundary the worker holds its
running total against the limits: `limits.currency` in its currency, in `api-key` mode;
`limits.tokens`, input and output apart; and, in `session` mode, `limits.quota` in turns. Once
one is reached, the worker ends the agent there, as it does for a stop, and the assignment ends
`stopped` with that boundary's checkpoint, `limit` naming the kind, and the numbers in `reason`
(W-14). The resumed assignment continues the same session in the same workspace. The worker
cannot know what the agent's next call will use, so it halts on what was reported, not on an
expectation. The call that crossed the limit has already run; it is the one step the limit
yields by, a few cents for a turn of the instance's runs. The control plane gives the worker
what is left of the run's money as its currency limit (ADR-0005, seventh amendment).

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

The agent calls its provider's API to work at all, and that host is in no step's frame. On an
execution kind that enforces a unit's reach (`container`, `cluster`), the operator names it for
this worker: `TAKTUS_EXECUTION_SERVICE_HOSTS`, or `TAKTUS_WORKER_<NAME>_EXECUTION_SERVICE_HOSTS`
for a named worker, `serviceHosts` in the chart. The unit reaches it for an assignment and for
the conformance suite, never for a probe; the frame the worker holds tool calls against stays the
step's (ADR-0089).

**Launched, the worker needs its authentication mode in its unit's environment.** An execution
adapter starts the image's own command, so there is no `--auth` to pass, and without
`CODING_AGENT_AUTH` the worker exits before it is ready. The operator names it for this worker,
with any other variable the worker reads (`CODING_AGENT_MODEL`, `CODING_AGENT_ENV`):
`TAKTUS_EXECUTION_UNIT_ENV=CODING_AGENT_AUTH=api-key`, or
`TAKTUS_WORKER_<NAME>_EXECUTION_UNIT_ENV` for a named worker, and in the chart:

```yaml
execution:
  workers:
    - name: coding
      image: <registry>/<image>:<version>
      unitEnv: {CODING_AGENT_AUTH: api-key}
```

Every unit of the worker receives them — a probe's too, so that it can answer. They are visible
configuration and never a secret: the credential itself stays a credential (ADR-0090).

### The frame

The agent is offered only the tools the frame allows (`--tools`) and may use exactly those
(`--allowedTools`, in its don't-ask permission mode). Until 2026-10-14 it was offered every tool
this worker maps; it then called one the frame did not allow, and three runs on the instance
ended so (#424). A call outside the frame is still refused by the agent's own permission system
at the moment of the call. The worker sees the attempt in the stream, emits
`tool.called` with `refused: true`, ends the agent and finishes the assignment `failed` (W-07).
Hosts the same way: a `web.fetch` names the URL's host, and a host outside `allowed_hosts` is
refused (W-13); with no allowed host, fetching is not approved at all. What the agent runs in
a shell can reach whatever the network allows — the container adapter's allowlist is the wall,
the worker's refusal is the record.

A tool the agent is not offered is one it never calls, so no refusal of it can be seen. The
worker therefore states what it offers, before the first step of every assignment, as
`reach.stated` (contract §4, ADR-0098). `tools` is the offer in the contract's terms: the
capabilities of the agent's tools below, `code.test` beside `shell.sandboxed` where the frame
allows it, and `web.fetch` where the task names hosts the worker holds against the frame itself.
`hosts` is stated only where no fetch is offered: then the hosts the task names are the only
ones a call can name. With a fetch offered, the agent may name any host, and the hosts are held
at the moment of the call. The conformance suite reads the statement: a fetch the frame took
out, left out of the statement and called nowhere, passes W-07 and W-13. Before the statement,
the suite against the real agent ended `incomplete` on both.

| Capability | The agent's tools |
|---|---|
| `code.read` | Read, Grep, Glob |
| `code.edit` | Edit, Write, MultiEdit, NotebookEdit |
| `shell.sandboxed` | Bash |
| `code.test` | Bash, for a command that runs tests (`pytest`, `npm test`, `make test`, …) — without `shell.sandboxed`, any other command is refused |
| `web.fetch` | WebFetch, when the frame allows at least one host |

## What an assignment does

`context.workspace` of kind `git` with a `location` is cloned into `<state>/workspaces/<id>`
(the branch `ref` if given), through the unit's proxy where the execution kind gives one — `git`
receives the proxy variables, as the agent does (#306); any other kind starts empty. A
workspace that an earlier attempt of the same assignment left is removed first, unless the
assignment resumes from a checkpoint (#280). The workspace is made a repository if it is not
one, and a baseline commit is made and tagged. The task's goal, acceptance and inputs
become the agent's prompt. Every completed tool call that changed the workspace is committed and
announced as an artifact `change-N` of kind `patch`; at the end, the artifact `summary` is the
agent's own account of what it did, and the artifact `changeset` (`application/json`) is every
file changed since the baseline with its full content — text as text, anything else as base64,
and `executable: true` on a file the index records with mode `100755` —
and every file deleted, by path: what a run hands to a repository connector to put the change
on a branch (`repository.branches.create`), so that the worker never pushes and never holds a
credential to the repository.

A task that names `after` gains one last step, after the summary and the changeset: the worker —
not the agent — runs its `command` in the workspace as the agent left it, without a shell and
with no credential in its environment, for at most five minutes. Its standard output becomes the
artifact `after.artifact`, of kind `output`, byte for byte. A command that exits with anything
but 0 publishes nothing and the assignment ends `failed` with the exit status and the end of what
it wrote to its error output (W-18). P-03 runs the repository's generator of the closing section
this way (ADR-0053).

## What it cannot do

- **Stop inside a tool call.** A boundary lies after a call's result; a shell command that runs
  for an hour is one step, and a stop waits for it up to the ceiling.
- **Know its money exactly while it runs.** See *Consumption*: per step the money is the
  worker's table's, and the agent's own figure arrives with its final result. A price the
  provider changed and the table did not follow is money held at the old price until the table
  is replaced.
- **Guarantee a resumable session after a hard kill.** A session ended inside a call may leave
  the agent's transcript with a call and no result; the agent's `--resume` may then refuse it,
  and the assignment fails with the agent's reason. A stop through the contract never does
  this.
- **Choose its tools by judgement.** The frame chooses; the agent is denied, never persuaded.
- **Go on past its limit of turns** (`--max-turns`). The agent ends with a result that names
  the error `error_max_turns` and carries no text. The assignment ends `stopped` at the last
  boundary the agent reached, with its checkpoint and the turns in its reason, and names no
  `limit`, because turns are not one of the assignment's limits (#380). The work is kept; a
  resume continues the same session for as many turns again. Until #380 it failed, and seven
  of fifteen coding steps on the instance lost their work so.

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
exhausted window; `--agent-env` passes those through. Its usage is fixed and overruns the
worker's default estimate — about 620 000 input tokens against 60 000, where the real agent
used 1.8 to 4.3 times the estimate in the first live run — so that the suite's `tight` run
can show the halt at a limit; `FAKE_AGENT_USAGE_FACTOR` scales every token count, and
`FAKE_AGENT_WRITE`, a JSON object of path to content, adds those files to its change, so that a
process test can give a change a file of its choosing. Its messages name a model the price
table prices, and it ends on `--max-turns` as the real agent does. The real agent is run with
`--agent claude` (the default), and a live run needs a credential the operator supplies.

## The agent's version

The agent is pinned to one exact version, written in one file: `agent-version` in this
directory. Today it is 2.1.295. The image installs that version and no other; a build whose file
names `latest`, a tag or a range fails. A release therefore carries the version the file names
at the release's tag, and two builds of one tag carry the same agent. The live test installs the
same version from the same file, so that it checks what a release ships.
`tests/governance/test_image_workflow.py` holds the image, the release workflow and the live job
to the file, and fails on anything but one exact version.

The agent's stream is not a stable interface. The first live run found that the real agent
wrote it differently from the stand-in, and the worker undercounted tokens (DEC-0038). A new
version of the agent is therefore taken deliberately, never by a build:

1. A pull request changes `agent-version` and nothing else of the agent. Its description names
   the old and the new version.
2. After it is merged, the workflow `live` is dispatched on `main`, or its monthly run is
   awaited. Its job `coding` runs the worker against the new version.
3. A release is tagged only after that run passed. If it failed, the worker is adapted or the
   file is set back, each in a pull request of its own.

The job `coding` says on its page when the registry has a newer release than the pin. It does
not install it.

## The live test

`tests/workers/test_coding_worker_live.py` runs this worker against the real agent on one small
assignment: one file in an empty workspace, through `taktusctl run`. The workflow `live` runs
it on `main`, monthly and by dispatch, never on a pull request (DEC-0048, DEC-0058). It installs
the agent at the pinned version (*The agent's version*). It needs the
agent's key in a file (`TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE`) and the cap per run
(`LIVE_SPEND_CAP_USD`); without either it skips and says which.

The cap is held as money, priced per step (see *Consumption*), and also as tokens, which hold
even where the table's prices were wrong. It is converted at the dearest rate the agent was measured at in the first live
run, rounded up to USD 8 per million input tokens. A quarter of that line is held back for the
one call the limit yields by; the rest is the worker's ceiling, and the worker's estimate is set
so that the run reserves exactly that ceiling (NTC-0028). The run's ledger, its output, the
conversion and this worker's log are kept as the job's evidence. The agent's own configuration
directory is not.

## Configuration

| Option | Variable | Meaning |
|---|---|---|
| `--auth` | `CODING_AGENT_AUTH` | `api-key` or `session`; required |
| `--credential` | `CODING_AGENT_CREDENTIAL` | the credential's name; default per mode above |
| `--agent` | `CODING_AGENT_COMMAND` | the agent's command line; default `claude` |
| `--model` | `CODING_AGENT_MODEL` | passed to the agent as `--model` |
| `--agent-env` | `CODING_AGENT_ENV` | names of variables passed on to the agent |
| `--max-turns` | `CODING_AGENT_MAX_TURNS` | the agent's turn limit per assignment (default 50); an operator sets it for a cluster unit through `execution.defaults.unitEnv` (ADR-0090), as the project's instance does with 150 (DEC-0193) |
| `--price-table` | `CODING_AGENT_PRICE_TABLE` | the price table every step's tokens are priced at: a file, or the table as JSON; default `prices.json` beside the worker |
| `--estimate-tokens-in`, `--estimate-tokens-out`, `--estimate-currency`, `--estimate-steps`, `--estimate-wall-seconds` | | the estimate |
| `--port`, `--state-dir` | `TAKTUS_UNIT_PORT`, `TAKTUS_UNIT_STATE_DIR` | the launch convention |
