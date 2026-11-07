# ADR-0259 — A domain has one owner, and its legal anchors per jurisdiction

**Status:** accepted · builds on ADR-0008 (anchors, reducible and never empty), ADR-0042 (the
anchor at the step boundary) and ADR-0180 (takeover instructions and their trial) · serves
UC-15.5

## Context

UC-15.5 asks that every domain an organisation instantiates has exactly one human owner. A
domain without one cannot be instantiated. A domain whose owner leaves is shown without one,
and nothing in it is raised in autonomy until a new one is named. The legal-anchor catalogue is
configurable per domain and per jurisdiction and never reduced to nothing. Every domain shows
whether its takeover test and its removal test passed.

An anchor already carries a scope with a domain and a jurisdiction (`contracts/shared/v1`). The
scope was not evaluated, because no domain existed: such an anchor held everywhere.

## Decision

### 1. A domain is a record of the tenant

A domain has an identifier, a name, an owner, a jurisdiction and its processes. The owner is an
identity of the tenant. The jurisdiction is an ISO 3166 code, a country (`DE`) or a region
(`DE-BY`). A process belongs to one domain at most. A domain is instantiated with an owner the
tenant knows, or it is refused. `domain.instantiated`, `domain.owner_named` and
`domain.owner_left` record the changes, by the person who made them.

### 2. Without an owner, nothing is raised

When the owner leaves, the domain is kept with no owner and is shown so. Registration refuses a
version that raises a level of a process whose domain has no owner. `autonomy.refused` records
it with outcome `no_owner`. A version that raises nothing registers.

### 3. The catalogue is the tenant's anchors, read in the domain's scope

The legal anchors in force for a domain are the tenant's legal anchors that are unscoped, or
whose scope names the domain or a jurisdiction that covers the domain's. `DE` covers `DE-BY`.
An anchor whose scope names a domain or a jurisdiction no domain of the tenant has holds
everywhere, as before. A domain for which no legal anchor would be in force is not instantiated.
A configuration of anchors that would leave a domain with none is refused. The run applies an
anchor scoped to a domain only to that domain's processes.

### 4. Takeover and removal per domain

A domain's view names, per process, whether a person passed the trial of its active version's
takeover instructions. It names whether every adapter that served a step of the process, as the
ledger records it, has a removal verdict that is `changed` or `exception`. The domain is shown
as able to run without Taktus only where both hold for every one of its processes.

## Alternatives

- **The owner as a role.** A role can be held by several people or by none. UC-15.5 asks for
  exactly one person. A person's steps still name roles (ADR-0146).
- **A catalogue as a record of its own.** The anchors already carry the scope. A second list
  would let the same legal act be configured twice, in two places that can disagree.

## Consequences

- `governance/domain/model/domains.py`, `governance/application/service/domains.py`,
  `governance/ports/domains.py`; `composition/domains.py`.
- `governance/domain/service/anchors.py`: `in_scope`, `legal_for`; `AnchorsInForce` and
  `ConfigureAnchorsHandler` read the domains.
- `process/ports/domains.py`: `DomainOwners`; `RegisterProcessVersionHandler(domains=...)`.
- Migration 0105: `domain`.
- `tests/components/governance/test_domains.py`.

## Where this promise ends

The domain's owner is recorded and shown. Escalations, proposals to raise a level and the
takeover test are not yet addressed to the owner: they still go to the roles they name. The
catalogue in force does not yet appear in generated conformity evidence (UC-11.3). An owner who
leaves is recorded by a person's act; the identity component does not yet remove identities, so
nothing records a departure by itself. The removal test is read from the adapters that served
the process so far; an adapter that would serve it and has not yet is not counted. No domain is
offered on a surface other than the application service yet.
