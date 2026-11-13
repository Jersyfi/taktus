# ADR-0315 — A partner's mapping is proposed from samples and confirmed, and a message that comes too often is stopped

**Status:** accepted · extends ADR-0273, ADR-0303, ADR-0272, ADR-0294 · UC-15.3 · DEC-0236

## Context

UC-15.3 requires three things that ADR-0273 and ADR-0303 left open.

- The mapping between a partner's format and the organisation's own data is built by Taktus
  from sample data in dialogue with a person, and kept versioned.
- A message that arrives at an unexpected frequency marks the import as deviating, before
  anything of it is mapped, and is escalated.
- Partner data is held to the access rights of the systems it came from.

ADR-0273 held the frequency only by the expected runs. A missing exchange raised an incident.
A message that came too early was not found.

## Decision

### 1. A mapping is proposed by rule and confirmed by a person

`partners.propose_mapping(contract, samples)` is a rule (`process/domain/service/partners.py`).
It reads the dotted paths that every sample message carries. A field of the contract takes the
one path whose last name equals the field's name. The match is letter for letter, or else once
case and separators are set aside. A field that two paths match is left for the person to
choose. A field that no path matches is asked for. It is never guessed. The answer is a
`MappingDraft`: the proposal, how each path was found, what is ambiguous, unmatched and unused,
and the question asked back (ADR-0008).

`POST /contracts/mapping-drafts` answers it on the HTTP surface. The draft is stored nowhere,
and nothing applies it.

A person confirms or corrects the mapping by registering a version whose contract carries
`mapping`: each field by the path that carries it in the partner's message. The mapping is part
of the version, so a changed mapping is a new version. Registration refuses a mapping that names
a field the contract does not have, or leaves out a field the contract requires.

### 2. A message that comes too early stops the run before it is mapped

`ContractControl` (`composition/partner_exchange.py`) answers the run component's boundary
port `ExternalControl` (ADR-0272). It sits in front of `TaskControl`, which keeps answering
first for a decoupled task. The check runs at the first boundary after an import step under a
contract that names a `frequency` has succeeded. It reads from the ledger when the same step of
the same process last succeeded in another run. A rehearsal does not count.

Where the time since then is shorter than the frequency, `partners.too_often` names the
clause `frequency` that the message breaks. The run halts at that boundary, before the step
that maps the message. The ledger records `contract.deviated` with outcome `too_frequent`.
Because the port is the one ADR-0272 introduced, the engine also records `control.withdrawn`.

`ContractWatch` delivers every deviation once. The governance component writes the situation
package from the run, with the clause as `Escalated.breaks`. The package goes to the role the
version names for its escalations, `owner` where it names none, in the owner-facing channel. The
ledger records `contract.escalated`. The scheduler calls the watch once a minute.

### 3. Partner data is read with the access rights of its source

A partner's system is reached through a connector. A shared connector is called only for a run
whose identity is inside the share's circle, and with that identity's own credential for the
source system (ADR-0247, ADR-0294). Nothing new is built for this. A test now proves it for
partner data: an identity outside the circle reads nothing of the partner's system, and one
inside it reads with its own credential.

## Alternatives

- **Taktus applies the proposed mapping directly.** That would guess where a person must
  decide. UC-15.3 builds the mapping in dialogue, and ADR-0008 never acts on an unconfirmed
  interpretation.
- **A model proposes the mapping.** The names in the samples already decide most fields. A
  rule is reproducible, and it asks for what it cannot match.
- **Find a message that came too early after the fact.** The run would already have mapped the
  message, and UC-15.3 checks before anything is mapped.

## Consequences

- `DataContract` has `mapping`; `MappingDraft` is a new value of the process component.
- `contract.deviated` and `contract.escalated` are new ledger kinds; `control.withdrawn` is
  also written for this cause.
- The daemon's engine takes `ContractControl` in front of `TaskControl`, and the scheduler
  takes `contracts_tick`.

## Where this promise ends

- **The proposal matches by name.** A partner who names a field differently is asked for that
  field. Values and formats are not compared.
- **The step that maps reads the message as its own work says.** Registration holds the
  mapping to the contract, not the work of the mapping step to the mapping.
- **Early is measured from the last success of the same step in another run.** Two messages
  read in one run are not compared with each other. A message after a failed import is not
  early.
- **The deviation is said, not answered.** Asking the partner for the message again stays with
  the person.
- **The access rights are the connector's share.** A connector that is not shared is called
  with the credential the operator configured, as before.
