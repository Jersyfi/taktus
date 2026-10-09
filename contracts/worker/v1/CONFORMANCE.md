# Checking a worker against the contract

This page is for someone who has built a worker — a program that takes work from Taktus over HTTP
and reports back over a stream of events — and wants to know whether it satisfies the contract.
You do not need to know anything else about Taktus to follow it.

The *conformance suite* is a program that talks to your worker exactly as Taktus would, and
reports, for each of seventeen numbered checks, whether your worker did what the contract requires.
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
| `--hosts HOST` | your task reaches a host over the network. Name each such host (repeat the option); the main run's frame allows exactly these, and W-13 withdraws one and expects your worker to refuse it. Without it the frame allows no host, and a worker that reaches one anyway fails W-13. |
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

It reads your capabilities, asks for an estimate, and posts up to seven assignments. Then it asks
about an id it never posted, fills your declared places to see what you answer to one more, and
last posts ids you already hold a second time. Each of the seven has a purpose, and the report
names it:

| Assignment | What it is | What it proves |
|---|---|---|
| `main` | your default work, in a frame that allows every capability you declare | the stream is well-formed and resumable, consumption comes per step, boundaries exist, tool arguments are hashed, artifacts are consistent |
| `narrowed` | the same work, with one tool you used in `main` taken out of the frame | you refuse that tool instead of using it silently |
| `narrowed-hosts` | the same work, with one host you reached in `main` taken out of the frame | you refuse that host instead of reaching it silently |
| `stopped` | the same work, with a stop requested while a step runs | the stop takes effect at the next boundary, with a checkpoint |
| `resumed` | the same work, resumed from that checkpoint | you produce no artifact a second time |
| `over-limit` | the same work, with a limit set below your own estimate | you reject before starting instead of failing later |
| `tight` | the same work, with one limit set equal to your estimate — for a quantity `main` used more of than you estimated | you start, because the estimate fits; and when the running total reaches the limit, you halt at the boundary instead of starting another step |

Every assignment references one credential by name. The suite never sends a value; Taktus never
would either. The value reaches your worker through its environment, put there by whoever started
it.

Each assignment is independent: its own id, its own stream. The suite runs the seven above one
after the other, never two at once.

Next the suite asks for the state of an assignment id it never posted. It expects `404`.

Then comes the *capacity probe*, the one time the suite holds assignments side by side. It posts
as many assignments as your `max_concurrent_assignments` declares, each the same work as
`main`, and then one more. The report lists the first as `held`; the one more appears as
`one-more` only if your worker accepted it. Afterwards the suite stops every assignment of the
probe and reads its stream to the end. So start your worker idle: an assignment the suite did
not post takes a place, and the probe cannot fill what it declares.

Last comes the *repeated-id probe*. The suite posts a fresh assignment, listed as `repeated`,
and posts it again at once, while it runs. Then it posts `main` again, which has finished. Each
repeat carries an id you already hold, and the suite expects `409`. A repeat your worker
accepted appears as `repeated-running` or `repeated-finished`. Afterwards the suite stops every
assignment of the probe and reads its stream to the end.

---

## 4. The seventeen checks in plain words

