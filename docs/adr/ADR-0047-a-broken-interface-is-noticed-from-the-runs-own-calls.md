# ADR-0047 — A broken interface is noticed from the run's own calls

**Status:** accepted · builds issue #100 on ADR-0006, ADR-0023, ADR-0024 and ADR-0045

## Context
The owner answered on 2026-10-08 that Taktus must notice on its own when an interface it depends
on stops behaving as its adapter expects (DEC-0058). It notices from its real calls, the repository
service first. It reports through the channel its instance has: for this tenant, the chat channel.
The monthly live test is the second net, not the first.

An *interface* here is a connector the instance configured, named by its adapter identifier
(`connector.<label>`), and the service behind it. Issue #100 states how it is verified. Calls that
fail in a way the connector's contract does not foresee — an unexpected shape, an authentication
refused, a status that should not occur — open one finding per interface and cause, not one per
call. The finding reaches the configured channel with the run, the step and the first and the last
occurrence. A transient failure that a retry resolves raises nothing. The decision to report is a
rule. Without a configured channel the finding is still recorded, shown by `taktusctl`, and says
that it was not delivered.

Four things stood in the way. The core could not tell a connector that answered outside its
contract from a connector that did not answer: both were `ConnectorError`. The reference
repository connector reported a status outside its mapping as `invalid` and a body it could not
read as `unavailable` or as an unclassified crash, so a changed interface looked like a wrong input
or a moment's outage. The engine retries nothing on its own (ADR-0024 §3): a retry is a resume,
which a person makes. And the owner-facing channel had an entry for a failure Taktus noticed
(`OwnerChannelWiring.failure`, ADR-0045 §6) that nothing called.

A broken interface is not a product finding (ADR-0046). A finding is something the product lacks;
a broken interface is an interface that worked and stopped. It goes to the owner of the instance,
not to the Taktus repository.

## Decision

### 1. The contract names the unforeseen answer
The connector contract's causes gain `unexpected`: the target answered with a status or a body the
connector does not foresee, so the interface it serves may have changed. Its effect is `none` and
it is not retryable. A body the connector cannot read in answer to a write keeps the cause
`unknown`, whose effect is `unknown`, because the target may have acted (`contracts/connector/v1`
§6). No version of Taktus that uses the contract is released, so `v1` may still move
(ADR-0019).

The reference repository connector maps every status outside its table — a redirect, `405`, `410`,
`418` — to `unexpected`; `400` stays `invalid`. A success it cannot read is `unexpected` for a read
and `unknown` for a write. A shape an operation does not foresee — a field missing, a list where a
record was expected — is the same.

The core's port gains `ContractBroken`, a `ConnectorError` raised when the connector answered and
its answer is outside the contract: an error without a classified body, a result that does not
validate, no structured content.

### 2. The run records every failed call that speaks about its interface
A rule reads the cause of a failed call (`run/domain/service/interfaces.py`):

| Kind | Token | When |
|---|---|---|
| unforeseen | `contract` | the connector answered outside its contract, or reported an effect other than the declared one |
| unforeseen | `unauthenticated` | the service refused Taktus's authentication |
| unforeseen | `unexpected` | the service answered a status or a shape the connector does not foresee |
| transient | `unavailable` | the service did not answer, or answered that it cannot now |
| transient | `unknown` | the answer did not arrive, or a write's answer could not be read |
| transient | `unreachable` | the connector itself did not answer |

`forbidden`, `not_found`, `invalid` and `conflict` are the service answering about the input or
the state, as the contract foresees. They say nothing about the interface, and nothing is recorded.

A failure the rule names is written to the ledger as `interface.failed`, in the same transaction as
the step's `step.finished`. The entry carries the run, the step, the adapter and the token as its
outcome, and no consumption: the step's own entry counts what the call used.

### 3. The rule that makes a broken interface
The reporting component reads the entries through its port `Failures`, which the composition root
binds to the run's query `InterfaceFailures`. A rehearsal's entries are left out.

