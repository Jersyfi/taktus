# `a2a` — a foreign agent as a worker

The *agent-to-agent protocol* (A2A) is an open protocol by which one agent hands a task to
another. This worker is the binding of the worker contract v1 to it (ADR-0172, #349): it speaks
the contract to the control plane and A2A to one agent. The agent needs to know nothing of
Taktus. The binding keeps what the protocol does not carry: the estimate, the limits, the
stream with its boundaries, the stop, and the commands before and after the work.

```
python3 workers/a2a/worker.py --port 9030 --agent https://agent.example \
    --capability report.draft --stores eu
```

## What the operator declares

- **`--agent`**: the agent's address. Its agent card is read at `/.well-known/agent-card.json`
  under it. The card must name a JSON-RPC address on the same host; one on another host is not
  used, and nothing is sent.
- **`--capability`**, required: what the agent does, named by function, such as
  `report.draft`. A process names that capability, never the agent or its product (ADR-0003).
  One binding offers one capability. An agent that does several things is configured as several
  bindings.
- **`--stores`**, required: `own`, `eu` or `elsewhere`, where the agent keeps what it is sent.
  The binding declares it as `data_location`. A tenant whose residency rule does not admit it
  is never handed to this worker (principle 11, UC-11.1). Taktus does not verify it.
- **`--estimate-seconds`** and **`--estimate-turns`**: how long the agent is expected to work on a
  task, and in how many status changes. This is the binding's estimate, declared as a fixed
  estimator.
- **`--resource-class`**, by default `agent.remote`: the class the binding reports the seconds in.

## What an assignment does

| Step | What it does | Its consumption |
|---|---|---|
| `before` | the task's command before the work, in the worker's workspace (W-18) | its seconds |
| `send` | reads the card and sends the task as one message: the goal and its acceptance as text, the inputs as data; the artifact `agent-task` names the agent's task | its seconds |
| `turn-N` | sends any message received at the boundary before it into the task, then reads the task until its status changes | its seconds |
| `fetch` | publishes every artifact of the task as `agent-<id>` of kind `agent.output`, and a `summary` of kind `report` | its seconds |
| `after` | the task's command after the work (W-18) | its seconds |

The binding speaks A2A 0.3 over JSON-RPC: `message/send` and `tasks/get`. It does not wait on
the agent's stream; it reads the task every `--poll-seconds`. An agent that answers the message
with a message of its own, without a task, has finished at once: its answer is the artifact
`agent-answer`. A task that ends `failed`, `rejected` or `canceled` fails the assignment with the
agent's reason.

Every step that calls the agent is a `tool.called` under the capability, with the agent's host.
A frame that does not allow either refuses it visibly, and nothing is sent (W-07, W-13).

**Consumption is the time the binding observed.** The protocol reports no consumption. The
binding reports the seconds each step lasted as `compute_seconds` in its resource class, and
holds a compute limit in that class: it rejects an assignment whose estimate exceeds it (W-10),
and halts at the boundary where the next turn would cross it (W-14). An assignment whose limits
carry no compute in that class is rejected. The agent's money and tokens are not seen.

**A stop lands on the next boundary and cancels nothing at the agent.** The agent's task runs
on. A resumed assignment observes the same task and sends nothing a second time. A turn that
does not end is ended at the stop's ceiling, `ceiling_seconds`, or after 30 seconds.

## Steering, and an agent that asks for input

The binding declares `supports.steering`. A message is received at the next boundary and sent
into the agent's task, as a further message with the task's id, at the start of the next turn.
An agent whose task is `input-required` has its question in the stream, as the turn's
`step.progress`: a person answers it by steering the step (UC-4.21). While the agent waits, a
message accepted ends the turn, so that it is received at the boundary and sent. A message that
arrives after the task ended is received and not sent. Handover and the outbound binding are not
offered.

## The credential

The assignment must reference `A2A_AGENT_TOKEN` (or the name `--credential` gives), unless the
binding is started `--anonymous` for an agent that needs none. The value reaches the worker's
environment under that name and goes to the agent in the header `--auth-header` names, after
`--auth-prefix`. It reaches no event, no artifact, no state and no log, and the commands before
and after the work run without it (W-08). The card is read without it.

## Fault injection

`--fault NAME` makes the binding violate exactly one conformance check; `--list-faults` prints
them. `tests/conformance/test_worker_v1_a2a.py` runs the suite against the binding and the
reference agent (`tests/fakes/a2a_agent.py`), honest and with every fault, and asserts that each
fault fails exactly its check.

## Not yet

No image and no live test: both need an agent an organisation chose, with its address and its
credential. The removal test against two configured bindings is
`tests/integration/test_a2a_worker.py`. Another version or transport of the protocol is a change
of this binding.
