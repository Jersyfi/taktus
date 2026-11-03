# ADR-0172 — A foreign agent is a worker through an A2A binding of the worker contract

**Status:** accepted · extends ADR-0007 (the worker contract), ADR-0139 (steering) and
ADR-0157 (a foreign service behind the contract, a declared location) · issue #349, DEC-0190,
UC-14.5

## Context

The *agent-to-agent protocol* (A2A) is an open protocol by which one agent hands a task to
another. An agent publishes an *agent card*: a JSON document that says what it does and where
it is reached. A client sends it a *message*. The agent answers with a *task*: an object with an
id, a *status* that moves through states such as `working`, `input-required` and `completed`,
and *artifacts*, its results. A client reads the task again by its id. The protocol has several
transports; the common one is JSON-RPC 2.0 over HTTP.

Taktus wants such an agent to serve a step (`docs/research/2026-10-12-market-review.md`
§2.2.7, DEC-0190). Four facts shape how.

- **The protocol knows nothing of the worker contract's obligations.** It has no estimate, no
  limits, no step boundary, no checkpoint and no consumption report. An agent built by anyone
  will not carry them.
- **The contract's obligations are what makes a worker safe to use.** Admission needs the
  estimate (ADR-0005). The ledger needs the stream. A stop needs a boundary. The removal test
  needs the worker to stand in a pool beside others of its capability.
- **A step's task may carry a command before and after the work** (W-18). Such a command runs
  in a workspace. The control plane runs no foreign code (DEC-0011).
- **The protocol changes.** It is young, and its method names and transports have changed
  between versions. The market review names that risk and says to keep it in an adapter.

## Decision

### 1. A binding, not a second contract

The A2A binding is a worker: a separate deployable, `workers/a2a/`, that speaks the worker
contract v1 on the side of the control plane and A2A on the side of the agent. The control plane
reaches it as it reaches every worker, at an endpoint. Nothing in the core changes, and nothing
in the core names the protocol. The binding imports nothing from the core.

One binding serves one agent and offers one capability. The operator names the capability,
`--capability`, by what the agent does, never by the agent or its product. An agent that does
several things is configured as several bindings, one per capability. The binding ships no
capability of its own.

### 2. Each contract obligation, and who keeps it

| Obligation | Kept by |
|---|---|
| capabilities | the binding: the operator's capability, `compute` as its consumption kind, the operator's location |
| estimate | the binding: the operator's estimate of a task, as a fixed estimator (ADR-0115) |
| limits before the start | the binding: an estimate above the limits rejects the assignment before anything is sent |
| limits while running | the binding: before each step it adds the step's share of the estimate to what it measured, and halts at the boundary |
| stream, boundaries, checkpoints | the binding: one step per status change the agent reports |
| frame | the binding: every call to the agent is a `tool.called` under the capability with the agent's host, refused where the frame allows neither |
| stop | the binding: it pauses the observation at the next boundary and cancels nothing at the agent |
| commands before and after | the binding, in its own workspace |
| steering | the binding forwards the message into the agent's task at the boundary |
| the work | the agent |

### 3. The protocol, mapped

The binding speaks A2A version 0.3 over JSON-RPC. It reads the agent card at
`/.well-known/agent-card.json` of the agent's address. It sends JSON-RPC to the address the
card names, only where that address is on the same host. A card that names another host, or no
JSON-RPC transport, ends the step failed, and nothing is sent.

An assignment is these steps:

1. **`send`.** The binding sends the task as one message: the goal and its acceptance as a text
   part, the task's inputs as a data part. It asks not to wait (`blocking: false`). The step's
   artifact `a2a.task` names the agent's task, the protocol version and the declared location.
   An agent that answers with a message instead of a task has finished at once; its answer is
   the result.
2. **`turn-N`, one step per status change.** The binding reads the task (`tasks/get`) until its
   status changes: another state, or another status message. The status message is the step's
   `step.progress`. A state of `input-required` is a turn like the others: its question is in
   the stream, where a person sees it and can answer by steering.
