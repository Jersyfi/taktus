# ADR-0264 — A step on behalf of a person reads with that person's own credential

**Status:** accepted · extends ADR-0024 · UC-5.5 §2, UC-5.6 §2, UC-12.1 §2 · DEC-0228

## Context

Three use cases require that Taktus reads a source with the rights of the person it acts for,
never with wider ones of its own. UC-5.5 §2: two identities whose permissions in a knowledge
source differ ask the same question, and each gets only what the source shows them. UC-5.6 §2:
the data warehouse is queried with the identity of the person or process on whose behalf Taktus
acts, so that its row-level and column-level security apply. UC-12.1 §2: in a rollout channel
every request is served with the user's own credential, and a user without one gets nothing
from that source.

Every connector already acts only with the credential the call names (ADR-0024: it declares
`permissions: passthrough` and has none of its own; conformance rule C-03). A step names its
credentials by parameter, for example `KNOWLEDGE_TOKEN`. That parameter resolves to one secret
for the whole tenant. So every person a process served was read for with the same rights: the
process's.

## Decision

### 1. A connector step may act on behalf of the run's identity

A connector step's work may carry `on_behalf: true`. The run engine then replaces every
credential the step names by the credential of the identity the run acts for (`Run.identity`,
the identity of the command that commissioned the plan). The replacement is made before the
call, so the connector sees only that person's credential.

### 2. Which credential is a person's own is configuration

The instance's configuration `TAKTUS_PERSONAL_CREDENTIALS` maps, per identity, a parameter a
step names to the parameter of that identity's own credential:
`person:ada/KNOWLEDGE_TOKEN=KNOWLEDGE_TOKEN_ADA`. It holds parameters only, never a value. The
operator creates each secret and maps it, as for every other credential (CLAUDE.md §9). The run
component reads the mapping through its port `PersonalCredentials`; the composition root
answers it from the configuration.

### 3. Without an own credential, nothing is read

An identity the mapping does not name for a parameter gets nothing from the source. The step
fails before any call, with the reason that the identity has no credential of its own, and the
outcome `unauthenticated`. It is never served with the process's credential instead. Its
fallback applies as for any failed step.

## Alternatives

- **The connector picks the credential by the identity in the call context.** Every connector
  would hold the mapping, and would then hold credentials of its own. That contradicts
  ADR-0024.
- **A token exchange at an identity provider, per call.** It is the stronger form where the
  organisation's sources trust one identity provider. Not every source does: a wiki or a
  warehouse often has accounts of its own. The mapping serves both; an exchange can later sit
  behind the same port.
- **Fall back to the process's credential when a person has none.** It would let a person learn
  through Taktus what the source would not have shown them. Rejected by UC-5.5 §1.

## Consequences

- `components/run/domain/model/work.py`: `ConnectorRule.on_behalf`.
- `components/run/ports/personal.py`: the port `PersonalCredentials`.
- `components/run/application/service/execute_run.py`: the replacement before the call, and the
  refusal without an own credential.
- `composition/personal.py` and `composition/settings.py`: `TAKTUS_PERSONAL_CREDENTIALS`, wired
  into the engine of `taktusctl` and of `taktusd`.
- Tests: `tests/components/run/test_on_behalf.py`.

## Where this promise ends

- The source's own rights are the boundary. Taktus passes the person's credential through; it
  does not check what the credential permits, and a credential that permits more than the
  person should see is the source's or the operator's error.
- The mapping is the instance's, not a tenant's. An identity is named the same way in every
  tenant of the instance.
- A credential that has expired or been withdrawn is refused by the source, not by Taktus. The
  step then fails with the source's refusal.
- Only connector steps act on behalf. A worker or a model step works with what earlier steps
  read; it reaches no source of its own on behalf of a person.
- A process that runs on a schedule acts for the identity that commissioned it. A step on behalf
  of that identity reads with that identity's credential, which may be a service identity's.
