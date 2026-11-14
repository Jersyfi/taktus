# ADR-0332 — Nothing leaves the system in a person's name

**Status:** accepted · bounds ADR-0264 · follows ADR-0033 · UC-1.7 §3 · DEC-0239

## Context

ADR-0264 lets a connector step act on behalf of the person a run acts for. The engine then
replaces every credential the step names by that person's own credential. The ADR was written
for reading: a person learns through Taktus only what the source shows that person.

Its decision does not say *reading*. A step marked `on_behalf` may call any operation, an
outward one among them. An operation is *outward* when its effect leaves the system: a `write`
or a `delivery` (contracts/connector/v1). So a step could send a mail, post a reply or write a
record under a person's identity. The recipient would see the person, not Taktus.

That contradicts two things the project already holds:

- **Taktus acts as an identity of its own.** ADR-0033 replaced a person's token by an app of
  Taktus's own, because every pull request Taktus opened appeared as the owner's. UC-1.7 §3 states
  it as a boundary: what Taktus does on its own behalf, it does as an identity of its own.
- **A recipient has a right to know.** UC-7.6 §1 labels a message a model wrote, so that the
  recipient knows. A message sent under a person's identity hides who acted, label or not.

A tenant may also forbid it outright: a business named "never write to people in a person's
name" among what always stays with a person. The product needs no such configuration if it
never does it.

## Decision

### 1. A step on behalf of a person only reads

A connector step with `on_behalf: true` may call only an operation whose effect is `read`. An
outward operation on behalf of a person is refused at the step boundary, before the connector
is called and before anything is booked. The step fails, is not retried, and its reason names
the operation and this ADR. The outcome is `refused on behalf`. The step's fallback applies as
for any failed step.

The rule holds whether or not the person has a credential of their own. It holds at every
autonomy level, in a rehearsal as in a run.

### 2. Registration refuses what it can see

Whether an operation is outward is its connector's declaration, which only the run reads at the
call (ADR-0130). Registration sees the step's work. A step that carries `on_behalf: true` beside
a message frame (`message`) or recipients (`recipients`) declares a send. Such a version does
not register, and the finding names the step and this ADR.

### 3. Where it is checked

- `components/run/application/service/execute_run.py`: the refusal before the call.
- `components/process/domain/service/frame.py`: the finding at registration.
- Tests: `tests/components/run/test_on_behalf.py`,
  `tests/components/process/test_frame.py`.

## Alternatives

- **A tenant setting that forbids it.** Rejected. A product default that lets a message go out
  under a person's identity contradicts ADR-0033 for every tenant; a setting would make the safe
  behaviour opt-in.
- **An anchor that halts the step for a person's approval.** Rejected. Approval does not change
  who the recipient sees. A person who wants to write in their own name writes themselves.
- **Refuse only `delivery`, allow `write`.** Rejected. A record written in a person's name — a
  comment, a ticket, a note in a customer system — is seen by others as the person's act, too.

## Consequences

- No shipped bundle is affected: every step marked `on_behalf` in `blueprints/` reads.
- The never-list item "never write to people in a person's name" is enforced by the product,
  not by a tenant's anchor.

## Where this promise ends

- **Registration sees declared sends only.** A step that calls an outward operation on behalf of
  a person without a message frame or recipients registers; the run refuses it at the call.
- **A worker reaches no source on behalf of a person** (ADR-0264). What a worker does with
  credentials an operator handed it directly is the operator's configuration; this rule covers
  connector steps.
- **The connector's declaration decides.** An operation a connector declares `read` that acts
  outward is the connector's fault; the conformance suite checks declarations, not intentions.
- **Taktus's own identity.** What Taktus's own identity is called at a service — an app, a
  service account, a mailbox of its own — is the operator's choice; this ADR only keeps a
  person's identity out of it.
