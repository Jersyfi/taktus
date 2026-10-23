# ADR-0130 — A step sees only the data of its case, and an analysis step never speaks outward

**Status:** accepted · extends ADR-0007 (the frame's allowed tools and hosts), ADR-0024 (connector effects), ADR-0021 (provenance) and ADR-0008 (anchors) · issue #432, UC-7.7

## Context

A step that answers a customer needs that customer's account and nothing else. A step that
analyses retention needs many records and must never write to anyone. Until now both ran in
the same frame. A connector step could call any operation of its connector, with any input a
template or an earlier step produced. A confused or manipulated model could therefore name a
second customer, and the connector would answer. An analysis step could call an operation
that sends mail. Nothing in the run knew which data was personal.

UC-7.7 asks for both to be enforced in the frame, not asked of the model. Five conditions:
a case scope taken from the intake, carried on every connector call and honoured by the
connector; an analytic step with no outward capability, refused at registration when given
one; an analytic source the tenant declares free of personal fields; personal data outside a
specific case kept with a person at every level; and the scope named in the provenance record.

Three words are used below. A **subject** is the person or organisation a case is about, named
by an identifier the source system understands — a customer number, for example. A **case
scope** is the statement that a step serves the case of one subject. A **frame** is what a step
may reach while it runs: capabilities, operations, hosts.

## Decision

### 1. A step declares its frame in its work

Two keys of a step's work set its frame. They sit beside `when` and `ask`, and like them they
are read by the run, never by the operation (`components/run/domain/model/work.py`):

- `scope: {subject: {$input: <name>}}` — the step serves the case of this subject.
- `analytic: {source: <capability>}` — the step analyses, reading one source. `analytic: true`
  is an analytic step that reads no source of its own and works on what analytic steps before
  it produced.

A step is scoped or analytic, never both.

### 2. The subject comes from the intake, never from a step

The subject is exactly one `$input` reference, with a `$select` at most. A run's inputs are what
its trigger or the person who started it gave: the intake of the case. A `$from`, a `$run`, an
`$otherwise` or a literal value is refused, at registration and again before a run starts. A
step's output, a model's among them, therefore never chooses whose data is seen. The input the
subject names is declared by the version and required.

### 3. Every connector call carries the scope, and a scoped capability honours it

The connector contract gains three things (`contracts/connector/v1`):

- `CallContext.scope`: `{subject}`. Every call of a scoped step carries it, a wait's polls
  included.
- `Capabilities.scoped`: the capabilities whose operations serve a subject's data and honour a
  scope. A call that carries a scope is answered with that subject's data only.
- The cause `out_of_scope`: a scoped call that asked for another subject's data is refused with
  it, and nothing is answered.

The run treats `out_of_scope` as final. The step fails, it is not retried, the run escalates to
a person, and the ledger records `frame.refused` with outcome `out_of_scope` beside the step's
entry.

### 4. Which capabilities serve personal data

Two declarations say it. The connector declares a capability `scoped`. The tenant declares a
capability `personal` (`taktusctl sources declare --personal`). Either is enough. The tenant's
declaration exists for a connector that serves personal data and does not know it, a vendor's
server behind ADR-0117 among them.

A scoped step that calls a capability the tenant declares personal, whose connector does not
declare it scoped, is refused before the call (`frame.refused`, `scope_not_honoured`). The
connector would answer every subject.

A scoped step that calls a capability that serves no personal data — a mail channel to answer
the customer, for example — calls it as any step does. The call carries the scope all the same.

### 5. An analytic step's frame holds its source and nothing else

Before a run starts, and at registration, an analytic step is refused when it:

- calls an operation, or waits on one, of a capability that is not its source — a mail
  capability among them;
- names an allowed host or a workspace, holds a worker credential, or has rows or a model
  behind a URI: each reaches a host;
- reads through `$from` what a step that is not analytic produced.

At every call the run refuses, before calling, an analytic step whose operation's effect leaves
the system (ADR-0024), whose source serves personal data, or whose source the tenant does not
declare free of personal fields. Each refusal fails the step and is recorded as `frame.refused`
with outcome `outward`, `personal_source` or `not_declared_free`. Registration asks the
tenant's declaration too, so that a version with an undeclared source is not stored. The run
asks again because a declaration can be withdrawn after a version was stored.

### 6. Personal data outside a specific case is anchored by the frame

A step that is neither scoped nor analytic and calls a capability that serves personal data
reads personal data outside a specific case. Such a read is the first half of every export. It
is anchored by an anchor of the frame's own, `anc-personal-data`, of class `legal`, decided by
the role `owner`. The run raises it at the step boundary, before anything of the step starts,
at every autonomy level and whatever the tenant configured. No tenant configuration names it,
and none removes it. The decision request and the wait are the ones every anchor has
(ADR-0042). A run where no decision request can be raised fails the step without its act.

### 7. The provenance record names the scope

The provenance record of every step that served a case carries `scope: {subject}`
(`contracts/shared/v1/Provenance.json`, migration `0065`). Every result therefore shows whose
data it was built from. The record carries the identifier, never a field of the subject's data.

### 8. The tenant's declaration

`SourceDeclaration` (governance) keeps two lists per tenant: `free` and `personal`. A capability
is on one list at most. A change is recorded as `sources.configured`, naming who made it. A
tenant that declared nothing has both lists empty (NTC-0224). No analytic step may then read a
source, and only a connector's own declaration says that a capability serves personal data.

## Alternatives

- **Scope enforced by the core alone, by filtering what a connector answered.** The core
  cannot know which part of an answer belongs to whom. Only the system that holds the data can
  tell, so the connector does it.
- **Every call of a scoped step to a capability not declared scoped refused.** A support reply
  then could not answer the customer by mail. The UC asks that the call carries the scope, not
  that every capability be scoped. Refused only where the capability serves personal data.
- **The frame declared in the shared kernel's `Step`.** It would change `Step.json` and every
  bundle's schema for two keys the run alone reads. Work keys beside `when` and `ask` keep the
  contract as it is.
- **A subject taken from a template.** A template is filled from earlier steps' results. It
  would let a step's output name the subject, which is what the scope exists to prevent.
- **The export anchor only on outward operations of a personal capability.** An export usually
  reads with one operation and sends with another, of another capability. The read is the act
  to hold.
- **The export anchor as a row in the tenant's anchor configuration.** A tenant could remove
  it. UC-03 §6 says Taktus never runs with less.
- **A digest of the subject in the provenance record.** A subject identifier has few possible
  values, so a digest is reversed by trying them. It would protect nothing and hide the answer
  the record exists to give.

## Consequences

- `ports/connector.py` and `Connector.json` carry `CaseScope`, `Capabilities.scoped` and
  `out_of_scope`. `v1` is not yet released (ADR-0019). A connector that conformed before
  conforms now.
- The run has a port `Sources`, and registration a port `FreeSources`. Both are answered by
  governance's `TenantSources` (`composition/decisions.py`). `taktusctl sources` shows and
  changes the declaration.
- Migration `0065` adds `source_declaration` and `provenance.scope`.
- `tests/components/run/test_case_scope.py`, `tests/components/process/test_frame.py` and
  `tests/components/governance/test_sources.py` prove the five conditions of UC-7.7 §2.

## Where this promise ends

- **The connector keeps the scope; the core cannot check it.** A connector that declares a
  capability `scoped` and answers another subject's data all the same breaks the promise. The
  conformance suite does not yet check it: a check that sends a scoped call for another subject
  and expects `out_of_scope` is still to be written, and no connector in this repository yet
  serves a scoped capability.
- **Personal data is known only where it is declared.** A capability that serves personal data
  and that neither its connector nor the tenant declares is treated as data that is not
  personal. No step is then anchored on it, and an analytic step may read it once the tenant
  declares it free.
- **Free of personal fields is the tenant's word.** Taktus neither produces the copy nor checks
  it (UC-7.7 §3).
- **A wrong subject in the intake gives a wrong scope.** That is a result defect (UC-4.10), not
  a breach of the frame.
- **Only connector calls carry the scope.** A worker reaches its hosts itself. A scoped worker
  step is therefore given no host and no workspace, and reads the case's data from a connector
  step before it. A model a step is routed to receives what the step's prompt carries. Where a
  model may process that data is the tenant's residency rule (ADR-0116), not this frame.
- **An analytic step's `$input` is not checked.** A run's inputs are parameters a person or a
  trigger gave. An input that carries personal data into an analytic step is the process
  author's error.
- **A rehearsal asks no anchor** (NTC-0079). A rehearsal from the tenant's recordings reads
  through real read operations and sends nothing outward, so the frame's anchor is not raised
  in it.
- **The subject's identifier stays in the provenance record.** The record is never changed
  (ADR-0021). A subject whose data was erased in the source system remains named there by its
  identifier, which then points to nothing.
- **The anchor is decided by the role `owner`.** A tenant cannot yet name another role, such
  as a data protection officer, for it.
