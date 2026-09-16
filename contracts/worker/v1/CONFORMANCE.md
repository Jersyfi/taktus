# Checking a worker against the contract

This page is for someone who has built a worker — a program that takes work from Taktus over HTTP
and reports back over a stream of events — and wants to know whether it satisfies the contract.
You do not need to know anything else about Taktus to follow it.

The *conformance suite* is a program that talks to your worker exactly as Taktus would, and
reports, for each of twelve numbered checks, whether your worker did what the contract requires.
The contract itself is in [README.md](README.md) in this directory; the checks are its section 7.

---

## 1. What you need

- Your worker, running, reachable at an HTTP address. Any language, any host.
- Python 3.13 or newer and [`uv`](https://docs.astral.sh/uv/) on the machine that runs the suite.
  Install `uv` with `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- A clone of this repository:

```
git clone https://github.com/Jersyfi/taktus
cd taktus
uv sync
```

The suite lives in the `taktus` package and runs as `uv run taktusctl`. It imports nothing from
the rest of Taktus; it needs no database and no configuration.

---

## 2. Running it

```
uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
```

Add `--json report.json` to also write a machine-readable report. The exit code is `0` when every
check passed, `1` when one failed, and `2` when nothing failed but something could not be proven
(section 6 says how to make it provable).

Options you may need:

| Option | When |
|---|---|
| `--task task.json` | your worker does nothing useful without a real task. The file holds `goal`, `acceptance` and `inputs` as the contract defines them (README §3). Without it the suite sends a generic task and expects the worker to do its default work. |
| `--credential NAME` | the name under which the suite references a credential (default `TAKTUS_CONFORMANCE_CREDENTIAL`). See check W-08 below. |
| `--worker-log FILE` | your worker writes a log file the suite can read. It is scanned for W-08. |
| `--timeout SECONDS` | one assignment may take longer than five minutes. |
| `--idle-timeout SECONDS` | your worker is silent for more than a minute between two events — a training job between epochs, say. |

To see what a passing run looks like, run the suite against the reference worker in this
repository — a shell wrapper with no AI at all:

```
python3 workers/script/worker.py --port 9000 &
export TAKTUS_CONFORMANCE_CREDENTIAL=any-random-value
uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
```

(Set the variable before starting the worker so that both processes carry it.)

---

## 3. What the suite does to your worker

It reads your capabilities, asks for an estimate, and then posts up to five assignments. Each has
a purpose, and the report names it:

| Assignment | What it is | What it proves |
|---|---|---|
| `main` | your default work, in a frame that allows every capability you declare | the stream is well-formed and resumable, consumption comes per step, boundaries exist, tool arguments are hashed, artifacts are consistent |
| `narrowed` | the same work, with one tool you used in `main` taken out of the frame | you refuse that tool instead of using it silently |
| `stopped` | the same work, with a stop requested while a step runs | the stop takes effect at the next boundary, with a checkpoint |
| `resumed` | the same work, resumed from that checkpoint | you produce no artifact a second time |
| `over-limit` | the same work, with a limit set below your own estimate | you reject before starting instead of failing later |

Every assignment references one credential by name. The suite never sends a value; Taktus never
would either. The value reaches your worker through its environment, put there by whoever started
it.

Each assignment is independent: its own id, its own stream. Your worker may run them one after
the other; the suite never runs two at once.

---

## 4. The twelve checks in plain words

| Check | In plain words | If it fails, fix this |
|---|---|---|
| **W-01** | `GET /v1/capabilities` answers with a valid declaration that names at least one way your use is measured: money (`currency`), a subscription window (`quota`) or held hardware (`compute`). | The body must match `Worker.json#/$defs/Capabilities`. The report quotes the first field that does not. |
| **W-02** | `POST /v1/estimate` answers with an estimate. It may be rough. It must exist. | Return `confidence` (`low` is fine), `wall_seconds` and `steps`, plus the quantities of your consumption kinds. Never answer with an error because you cannot know. |
| **W-03** | Your events are numbered 1, 2, 3, without a gap. Each SSE message carries the number in its `id` field and the event type in its `event` field. A client that reconnects with `Last-Event-ID: 7` — or `?after=7` — gets 8 onwards and nothing else. The stream ends with `assignment.finished`, and `GET /v1/assignments/{id}` agrees with it. | Keep every event of an assignment; number them once, in order; serve the tail on reconnect through both mechanisms. |
| **W-04** | After every step, before the next one starts, you report what that step used. | Emit `consumption.reported` with the step's id before `step.started` of the next step. Reporting everything at the end is exactly what this check refuses. |
| **W-05** | At least once per assignment you emit `step.boundary`: a point where your work is saved and you could stop. | Emit it after every step, with a `checkpoint_ref` you can resume from. |
| **W-06** | When a stop is requested, you finish the running step, emit its boundary, and end with outcome `stopped` and that boundary's `checkpoint_ref`. No step starts after that boundary. | Do not abort the running step. Do not start another one. The `checkpoint_ref` in `assignment.finished` and in the assignment state must be the boundary's. |
| **W-07** | A tool the frame does not allow is refused visibly, not used silently. | When a step wants a tool that is not in `allowed_tools` or matches `forbidden`, emit `tool.called` with `refused: true` and a `reason`, and do not run it. |
| **W-08** | The value of a credential never appears anywhere the suite can see: no event, no artifact, no state, no log. | Never print, echo or store a credential value. Report its presence if you must, never its content. |
| **W-09** | `tool.called` carries the arguments as a hash — `sha256:` and 64 hex characters — never in clear. | Hash the arguments; do not add a field with them in clear. |
| **W-10** | When your estimate does not fit the limits, you do not start: the answer to `POST /v1/assignments` is `finished` / `rejected` with a reason, and the stream has exactly one event. | Compare the estimate with `limits` before the first step. Rejection is a state, not an HTTP error: answer `201` with the rejected state. |
| **W-11** | An assignment resumed from a checkpoint produces nothing it produced before that checkpoint. Every artifact you announce is listed under `GET /artifacts` with the same digest, and its bytes hash to that digest. | Remember, per checkpoint, which artifacts exist. Serve every artifact's bytes at its `uri`. |
| **W-12** | Removing your worker from a running Taktus changes quality or cost but breaks no process. | Nothing yet: this check is not run by the suite. See section 7. |

The report attributes a malformed event to the check that owns that event type: a bad
`arguments_digest` is a W-09 failure, a bad `consumption.reported` a W-04 failure, and so on. Base
fields, unknown types and transport faults are W-03.

---

## 5. Reading a failure

```
  failed       W-04  consumption.reported appears per step, not only at the end
               requires: every step that started has a consumption.reported with its step_id
                         before the next step starts; ...
               observed: main run asg_conf_1c3f...: consumption for step 'inspect' was reported
                         at seq 15, after the next step had started
               see: contracts/worker/v1/README.md §4 Events
```

Four lines: which check, what the contract requires, what your worker did, and where the README
states the rule. The JSON report carries the same fields (`requirement`, `observed`, `section`)
plus any further findings under `details`.

---

## 6. When a check is inconclusive

`inconclusive` means the suite could not create the situation the check is about. The report says
what would make it conclusive. The common cases:

| Check | Why | What to do |
|---|---|---|
| W-07 / W-09 | your worker called no tool during `main`, so nothing could be placed outside the frame and no hash could be inspected | give it a task that uses a tool: `--task` |
| W-06 | the assignment finished before the stop arrived; or the step the suite waits for never started | make the default work take more than a moment, or supply a task with several steps |
| W-08 | the suite had no value to look for | set the same random value under the credential's name in your worker's environment and in the environment of the suite before starting both: `export TAKTUS_CONFORMANCE_CREDENTIAL=$(openssl rand -hex 16)` |
| W-10 | your estimate is zero for every quantity, so no limit can lie below it | estimate something; a shell script still takes seconds of `cpu` |
| W-11 | the stopped run produced no artifact before its checkpoint, so a repeat could not be observed | produce an artifact in an early step, or supply a task that does |

A check that failed can leave later checks inconclusive: without a boundary there is nothing a
stop can land on, without a stopped run there is nothing to resume. Fix the failure first.

---

## 7. What a pass means

A worker whose report shows eleven `passed` and one `pending` satisfies the contract as far as a
suite talking to one endpoint can tell.

It is not yet *verified*. Taktus grades adapters in three levels — `experimental`, `verified`,
`reference` — and *verified* needs two things: this suite passed, and the *removal test* passed.
The removal test takes the worker out of a running Taktus and shows that processes still run,
only at different quality or cost. It needs processes, and the part of Taktus that runs processes
does not exist yet. The report states this: `removal test pending; verified: no`. Nothing in this
repository marks a worker *verified* today.

---

## 8. Proving the suite itself

A suite that only ever passes proves nothing. The reference worker can be started with a *fault*
— `python3 workers/script/worker.py --fault W-04` — that makes it break exactly one check; the
suite must then fail on that check and on no other. `make gate-conformance` does this for every
fault. `python3 workers/script/worker.py --list-faults` prints them. If you want to see the suite
catch something before trusting it with your own worker, this is the way.
