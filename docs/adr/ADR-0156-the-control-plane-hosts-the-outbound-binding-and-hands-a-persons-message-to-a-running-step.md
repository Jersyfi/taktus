# ADR-0156 — The control plane hosts the outbound binding, and hands a person's message to a running step

**Status:** accepted · extends ADR-0139 (the worker contract's outbound binding and steering), ADR-0128 (a person takes over a running step), ADR-0038 (an assignment is handed over once) and ADR-0021 (provenance) · issues #625 and #624, which complete #403; DEC-0195 W2

## Context

ADR-0139 gave the worker contract two extensions and left their control-plane side open. A
worker in a customer's network opens no port: it connects to a *host* and fetches the
contract's requests from it, over the *outbound binding* (`POST <base>/next`,
`POST <base>/answers/{request_id}`). A worker that declares `supports.steering` accepts a
*steering message*, an identifier and a text, and receives it at its next boundary. The
contract says what crosses. It does not say who hosts the binding, how a connecting worker is
authenticated, who may send a message, or what the run records of one.

Three properties of the control plane bear on both:

- **Several instances.** Any instance may run any run (ADR-0013 A). The runner that holds a run
  and the instance a worker connects to are, in general, not the same process. The instance a
  person uses is not the runner's either.
- **The claim.** A run is executed under a claim on its job. Every write under it is fenced,
  and a person who takes over a step holds the claim (ADR-0128).
- **The record.** Every input of a result is named in its provenance, and the ledger names who
  acted, for the audit only (ADR-0021, principle 14).

The only medium every instance shares is the database. Two instances never talk to each other
directly; nothing in the configuration names another instance's address.

## Decision

### 1. A worker of kind `connected` is reached through the database

A configured worker gains a fourth way to be reached beside `endpoint` and the launching kinds:
`connected` (`TAKTUS_EXECUTION=connected`, or `TAKTUS_WORKER_<NAME>_EXECUTION`). It has no
endpoint. Its base is `<prefix>/workers/<name>/relay` on the `api` role of every instance; the
unnamed worker's name is `connected`.

Every relayed request lives in the database, in two tables of migration 0087:

- `worker_relay` holds one row per request: the worker's adapter identifier, the request in
  the shape `RelayRequest`, when a host took it, the answer's status and type, whether its body
  ended, and how many answers were posted for it.
- `worker_relay_chunk` holds the answer's body in the order it arrived.

The tables belong to the instance, not to a tenant: a worker serves the instance's tenants
alike, as its configuration does. Row security admits a transaction to them only when it names
`taktus.relay`, which no tenant's transaction does. A row is removed once its answer was read
to the end or abandoned, and at the latest an hour after it was written.

### 2. A runner uses the connected worker through the worker port

On the runner's side the worker is the same HTTP client as one at an endpoint, given a
transport that writes each request as a row and reads its answer from the rows as they arrive.
So every runner on every instance reaches the worker, the stream is read with its reconnect
from `Last-Event-ID`, and nothing in the core knows the difference. The core is not changed.

### 3. A host authenticates the worker before it relays anything

`POST <base>/next` and `POST <base>/answers/{request_id}` need `Authorization: Bearer <key>`.
The key is the worker's *connect key*, configuration key `connect.key`, read from the file
`TAKTUS_CONNECT_KEY_FILE` names, or `TAKTUS_WORKER_<NAME>_CONNECT_KEY_FILE` for a named
worker. It is the worker's alone and has no fallback to the instance's. The comparison takes
constant time.

- No key, or a wrong one: `401`. Nothing is taken and nothing is written.
- A worker that is not configured as connected, or has no key configured: `404`. A connected
  worker without a key cannot connect at all.
- `/next` takes the oldest request of that worker not yet taken, under `FOR UPDATE SKIP
  LOCKED`, so that two polls never take the same one. Without one it waits up to 20 seconds and
  answers `204`.
- `/answers/{id}` answers `404` for a request of another worker or of none, `409` for one
  answered already, and `204` once the body ended. The body is written as it arrives.

### 4. A restart on either side resumes at the boundary

Neither side keeps a request outside the database. A host instance that stops leaves the
answer it was receiving unfinished. The runner's read of it falls silent, and the client does
what it does at an endpoint: it asks the state and reads on from the last event, with a new
request. Whichever instance the worker reconnects to relays that one. A runner instance that
stops loses its claim, and the next runner adopts the open assignment over the binding, as at
an endpoint (ADR-0038).

### 5. The instance's suite runs over the binding, and its pass names the binding

The instance's own conformance run of a connected worker (ADR-0044) uses the same transport.
Its W-21 is judged from what the database recorded: every request relayed, and every answer
posted for it. The configuration a pass names, which the run's maturity threshold compares,
carries `binding: outbound` for a connected worker. A verdict earned at an endpoint therefore
never stands for the binding, nor the other way round.

### 6. The removal test removes a connected worker as any other