| Check | In plain words | If it fails, fix this |
|---|---|---|
| **W-01** | `GET /v1/capabilities` answers with a valid declaration that names at least one way your use is measured: money (`currency`), a subscription window (`quota`) or held hardware (`compute`). | The body must match `Worker.json#/$defs/Capabilities`. The report quotes the first field that does not. |
| **W-02** | `POST /v1/estimate` answers with an estimate. It may be rough. It must exist. | Return `confidence` (`low` is fine), `wall_seconds` and `steps`, plus the quantities of your consumption kinds. Never answer with an error because you cannot know. |
| **W-03** | Your events are numbered 1, 2, 3, without a gap. Each SSE message carries the number in its `id` field and the event type in its `event` field. A client that reconnects with `Last-Event-ID: 7` — or `?after=7` — gets 8 onwards and nothing else. The stream ends with `assignment.finished`, and `GET /v1/assignments/{id}` agrees with it. | Keep every event of an assignment; number them once, in order; serve the tail on reconnect through both mechanisms. |
| **W-04** | After every step, before the next one starts, you report what that step used. | Emit `consumption.reported` with the step's id before `step.started` of the next step. Reporting everything at the end is exactly what this check refuses. |
| **W-05** | At least once per assignment you emit `step.boundary`: a point where your work is saved and you could stop. | Emit it after every step, with a `checkpoint_ref` you can resume from. |
| **W-06** | When a stop is requested, you finish the running step, emit its boundary, and end with outcome `stopped` and that boundary's `checkpoint_ref`. No step starts after that boundary. | Do not abort the running step. Do not start another one. The `checkpoint_ref` in `assignment.finished` and in the assignment state must be the boundary's. |
| **W-07** | A tool the frame does not allow is refused visibly, not used silently. | When a step wants a tool that is not in `allowed_tools`, emit `tool.called` with `refused: true` and a `reason`, and do not run it. |
| **W-08** | The value of a credential never appears anywhere the suite can see: no event, no artifact, no state, no log. | Never print, echo or store a credential value. Report its presence if you must, never its content. |
| **W-09** | `tool.called` carries the arguments as a hash — `sha256:` and 64 hex characters — never in clear. | Hash the arguments; do not add a field with them in clear. |
| **W-10** | When your estimate does not fit the limits, you do not start: the answer to `POST /v1/assignments` is `finished` / `rejected` with a reason, and the stream has exactly one event. | Compare the estimate with `limits` before the first step. Rejection is a state, not an HTTP error: answer `201` with the rejected state. |
| **W-11** | An assignment resumed from a checkpoint produces nothing it produced before that checkpoint. Every artifact you announce is listed under `GET /artifacts` with the same digest, and its bytes hash to that digest. | Remember, per checkpoint, which artifacts exist. Serve every artifact's bytes at its `uri`. |
| **W-12** | Removing your worker from a running Taktus changes quality or cost but breaks no process. | Nothing yet: this check is not run by the suite. See section 7. |
| **W-13** | A host the frame does not allow is refused visibly, not reached silently. `allowed_hosts` is the whole list of what you may reach; absent or empty means nothing. | Whenever a step reaches a host, emit `tool.called` with that `host`. When the host is not in `allowed_hosts`, set `refused: true` and a `reason`, and do not reach it. Never treat an absent list as "anything goes". |
| **W-14** | The limits are your hard ceiling while you run, not only before you start. Once what you have reported so far reaches a limit, you start no further step: you end `stopped` at the boundary you are at, with its `checkpoint_ref`, and name the limit. | Keep a running total of what you report, per quantity the limits bound. Before each step, add that step's expected demand; if the sum would exceed a limit, do not start it — emit `assignment.finished` with outcome `stopped`, the last boundary's `checkpoint_ref` and `limit` set to the kind (`currency`, `quota`, `compute` or `tokens`). |
| **W-15** | When you hold as many assignments as `max_concurrent_assignments` declares, you answer one more with `503` and a problem body, and you record nothing of it. Taktus relies on that answer: a step whose worker answers `503` waits for a free place, and Taktus does not count your assignments itself (ADR-0037). | Count the assignments you hold that have not finished. When the count has reached what you declare, answer `POST /v1/assignments` with `503` and a JSON body with `title` and `status: 503`. Keep nothing of that assignment: `GET /v1/assignments/{id}` answers `404` for it. Declare no more places than you really have. |
| **W-16** | When asked for the state of an assignment id you never received, you answer `404` with a problem body. Taktus relies on that answer: a runner that recovers a run asks you about an assignment it recorded before posting it, and a `404` means the post never arrived, so it posts the same id again (ADR-0038). | Look the id up among the assignments you hold. When it is not there, answer `GET /v1/assignments/{id}` with `404` and a JSON body with `title` and `status: 404`. Never invent a state for an id you do not hold. |
| **W-17** | When a new assignment carries an id you already hold, running or finished, you answer `409` with a problem body and start nothing. The assignment of that id stays the first one: the same `accepted_at`, its stream not begun again, its outcome unchanged. Taktus relies on that answer: it may post an id a second time when it does not know whether the first post arrived, and a `409` tells it to continue the assignment you hold (ADR-0038). | Before anything else, look up the `assignment_id` of `POST /v1/assignments`. When you hold it, answer `409` with a JSON body with `title` and `status: 409`, and leave the assignment you hold as it is. A finished assignment is still held: the suite repeats `main` after it finished. |

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
| W-13 | your worker reached no host during `main`, so no host could be withdrawn from the frame | give it a task that reaches one (`--task`) and name that host (`--hosts`) |
| W-06 | the assignment finished before the stop arrived; or the step the suite waits for never started | make the default work take more than a moment, or supply a task with several steps |
| W-08 | the suite had no value to look for | set the same random value under the credential's name in your worker's environment and in the environment of the suite before starting both: `export TAKTUS_CONFORMANCE_CREDENTIAL=$(openssl rand -hex 16)` |
| W-10 | your estimate is zero for every quantity, so no limit can lie below it | estimate something; a shell script still takes seconds of `cpu` |
| W-11 | the stopped run produced no artifact before its checkpoint, so a repeat could not be observed | produce an artifact in an early step, or supply a task that does |
| W-14 | `main` used no more of any quantity than you estimated, so no limit your estimate fits can be crossed; or the `tight` run finished its work before a step remained to be withheld | nothing is wrong with an estimate that holds. To see the halt, start your worker so that it underestimates — the reference worker has `--estimate-factor 0.5` — or give it a task that uses more than it expects |
| W-15 | a held assignment finished before the suite had filled your places, or before you answered one more, so you may have had a free place; or you answered an assignment of the probe with something other than `201` before your places were full; or you declare more than sixteen places, the most the suite fills | make your default work last longer than posting that many assignments takes, or give a task that does (`--task`); run the suite against an idle worker; for the conformance run, start your worker so that it declares sixteen places or fewer — the reference worker has `--max-concurrent` |
| W-17 | you turned away the fresh assignment the suite meant to repeat, so no running assignment could be repeated; or `main` did not finish, so no finished one could | run the suite against an idle worker; fix the failure that kept `main` from finishing |

