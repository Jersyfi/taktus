# ADR-0157 — A software factory is a worker, and a worker declares where it stores data

**Status:** accepted · extends ADR-0007 (the worker contract), ADR-0078 (several workers in one
pool) and ADR-0116 §2–§3 (a declared location and a tenant's residency rule) · issue #411,
DEC-0195 W10, UC-8.15, UC-11.1

## Context

A *software factory* is a service that takes a task, such as "implement this change", and
returns the finished change. It runs its own agents, its own review and its own checks. Several
are sold. Taktus does not become one (DEC-0195, non-goal "no coding agent and no agent runtime
as a core product"). It may use one, for the step that implements a change.

Three facts shape the decision.

- **A factory is reached through its own API.** Every factory has a task API of its own:
  submit a task, read its state, fetch its result. None of them speaks the worker contract.
- **A factory stores what it is sent.** The repository, the task and the transcript end up
  with the factory's operator. The factory the review of 2026-10-13 read stores in the United
  States (`docs/research/2026-10-13-warp-review.md` §1). Principle 11 makes sovereignty an
  organisation's choice. UC-11.1 requires every worker to have a declared location.
- **Models already declare a location, workers did not.** ADR-0116 routes a step on a model
  only to a member the tenant's residency rule admits. A worker step was resolved to the first
  worker that offers its capabilities, wherever that worker stores.

## Decision

### 1. A worker declares where it stores data

The declaration a worker answers at `GET /v1/capabilities` gains an optional field
`data_location`. Its values are those of ADR-0116 §2: `own` is the organisation's own
infrastructure, `eu` is inside the European Union, `elsewhere` is anywhere else. It says where
the worker keeps, or lets a service keep, what an assignment sends it.

A worker that declares nothing counts as `elsewhere`. That is ADR-0116's default for a model,
for the same reason: a location nobody declared is outside every rule narrower than
*anywhere*.

### 2. A worker step goes only to a worker the residency rule admits

A worker step may declare the data class of what it sends, as `data_class` in its work, as a
step on a model does. The location the step permits is the tenant's rule for that class, or
the tenant's own where the class has none (ADR-0116 §3).

The worker pool resolves a step to the first configured worker that offers every required
capability *and* whose declared location the rule admits. A worker outside the rule is passed
over for the next one, in the order of `TAKTUS_WORKERS`.

When workers offer the capabilities and none of them is admitted, the step fails before
anything is assigned. Its reason names the permitted location and the first worker passed over
with its location. The run escalates at the boundary, as for a step no worker serves. A resume
after the rule or the configuration changed retries it.

### 3. A factory is a worker behind the contract

`workers/factory/` is a worker like the others: a separate deployable that imports nothing
from the core. It offers one capability, `change.implement`: a change implemented as a whole,
by a service outside this instance. It is generic over a factory's task API in three calls:

| Call | What it does |
|---|---|
| submit | posts the task and receives the factory's id for it |
| state | reads the task's state, the stages it completed and its running cost |
| change | fetches the change, once the task succeeded |

A *profile* maps the three calls onto one factory's API: paths, field names, the words for its
states, the header that carries the credential. The worker ships one profile, `generic`, which
describes the shape above. A profile for a product is a file of the operator's. No product
name appears in the core, in the worker or in a shipped profile (ADR-0003).

The operator declares where the factory stores, `--stores`. It is required: the worker assumes
no location.

### 4. The factory's work in steps

An assignment is these steps, each with its consumption and its boundary:

1. **`submit`.** The worker posts the task. This is the tool call the frame holds:
   capability `change.implement`, host the factory's. A frame without either is refused
   visibly, and nothing is sent. The step's artifact `submission` names the factory's id for
   the task.
2. **One step per stage the factory reports.** The step reads the factory's state, under the
   same capability and host, until the factory reports its next stage or the task's end. Its
   consumption is the difference in the factory's running cost.
3. **`fetch`.** The worker fetches the change and publishes it as `changeset` and `summary`,
   in the shape the coding workers publish them. A process reads either the same way.

A command before or after the work (W-18) runs in the worker's workspace, where the fetched
change was written.

A stop lands on the next boundary (W-06), and the checkpoint names the factory's task. A
resumed assignment continues observing the same task. It submits nothing a second time.

### 5. Removal changes the step, it breaks nothing

A process that names `change.implement` and configures a second worker offering it moves the
step to that worker when the factory is withdrawn. A process whose step has a person as its
fallback moves the step to that person. Either verdict is *changed* (UC-8.9, DEC-0111).

The project's own P-03 keeps its own workers. Its bundle does not name `change.implement`.

## Alternatives

- **The factory as a connector.** A connector serves a single call with a recorded answer
  (ADR-0024). A factory's task runs for minutes to hours, in stages, with cost and a result
  artifact. That is the shape of an assignment. Rejected.
- **Declare the coding capabilities, `code.edit` and the rest.** The frame holds each of those
  per tool call (W-07). A factory does not report its tool calls, so the worker could not hold
  them. A capability it cannot hold would be a false declaration. Rejected.
- **The location in the instance's configuration only, as for a model.** The worker is the
  party that knows which service it sends to. The declaration then travels with the worker,
  and the conformance suite reads it. The operator still decides it, through the worker's own
  option.
- **An undeclared worker counts as `own`.** That would keep every existing worker eligible
  under every rule. A worker that sends a repository to a provider in another jurisdiction
  would then pass a rule that forbids it. Rejected: the strict default is ADR-0116's.
- **Cancel the factory's task on a stop.** A stop in Taktus is a pause at a boundary that a
  resume continues (W-06). A cancelled task cannot be continued. Rejected.

## Consequences

- `contracts/worker/v1/Worker.json`: `Capabilities.data_location`; README §2.
- `ports/worker.py`: `Capabilities.data_location`, `ResolvedWorker.location`.
- `components/run/ports/workers.py`: `WorkerPool.resolve` takes the permitted location.
- `adapters/driven/workers/pool.py`: the pool passes over a worker outside it.
- `run/domain/model/work.py`: `WorkerWork.data_class`.
- `RunEngine._worker_step`: the step fails naming the rule when only workers outside it offer
  its capabilities.
- `workers/factory/`: the worker, its generic profile and its faults.
- `tests/fakes/factory_service.py`: the stand-in for a factory, which the conformance suite and
  the removal test run against.
- The existing workers declare no location yet. Under a rule narrower than *anywhere* they
  are not chosen until they declare one.

## Where this promise ends

- **A location is what its operator declares.** Taktus holds a step to the declaration. It
  does not verify where a factory really stores (UC-11.1 §3).
- **Inside the factory the frame does not reach.** The frame holds the calls to the factory
  and its host. What the factory's own agents do with the task, which tools they call and which
  hosts they reach, is the factory's.
- **A limit holds at the boundaries only.** The factory's cost between two reported stages is
  what the factory spends. The worker halts at the next boundary (W-14). It cannot halt the
  factory inside a stage.
- **A stop pauses the observation, not the factory.** The factory's task runs on while the
  assignment is stopped, and it may cost. A resumed assignment finds it where the factory got
  to.
- **The check is at run time only.** A process version that binds a step to a worker outside
  the rule still registers. The registration check of UC-11.1 is not part of this decision.
- **The removal test does not hold the rule.** It names as a step's alternative the next
  worker of the capability, whatever the tenant's residency rule says of it.
- **Connectors are not covered.** A connector's location is not declared by this decision.
- **No steering, no handover, no outbound binding.** The factory worker refuses all three. A
  factory that takes a message while it runs is reached through its own interface.
- **No product profile is shipped.** A profile for a real factory is written by its operator
  and checked by the conformance suite against that factory, with a credential the operator
  holds.