3. **`fetch`.** Once the task is `completed`, every artifact of the task becomes an artifact
   of the assignment, of kind `agent.output`, beside a `summary` of kind `report`. A task that
   ends `failed`, `rejected` or `canceled` fails the assignment with the agent's reason.

### 4. Consumption is what the binding measures

The protocol reports no consumption. The binding reports the one quantity it measures: the
seconds each step lasted, as `compute_seconds` in a resource class its operator names
(`--resource-class`, by default `agent.remote`). A limit on compute in that class is held as
section 2 says. The agent's money and tokens are not reported.

### 5. Steering is the protocol's further message

The binding declares `supports.steering`. A message accepted from the control plane is received
at the next boundary (W-19) and sent into the agent's task as a further message with the task's
id, at the start of the step after that boundary. That is also how an agent's request for input
is answered. A message that arrives after the agent's task ended is received and not forwarded.
The binding declares no handover and offers no outbound binding.

### 6. Removal changes the step

A process names the capability. Withdrawn, the step moves to the next worker of the capability,
or to its fallback. The verdict is *changed* (UC-8.9). The rehearsal of the removal test sends
the agent nothing (ADR-0030).

## Alternatives

- **An adapter inside the control plane that speaks A2A.** It would save a deployable. The
  control plane would then run a task's commands before and after the work, which is foreign
  code in the control plane (DEC-0011), and the protocol's churn would reach the core image.
  Rejected.
- **A second contract for agents.** Every obligation of section 2 would have to be designed
  again, and the conformance suite, the removal test and admission would each learn a second
  shape. The issue rules it out. Rejected.
- **Require the agent to carry the contract's obligations in a protocol extension.** An agent
  built by somebody else does not carry them, and the use case is exactly such an agent. An
  extension can come later beside this binding. Rejected for now.
- **The protocol's streaming method instead of reading the task.** Not every agent offers it,
  and a reading catches up after a restart without a stream to resume. Reading works with both.
- **Cancel the agent's task on a stop.** A stop is a pause that a resume continues (W-06); a
  canceled task cannot be continued. Rejected, as for the factory (ADR-0157).
- **Several capabilities per binding, one per skill of the card.** The binding cannot tell
  which skill a message reaches: the protocol addresses an agent, not a skill. Rejected.

## Consequences

- `workers/a2a/`: the binding, its faults, its README.
- `tests/fakes/a2a_agent.py`: the reference agent, a small A2A server that knows nothing of
  Taktus.
- `tests/conformance/test_worker_v1_a2a.py` and `tests/integration/test_a2a_worker.py`.
- `contracts/worker/v1/README.md` §10 states the binding. The schema does not change.
- `CREDENTIALS.md` gains the agent's credential, referenced by name as every worker's is.

## Where this promise ends

- **One version of the protocol, one transport.** The binding speaks A2A 0.3 over JSON-RPC.
  Another version or transport is a change of the binding, and the conformance suite against
  the reference agent shows whether it holds.
- **The agent's inside is the agent's.** The frame holds the calls to the agent and its host.
  What the agent calls and reaches is not held.
- **Consumption is the time the binding observed.** The agent's money and tokens are not seen.
  A limit in money or tokens is not held by this binding; an assignment that carries only such a
  limit is rejected, since the binding consumes compute.
- **A limit holds at the boundaries.** The binding cannot halt the agent inside a turn. It halts
  at the next boundary.
- **A stop pauses the observation, not the agent.** The task runs on while the assignment is
  stopped. A resumed assignment finds it where the agent got to. A turn that does not end is
  ended at the stop's ceiling.
- **A turn is a status change the binding saw.** A change between two readings that is
  superseded by the next is not seen. The steps are what the binding observed.
- **A message forwarded is the agent's to take.** The binding sends it into the task. Whether
  the agent acts on it is the agent's; an agent that refuses it is named in the stream.
- **A location is what its operator declares.** The binding does not verify where the agent
  stores (UC-11.1 §3).
- **No real agent is proven.** The reference agent is a stand-in. A real agent needs its
  operator's address and credential, and is proven by running the suite against it.
- **No image yet.** The binding runs as a process from the repository, as the factory worker
  does.
