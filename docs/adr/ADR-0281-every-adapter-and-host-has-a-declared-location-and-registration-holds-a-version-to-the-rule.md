# ADR-0281 — Every adapter and host has a declared location, and registration holds a version to the rule

**Status:** accepted · extends ADR-0116 §3, ADR-0157 and ADR-0258 (the residency rule) and
ADR-0022 §4 (egress entries) · serves UC-11.1

## Context

A tenant's residency rule says where its data may be processed: `own`, `eu` or `anywhere`. It is
narrowed per process and per data class, and the narrowest holds (ADR-0258). The run held models
and workers to it (ADR-0116 §4, ADR-0157). Four things were missing for UC-11.1.

- A connector had no location. Nothing held a connector call to the rule.
- Registration accepted a version whose step could only be served outside the permitted
  location. The step failed at run time instead.
- An egress entry named the adapter an effect went out through, but not where that adapter is.
- The hosts a worker's unit may reach were not held to the rule.

## Decision

### 1. A connector's location is configured

`TAKTUS_CONNECTOR_LOCATIONS` declares a location per connector, by the label it has in
`TAKTUS_CONNECTORS`: `channel.repo=eu,channel.chat=own`. Each value is `own`, `eu` or
`elsewhere`. A label that `TAKTUS_CONNECTORS` does not name is refused at startup. A connector
whose location nobody declared counts as `elsewhere`, as a worker does (ADR-0157). The
connectors the instance brings itself — the loopback and the served directory — are `own`.
`ResolvedConnector.location` carries the location to the run.

### 2. A connector step is held at its boundary

A connector step's work may name the class of the data it carries, `data_class`, as a worker
step's and a model step's do. Wherever the run resolves a connector — at the estimate, at the
call, for a wait and for a check's reading — it asks the rule with the step's data class and the
run's process. A connector the rule does not admit is not called. The step fails, retryably,
with a reason that names the rule, the connector and its location.

The pool does not pass over such a connector for the next one. A capability is served by the
first connector that declares it, and a later one is not a stand-in for it: it reaches another
system. A model chain and a worker pool are ordered stand-ins; connectors are not.

### 3. A host's location is configured

`TAKTUS_HOST_LOCATIONS` declares a location per host, written as the host is written in a step's
`allowed_hosts` or a worker's service hosts: `api.example.eu=eu`. An undeclared host counts as
`elsewhere`. Before a worker step is assigned, the run reads the hosts its unit may reach: the
step's `allowed_hosts` and the chosen worker's own service hosts (ADR-0089). Where one is outside
the permitted location, nothing is assigned. The step fails, naming the rule and the host.

### 4. Registration holds a version to the rule

The process component asks a port, `ResidencyBindings`, for every step that would be bound
outside the permitted location. The composition root answers it from the pools, the tenant's
rule and the declared host locations. A step is bound outside when the rule for its data class
and its process is narrower than `anywhere` and one of these holds:

- a model step's purpose chain has members and none is admitted;
- a worker step's capabilities are offered only by workers outside the location;
- a connector step's connector is outside the location;
- a worker step's `allowed_hosts` names a host outside the location.

Such a version does not register. Each finding names the step, the data class, the adapter or
host, its location and what the rule permits. A step that no adapter serves at all is not a
residency finding: registration does not require an adapter to be configured.

### 5. Every outward effect names its location

Beside every egress entry the run writes `residency.egress`. It has the same step references and
the same adapter. Its outcome is the location the effect went to: `own`, `eu` or `elsewhere`. A
result defect delivered into the tracking system (ADR-0179) is followed by the same entry,
naming the incident. A rehearsal writes no egress, and therefore no such entry.

A companion entry was chosen over a field on the egress entry. `LedgerEntry` admits no property
it does not name. A new field would make every new egress entry unreadable to the previous
release (ADR-0093). A new kind uses only fields that release already reads.

## Alternatives

- **The location inside `TAKTUS_CONNECTORS`**, as a suffix of the URL. A URL may end in any
  character, so the suffix could not be told from the URL. A separate setting is read alone.
- **The connector declares its own location** in its declaration, as a worker does. A connector
  speaks for a product whose location the product's operator knows, not the connector. UC-11.1
  §3 places the declaration with whoever configures it.
- **Narrowing the hosts instead of failing the step.** A unit given fewer hosts than its work
  names fails later, somewhere inside the work, without naming the rule.
- **A field `location` on the egress entry.** Refused in §5.

## Consequences

- `ports/connector.py`: `ResolvedConnector.location`.
- `adapters/driven/connectors/pool.py`: the pool takes the declared locations.
- `composition/settings.py`: `TAKTUS_CONNECTOR_LOCATIONS`, `TAKTUS_HOST_LOCATIONS`.
- `run/domain/model/work.py`: `ConnectorRule.data_class`.
- `run/application/service/execute_run.py`: the connector check, the host check,
  `residency.egress`.
- `process/ports/residency.py`, `register_version.py`: the registration check.
- `composition/residency.py`: the port's answer from the pools.
- `contracts/shared/v1/LedgerEntry.json`: the kind `residency.egress` described.

## Where this promise ends

A location is what the operator declared; Taktus does not verify it. A worker's location is what
the worker declares. Registration cannot check a step whose worker cannot be asked what it offers
when the version registers; the run holds that step when it is assigned. Registration reads the
pools as they are configured when the version registers; a later change of configuration is held
by the run, not by registration again. A worker reached by endpoint keeps the reach its operator
gives it: only the frame's hosts it is handed are held to the rule, and its own network is not
Taktus's. Two connector calls are recorded with their location but not held to the rule: a cap
on open work reads its count through its connector, and a result defect is delivered into the
tracking system. The delivery sends an incident's situation package wherever the tracking
connector is. A worker's own tool calls are recorded as
`connector.called`, not as egress, and carry no location.
