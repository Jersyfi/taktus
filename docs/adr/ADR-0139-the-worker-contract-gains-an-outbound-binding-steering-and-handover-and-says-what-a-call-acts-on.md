# ADR-0139 — The worker contract gains an outbound binding, steering and handover, and says what a call acts on

**Status:** accepted · extends ADR-0007 (the worker contract), ADR-0005 (a stop lands on a boundary) and ADR-0128 (a person takes over a running step) · issue #403, DEC-0195 W2; closes the contract's part of the gap ADR-0132 leaves to #433

## Context

The worker contract freezes at `1.0.0`. Before then, DEC-0195 adopted three cases that users of
other agent platforms expect (W2):

- **A worker in a customer's network.** Such a network admits outbound connections and no
  inbound one. A worker there cannot be reached at an endpoint; it has to fetch its work.
- **Steering.** A person sends a message to an assignment while it runs.
- **Handover.** An assignment is paused at a boundary. Its state is handed over as an artifact,
  and the work continues elsewhere: in another instance of the worker, in another worker, or
  with a person.

Two of the contract's existing promises bear on these. A stop takes effect at a step boundary,
so that at most one step of work is lost (ADR-0005). A take-over gives a person the worker's
checkpoint reference, which only the worker can open (ADR-0128, *Where this promise ends*).

A third gap was left open by ADR-0132. Its stop to repetition counts the engine's own outward
calls and model answers. It cannot count a worker's. The contract reports a tool call without
saying whether the call acts outward, and it reports no model call at all.

Two words are used below. A **boundary** is the point a `step.boundary` event marks: the step's
result is kept, and a stop may take effect there. A **host** is the party that serves the
outbound binding: the control plane, or the conformance suite that stands in for it.

## Decision

### 1. Every extension is optional, and the contract stays `worker/v1`

Each addition is a property a worker may declare, an endpoint it offers when it declares it, or
an event it may emit. A worker that conformed before conforms unchanged. Nothing is removed and
no meaning changes, so a version `v2` would add a second contract to keep and nothing else.

The compatibility runs one way. A worker written before this decision works with a control
plane written after it. A control plane written before it rejects what it does not know, since
every shape of the contract is closed.

### 2. The outbound binding carries the same messages the other way round

A worker started with the address of a host, its *base*, opens no port. It asks the host for
requests and posts its answers:

- `POST <base>/next` answers `200` with a `RelayRequest` — an identifier, a method, a path of
  the contract, the headers `Accept`, `Content-Type` and `Last-Event-ID` where the request
  carries them, and the body as text. It answers `204` when no request arrived within the
  host's wait, which is 30 seconds at most.
- `POST <base>/answers/{request_id}` carries the answer. The header `Relay-Status` holds its
  status code, `Content-Type` its type, and the body is the answer's body. The host answers
  `204`, `404` for a request it never relayed, and `409` for one answered already.

The worker handles each request exactly as at an endpoint. Its answer to the event stream is
the stream itself: the worker posts it in chunks while it lasts, and the host reads it as it
arrives. The worker asks for the next request while it answers others, so that a long stream
does not hold the rest back.

So the binding adds no message of its own. Every endpoint, every body and every check of the
contract holds unchanged across it. The conformance suite runs whole over it
(`--listen`), and check W-21 holds the worker to the binding itself: every relayed request is
answered exactly once, under its identifier, with a status.

### 3. Steering is a message the worker receives at a boundary

A worker that declares `supports.steering` accepts `POST /v1/assignments/{id}/messages` with a
`SteeringMessage`: an identifier the control plane chooses and a text.

- It answers `202` with the assignment's state. A message whose identifier it holds already is
  answered `202` again and received once. A finished assignment answers `409`.
- At the next boundary it emits `message.received`, naming the message, once. The steps after
  that boundary have the message as an input of their work. A message is never received inside
  a step: the step that was running finishes with the inputs it started with.
- A message is an input like the task's inputs. It cannot widen the frame, raise a limit, add
  a step beyond `max_steps` or move the deadline. A call it prompts outside the frame is
  refused as any other is.

A worker that does not declare steering refuses a message with a problem and changes nothing.
Check W-19 holds both.

The boundary is the unit of record (ADR-0005). A step whose inputs changed while it ran would
have a result no record could explain.

### 4. A handover is a stop that leaves a document anyone can continue from

A worker that declares `supports.handover` accepts `POST /v1/assignments/{id}/handover`. It
stops at the next boundary as for a stop. Then it produces one artifact of kind
`handover.state`, a JSON document of the shape `Handover`, and ends `stopped` with that
boundary's checkpoint and `handover` naming the artifact.

The document stands on its own:

- for a person: a summary of what was done and what remains, the steps done, and every
  artifact produced so far, with what the work changed in its workspace among them;
