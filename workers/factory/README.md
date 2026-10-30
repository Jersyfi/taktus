# `factory` — a whole software factory as a worker

A *software factory* is a service that takes a task, such as "implement this change", and
returns the finished change. It runs its own agents, its own review and its own checks. This
worker hands a step's task to one through the factory's API, observes it, and returns its
change, behind the worker contract v1 (ADR-0157, #411).

It offers one capability, `change.implement`: a change implemented as a whole, by a service
outside this instance. A process names that capability, never a factory (ADR-0003). This
directory names no product either. A factory is reached through a *profile*, and the profile
for a product is a file of its operator's.

```
python3 workers/factory/worker.py --port 9020 --factory https://factory.example --stores eu
```

## Where the factory stores

`--stores` is required: `own`, `eu` or `elsewhere`. It is where the factory keeps what it is
sent — the task, the repository it works on, its transcripts. The worker declares it as
`data_location` in its capabilities. A tenant whose residency rule does not admit that location
is never handed to this worker; with no other worker for the step, the step fails before
anything is sent and names the rule (principle 11, UC-11.1). The operator declares it from what
the factory's operator says. Taktus does not verify it.

## Profiles

A factory's task API is reached in three calls. The profile says how one factory spells them.
`--profile FILE` names a JSON file; without it the worker uses `generic`, which is this:

```json
{
  "name": "generic",
  "submit": {"method": "POST", "path": "/tasks", "id": "id",
             "body": {"title": "$goal", "description": "$brief", "acceptance": "$acceptance",
                      "reference": "$assignment", "inputs": "$inputs"}},
  "state": {"path": "/tasks/{id}", "state": "state", "stages": "stages",
            "stage_summary": "summary", "cost": "cost.amount",
            "summary": "summary", "reason": "reason"},
  "states": {"succeeded": ["succeeded"], "failed": ["failed", "cancelled"]},
  "change": {"path": "/tasks/{id}/change"},
  "auth": {"header": "Authorization", "prefix": "Bearer "}
}
```

- **submit** posts the body, with the task's values in place of `$goal`, `$brief` (the goal
  and its acceptance criteria as text), `$acceptance`, `$assignment` and `$inputs`. `id` is
  the field of the answer that names the factory's task.
- **state** reads the task. Each name is a dotted path into the answer: its state word, its
  list of completed stages, a stage's summary, its running cost, its summary and the reason it
  failed. `states` says which words mean succeeded and which failed; every other word means it
  still runs.
- **change** fetches the change once the task succeeded. The answer is a changeset —
  `base`, `files` with `path`, `content` and `encoding`, `deleted` — or holds one at the
  dotted path `document` names.
- **auth** names the header the credential goes in, and what precedes it.

A factory whose API does not fit these three calls is not reached by a profile. It needs a
worker of its own.

## What an assignment does

| Step | What it does | Its consumption |
|---|---|---|
| `before` | the task's command before the work, in the worker's workspace (W-18) | nothing |
| `submit` | posts the task; the artifact `submission` names the factory's task | nothing |
| `stage-N` | reads the factory's state until it reports its next stage or the task's end | the difference in the factory's running cost |
| `fetch` | fetches the change, writes it into the workspace, publishes `summary` and `changeset` | nothing |
| `after` | the task's command after the work, on the change (W-18) | nothing |

Every step that calls the factory is a `tool.called` under `change.implement`, with the
factory's host. A frame that does not allow either refuses it visibly, and nothing is sent
(W-07, W-13). The `changeset` has the shape the coding workers give it, so that a process reads
either the same way.

Every step ends with a boundary and a checkpoint that names the factory's task. **A stop lands
on the next boundary and cancels nothing at the factory.** The factory's task runs on, and may
cost. A resumed assignment observes the same task and submits nothing a second time.

**The limits hold at the boundaries.** The worker estimates `--estimate-amount` in
`--currency` for a task of `--estimate-stages` stages, and declares that as a fixed estimator.
It does not start when the estimate exceeds the limit (W-10). Before each stage it adds that
stage's share of the estimate to the running total, and halts when the limit would be crossed
(W-14). What the factory spends inside a stage is the factory's.

## The credential

The assignment must reference `FACTORY_TOKEN` (or the name `--credential` gives); one that does
not is rejected before it starts. The value reaches the worker's environment under that name
and goes to the factory in the profile's header. It reaches no event, no artifact, no state and
no log, and the command before or after the work runs without it (W-08).

## What it cannot do

- **Hold the factory's own work to the frame.** What the factory's agents call and reach is the
  factory's. The frame holds the calls to the factory.
- **Stop the factory.** See above.
- **Steer or hand over.** It refuses a message and a handover with `400`; it does not offer the
  outbound binding.

## Fault injection

`--fault NAME` makes the worker violate exactly one conformance check; `--list-faults` prints
them. `tests/conformance/test_worker_v1_factory.py` runs the suite against the worker and a
stand-in factory (`tests/fakes/factory_service.py`), honest and with every fault, and asserts
that each fault fails exactly its check.

## Not yet

No image and no live test: both need a factory an organisation chose, with its profile and its
credential. The removal test against two configured factories is
`tests/integration/test_factory_worker.py`.