The pool withholds a connected worker as it withholds one at an endpoint. Its process may keep
polling; no request arrives for it.

### 7. A person's message to a running step is asked on the run's job

A person sends a message to one step of one run. The engine refuses it, writing nothing,
unless the step is a running `worker` step of a run a runner holds, and its worker declares
`supports.steering`. Each refusal names its reason.

Who may send one is who may take the step over (ADR-0128 §1): on the HTTP surface and in the
web app, an identity that may see the run, until rights per role exist (UC-7.3); on the MCP
surface, a person whose roles hold the right `agent.steer` (ADR-0131 §3); in the chat, the
owner or someone the owner named, and only on the same person's `yes` to the message read back
(ADR-0008).

An accepted message is three facts in one transaction. The text is stored as an object. The
ledger records `step.message_asked`, naming the person as actor and the text by its digest,
never the text. The message, `msg_…`, is placed on the run's job with the text's digest.

### 8. The runner holding the run hands it over under its claim

The runner reads the messages placed on its job with each renewal of its lease, as it reads a
take-over. It hands each one to the worker once (`steer`) and records `step.message_handed`,
fenced by its claim, with outcome `handed`, `refused` where the worker refused it, or
`not_running` where the step had ended. The message is marked handed in the same transaction
and never handed again, by this runner or the next.

### 9. A message received is an input of the step

The worker's `message.received` is recorded as `step.message_received` with the text's digest.
The step run keeps the message's identifier, digest and time. Its provenance record lists the
message among its inputs, as a new kind of input of the shared kernel, `message`: the message's
identifier and the text's digest, with the time it was received. The ledger entry of the ask
names who sent it.

### 10. A message never widens the frame

What reaches the worker is the contract's `SteeringMessage`, a closed shape of an identifier
and a text. The frame, the limits, the exactness class and the anchors of the step are not read
from it, and the next step boundary is asked what it is asked without one. A call the message
prompts outside the frame is refused by the worker as any other is (W-07).

No measure is computed from messages per person. The person is named as actor for the audit
only (principle 14).

## Alternatives

- **A host in each instance's memory, as the conformance suite's.** Rejected: a runner on one
  instance could not reach a worker connected to another, and a restart would drop every
  request in flight.
- **Instances forwarding requests to each other.** Rejected: an instance would need the others'
  addresses, and a channel between them that nothing else needs.
- **`LISTEN` and `NOTIFY` instead of polling.** Not now: a notification still needs the rows,
  and a poll every 50 milliseconds is enough for a step boundary. It can be added inside the
  adapter.
- **A tenant column on the relay.** Rejected: the worker port carries no tenant, and a worker
  serves every tenant of its instance.
- **The connect key as a credential reference of the assignment.** Rejected: that name is for
  what a unit's task needs, and the worker authenticates before any assignment.
- **A message stored on the step run when it is asked.** Rejected: the runner's follow of the
  step writes the step run, and a second writer from the heartbeat would race it. The job
  carries the message, as it carries a take-over.
- **A message as a `source` input.** Rejected: a source is read through a capability by a
  connector; a message is a person's input with an identifier of its own.

## Consequences

- `ports/relay.py` and its memory and PostgreSQL adapters; migration 0087 adds `worker_relay`,
  `worker_relay_chunk`, `job_message` and `step_run.messages`.
- `adapters/driven/workers/connected.py` is the runner's transport and
  `adapters/driving/rest/relay.py` the host; `ExecutionKind.CONNECTED` and `connect.key` in the
  settings; a row in `CREDENTIALS.md`.
- The reference worker's `--connect` sends the key from `TAKTUS_CONNECT_KEY_FILE`.
- The queue gains `ask_message`, `messages_asked` and `message_handed`; the engine `steer`; the
  HTTP surface `POST /runs/{run_id}/steps/{step_id}/messages`; the MCP surface `steer_step`
  under the right `agent.steer`; the chat `message <run> <step>: <text>`; the web app a field
  on a running worker step.
- The shared kernel's `ProvenanceInput` gains the kind `message`.

## Where this promise ends

The binding is plain HTTP from the control plane's side. TLS, the firewall and the proxy
between a customer's site and the control plane are the operator's. A connect key rotates by a
new value in its file and a restart of the instances; there is no second key during a
rotation. One key admits one worker's connections, however many processes present it.

A relayed request reaches the worker no sooner than the host's next poll of the database, about
50 milliseconds later, and each chunk of an answer the same. The relay keeps a request's body,
an assignment with its task and inputs, in the database while it is in flight and at most an
hour. The contract carries credentials by name only, so no secret value is among it.

A message is received at the worker's next boundary, which the worker decides; Taktus cannot
make it come sooner. Taktus records that the worker received it. It cannot see that the work
took it into account. A message asked while no runner holds the run is refused, not kept for
later. A message the runner handed that the worker never received before the step ended is in
no provenance record, because no step read it. Neither coding worker declares steering yet, so
a message to a coding step is refused until one does.
