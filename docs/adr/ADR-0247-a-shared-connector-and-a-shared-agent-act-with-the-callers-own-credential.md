# ADR-0247 — A shared connector and a shared agent act with the caller's own credential

**Status:** accepted · extends ADR-0024 (connector contract), ADR-0246 (shares) and ADR-0163
(shared agents) · UC-8.7, UC-8.8 · DEC-0228

## Context

A connector has no credential of its own. A call names the credential it acts with, by name, in
its context, and the connector reads the value from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names at the moment of the call (ADR-0024,
`connectors/taktus_connectors/serving.py`). Every call of a run carries the run's identity. Until
now, though, it carried the credential names the step's work wrote down. Every identity that ran
the same step acted with the same credential.

UC-8.8 asks that every call through a shared connector act with the credential of the identity
that requests it, so that each identity sees only what the source system shows it. UC-8.7 asks
the same of a shared agent: each call runs in the rights, credentials and cost context of its
caller, never of its author. ADR-0024 left "how a runtime makes per-identity credentials
available" open.

## Decision

### 1. A caller's credential is a parameter of its own, bound to the identity

A **caller credential** (`catalog/domain/model/shares.py`, `CallerCredential`) binds one
identity and one credential name to the parameter that identity's value is provided under. It
is kept under `<identity>:<NAME>`. The parameter is `<NAME>_<SUFFIX>`, and the suffix is a name
the operator chose for that identity's credential. The operator provides the value as for any
parameter: in the file `TAKTUS_CREDENTIAL_<NAME>_<SUFFIX>_FILE` names. The binding holds no
value and no part of one. Changing it is recorded as `credential.bound`, by the person in
`refs.actor`, naming the identity's credential by name only.

### 2. A call through a shared connector names the caller's parameter, or is not made

Before a run calls a connector, it asks the port `Shares` (ADR-0246) for the credentials of the
call. For a connector with no share nothing changes: the call names what the step's work names.
For a shared connector each name the step's work names is replaced by the parameter bound to the
run's identity for that name. A name with no binding for the run's identity refuses the call
before it is made. The refusal is recorded as `frame.refused`, outcome `no_caller_credential`,
and the step fails without retrying. The finding names the identity, the credential name and
the command that binds one (`taktusctl catalogue bind-credential`).

The call never falls back to the name the work wrote, and never to the author's or the
operator's binding. A caller without a credential of their own is refused, not served with
someone else's.

### 3. The source system decides what the caller sees

Taktus passes the caller's credential through and never widens it (ADR-0024, permissions
`passthrough`). What one identity reads through a shared connector is what the source system
shows that credential.

### 4. A shared agent runs as its caller

A call of a shared agent runs its flow as the caller (ADR-0163): the command and the run carry
the caller's identity and organisational unit, and the run's budget is committed to the
caller's unit (ADR-0166). Every connector call in that run is a call of §2, with the caller's
binding. The author of the agent is named on the agent's share as its owner and nowhere in the
run.

### 5. A shared agent runs at most at the level its entry states

The share of an agent states the level of its active core. A call runs at the lower of that
level and the level of the flow's active version, as ADR-0163 already ran it. Nothing a caller
passes raises it, and a caller's own rights do not either.

### 6. An agent is shared only by a person who accepted it

Taktus may propose an agent's core. Sharing it is a person's act, and the share records that
person as `refs.actor` of `catalogue.shared`. A share requested with no person as actor is
refused with outcome `not_accepted`. So is the share of an agent whose core is not active
(ADR-0246 §4). Taktus never shares an agent on its own.

## Alternatives

- **One credential per connector, permissions in Taktus.** Taktus would filter what the source
  returns. It would widen access to whatever the one credential reaches. If a filter were
  missing or wrong, someone would see what the source system would have hidden. Rejected by
  ADR-0024's passthrough rule.
- **The value in the call's context.** The value would cross the contract, and every log and
  ledger line on its way would have to mask it. Rejected: a value never travels through the
  contract (ADR-0007).
- **Fall back to the work's name when the caller has none.** It is the author's credential
  under another name. Rejected by UC-8.7 §2.

## Consequences

- `catalog`: `CallerCredential`, kept in `caller_credential` (migration 0103).
- `run`: the port `Shares` answers the credentials of a call. The engine asks it before each
  connector call and refuses the call when the answer is a refusal.
- `CREDENTIALS.md` describes the pattern `<NAME>_<SUFFIX>`.
- A connector needs no change: it reads the parameter the reference names, as it always did.

## Where this promise ends

- The source system's permissions are the source system's. If two identities' credentials
  reach the same records there, both see them.
- The binding says which parameter holds an identity's value. That the operator provided the
  value of the right person under it is the operator's act. A connector reads the file the
  variable names and cannot tell whose credential it is.
- A connector deployment must be given the file of each bound parameter. A parameter that was
  bound and not provided answers `unauthenticated` from the connector, at the call.
- A worker's own tools act with the credentials of its assignment. This decision covers
  connector calls a run makes. A coding worker's credential is the assignment's, as before.
- A rehearsal answers its outward operations from recordings (ADR-0030) and calls nothing for
  them. Its reads call the connector, and they name the caller's own credential like any call.