A check that failed can leave later checks inconclusive: without a boundary there is nothing a
stop can land on, without a stopped run there is nothing to resume. Fix the failure first.

---

## 7. What a pass means

A worker whose report shows sixteen `passed` and one `pending` satisfies the numbered checks. A
W-14 that stays *inconclusive* because your worker's estimate always held is no failure; it
means the halt was not observed.

The capacity answer is checked too: W-15 holds as many assignments as you declare and expects
`503` for one more. Until W-15 existed, a worker that took more than it declared passed this
suite (DEC-0085).

So are the two answers about an assignment's id that Taktus relies on since ADR-0038. W-16
expects `404` for an id you do not hold. W-17 expects `409` for an id you hold, and the
assignment of that id unchanged afterwards. Until they existed, a worker that took a repeated id
as a second assignment passed this suite, and two assignments could run for one step
(DEC-0091). What W-17 cannot see is a second assignment your worker runs without showing it: a
worker that answers `409`, keeps the first state, and still starts the work again somewhere
passes. Nothing the suite can read from your endpoints tells that apart.

It is not yet *verified*. Taktus grades adapters in three levels — `experimental`, `verified`,
`reference` — and *verified* needs two things: this suite passed, and the *removal test* passed.
The removal test takes the worker out of a running Taktus and shows that processes still run,
only at different quality or cost. A running Taktus does it as a process of its own. The report
states this: `removal test pending; verified: no`.

**A report you run does not make your worker *verified* in anybody's Taktus.** A Taktus instance
records this suite's half only when it ran the suite itself, against the worker its own
configuration names (`taktusctl conformance record worker.endpoint`, ADR-0044). It records the
outcome with what your worker declared — its capabilities and its version. When either changes,
the pass no longer counts, and the instance needs to run the suite again.

---

## 8. Proving the suite itself

A suite that only ever passes proves nothing. The reference worker can be started with a *fault*
— `python3 workers/script/worker.py --fault W-04` — that makes it break exactly one check; the
suite must then fail on that check and on no other. `make gate-conformance` does this for every
fault. `python3 workers/script/worker.py --list-faults` prints them. If you want to see the suite
catch something before trusting it with your own worker, this is the way.

---

## 9. Running the suite by hand, as an instance does

A person can run the same suite against the same worker without Taktus, and keep the report as
evidence. This is the way to check a worker when no instance runs, and the way to repair one
(ADR-0013 B and C). Nothing about it needs a database or a running Taktus.

1. **Find the endpoint.** It is the worker the instance is configured with: `TAKTUS_WORKER`. For a
   launched kind (`TAKTUS_EXECUTION` is `process`, `container` or `cluster`), start one unit of
   the configured program by hand, with no credential but the one in step 3, and use its
   address.
2. **Read what it declares**, and keep it with the report:

   ```
   curl -s http://localhost:9000/v1/capabilities > capabilities.json
   ```

3. **Run the suite** with what the instance reads from its configuration. The task file is
   `TAKTUS_CONFORMANCE_WORKER_TASK`, the hosts `TAKTUS_CONFORMANCE_WORKER_HOSTS`, the
   credential's name `TAKTUS_CONFORMANCE_WORKER_CREDENTIAL` (default
   `TAKTUS_CONFORMANCE_CREDENTIAL`), its value the file `TAKTUS_CREDENTIAL_<NAME>_FILE`, and the
   worker's log `TAKTUS_CONFORMANCE_WORKER_LOG`:

   ```
   export TAKTUS_CONFORMANCE_CREDENTIAL="$(cat "$TAKTUS_CREDENTIAL_TAKTUS_CONFORMANCE_CREDENTIAL_FILE")"
   uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000 \
       --task task.json --hosts registry.example --worker-log worker.log --json report.json
   ```

4. **Keep the evidence together**: `report.json`, `capabilities.json`, the date, who ran it, and
   the commit of this repository the suite came from (`git rev-parse HEAD`). Put them where your
   organisation keeps evidence. The exit code says what the instance would record: `0` passed,
   `1` failed, `2` incomplete.

The report kept this way is evidence for a person. A Taktus instance does not import it: it would
be asserted, not measured by the instance.