A call counts when its token is unforeseen. A call whose token is transient counts only when the
same step of the same run failed transiently through the same interface on another attempt too:
a retry did not resolve it. A transient failure that a retry resolved never counts. Every counted
call through one interface with one token belongs to one **broken interface**. Its identifier is
derived from the interface, the token and its first call.

Nothing else decides: no model, no estimate, no reading of a reason in words. ADR-0023 asks this
of an automatic stop; a report that pages a person is held to the same.

### 4. Reported once, through the owner-facing channel
While the scheduler leads, it looks once a minute (`composition/interfaces.py`). Every open broken
interface without a report raises one through `RaiseReportHandler`, the same handler
`OwnerChannelWiring.failure` calls. It is a report of kind `failure`, with the broken interface's
identifier. Its four items are what is needed — a look at the interface and what it did — the steps
naming the first and the last failed call with their run, step and time and the count, the runs
that stood still, and today as the date. Raising is idempotent by the identifier, so a broken
interface is said once however many calls fail after it. A message that was not delivered is
tried again once an hour.

A broken interface is closed when the owner answered its report that it is done. A call that fails
after that moment opens a new one, with a report of its own.

### 5. Recorded without a channel, and shown
The failed calls are in the ledger whether or not anyone hears of them. A tenant without an
owner-facing channel raises no report. `taktusctl interfaces` shows every broken interface with its
interface, cause, count, first and last call, the runs it held up, and what became of its report:
delivered, not delivered with the reason — no channel, a refused or failed delivery — or closed.

## Alternatives
- **No new cause; read the connector's `detail`.** Rejected: a decision that reads words is not
  a rule over a recorded cause, and the detail is free text.
- **Every `invalid` counts.** Rejected: a wrong input of a process would page the owner as a broken
  interface.
- **`forbidden` counts.** Rejected: the contract keeps the source system's permissions in force,
  and a process that asks for what its identity may not do is the expected outcome, not a change
  of the interface.
- **Report at the first transient failure, or after a waiting time.** Rejected: the first pages
  the owner for a moment's outage the next attempt would have passed; a waiting time is a race
  between the look and the retry. A failed retry is the evidence the issue names.
- **A table of broken interfaces kept by the reporting component.** Rejected: a second state beside
  the ledger. The entries are the record, and the report is the memory of what was said.
- **Report from inside the run, at the step boundary.** Rejected: a delivery would sit in the
  run's path and could slow or fail it. The scheduler's look keeps the run free of the channel.

## Consequences
- `contracts/connector/v1`: the cause `unexpected`; the conformance rule C-06 counts it as not
  retryable. `ports/connector.py`: `Cause.UNEXPECTED`, `ContractBroken`.
- The reference repository connector's mapping, and the fake service's `POST /_fake/answer`.
- The ledger kind `interface.failed`; `run/domain/service/interfaces.py`;
  `run/application/query/interfaces.py`.
- `reporting`: `FailedCall`, `BrokenInterface`, the rule and its words, the port `Failures`, the
  use case `BrokenInterfaces`.
- `composition/interfaces.py`, the scheduler's look, `taktusctl interfaces`.
- No migration: the entries are the record.

## Where this promise ends
A broken interface is noticed only from calls the run makes through a connector step. A connector
the instance calls on its own behalf — the findings channel, the owner-facing channel's own
delivery — is not watched, and an interface nobody calls is not noticed until a run calls it. A
transient failure is noticed only once a person or a process resumed the step and it failed
again; ten runs that each failed once through an outage report nothing. An interface that answers
in a shape its connector reads without complaint, but wrongly, is not noticed: that is a result
defect, found by a check of the result (ADR-0021). The reference repository connector maps its
own answers; another connector reports `unexpected` only if it was written to. A report says the
first and the last call as they stood when it was raised; later calls are counted in
`taktusctl interfaces` and are not said again. A message that cannot be delivered is tried once an
hour for as long as the broken interface stays open. Nothing in this decision repairs anything:
Taktus reports, and the repair is a task.