- for a worker of the same kind: `resume`, the worker's own, from which it continues without
  anything the first instance kept.

A new assignment whose `context.handover` carries the document continues the work. It repeats
no step the document lists as done, and it produces no artifact the document lists. A worker
that does not declare handover refuses the request with a problem, and the assignment runs on.
Check W-20 holds all of this.

A worker that cannot hand its workspace over, as a document or an artifact, does not declare
handover. The checkpoint stays the worker's own reference for its own resume, as before.

**The take-over uses it.** A runner that serves a take-over (ADR-0128 §2) asks a worker that
declares handover for a handover instead of a stop. The handover document is then among the
step's artifacts, and the take-over's state lists it. A person receives what the worker knew,
not only its checkpoint reference.

### 5. A call says what it acts on, and a model's answer is reported

`tool.called` may carry `effect`:

- `local`: the call changes nothing outside the assignment's workspace. A read, an edit of the
  workspace's files and a test run are local.
- `outward`: the call changes something outside it, such as a record written or a message
  delivered.

A new event, `model.called`, reports each answer of a language model the worker received
inside a step. Both are optional. With them the stop to repetition of ADR-0132 has what it
needs for a worker's step: its outward calls, and its model answers with the tool calls between
them. Counting them stays with #433.

### 6. Three checks, each proven by a fault

| Check | What it holds | Fault of the reference worker |
|---|---|---|
| W-19 | a message is received once, at a boundary, after it was accepted; without `supports.steering` it is refused | `message.received` is emitted inside the running step |
| W-20 | a handover ends the assignment at a boundary with a `handover.state` artifact that validates and names the checkpoint; a continuation repeats nothing it lists; without `supports.handover` it is refused | the handover stops without the artifact |
| W-21 | over the outbound binding, every relayed request is answered exactly once, under its identifier, with a status | every answer is posted twice |

The suite against an endpoint reports W-21 *pending*: the binding is not in use there.

## Alternatives

- **A contract `v2`.** Rejected: nothing is removed or changed, and two versions would have to
  be kept before the first freeze.
- **A binding of its own messages**, in which the worker posts its events and fetches its
  assignments. Rejected: a second set of messages to keep consistent with the first, and a
  second reading of every check.
- **WebSocket or a bidirectional gRPC stream.** Rejected: a worker in a shell or in a standard
  library would need a library it does not have. Plain HTTP requests leave a customer's network
  through the proxies it already allows. ADR-0007 keeps gRPC as a later binding.
- **A message that takes effect at once.** Rejected: the step's result would rest on inputs no
  record names.
- **A message that may change the frame.** Rejected: the frame is a ceiling set by the control
  plane, and exactness rests on it (ADR-0014).
- **A handover as a stop and the checkpoint.** Rejected: the checkpoint is opaque and local to
  the worker that wrote it, which is the gap ADR-0128 names.

## Consequences

- `contracts/worker/v1`: `Worker.json` gains `SteeringMessage`, `HandoverRequest`, `Handover`,
  `HandoverStep`, `RelayRequest`, the events `message.received` and `model.called`,
  `tool.called.effect`, `assignment.finished.handover`, `context.handover`,
  `supports.steering` and `supports.handover`, and the fixture shape `RelayProbe`.
  `openapi.yaml` gains the two endpoints of the worker and the two of the host.
- The conformance suite gains W-19, W-20 and W-21, the runs `steered`, `handed-over` and
  `continued`, and `--listen`, which serves the binding and runs the whole suite over it.
- `workers/script` implements all three: `--connect` reaches a host and opens no port. The
  coding workers and the ML bench declare neither steering nor handover and conform unchanged.
- The worker port gains `steer` and `hand_over`. The run asks for a handover when it serves a
  take-over of a worker that declares it.
- #624 builds steering on the control plane's side: who may steer, the ledger entry with its
  origin, and the message as an input of the step's provenance. #625 builds the control
  plane's host of the binding and its authentication.

## Where this promise ends

This decision covers the contract, the conformance suite and the reference worker. The control
plane does not yet send a message, and does not yet host the binding: both are #624 and #625.
The binding names no authentication of its own. The host decides it when it is built, and the
conformance host needs none, since it listens only where the suite is told to.

The suite sees that a message was received once, at a boundary. It cannot see that the work
took the message into account. The suite continues a handover at the same endpoint. That the
continuation needs nothing the first instance kept is shown by the reference worker's own test,
which continues on a second instance with a state directory of its own. Neither coding worker
offers steering or handover yet. Until one does, a take-over of a coding step still gives the
person only the checkpoint reference.

`effect` and `model.called` are the worker's own statements. The suite cannot check that a
`local` call changed nothing outside, nor that every model answer was reported. A call without
`effect` says nothing about what it acts on. The compatibility of §1 runs from an older worker
to a newer control plane only.
