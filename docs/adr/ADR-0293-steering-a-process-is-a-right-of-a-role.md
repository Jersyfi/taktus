# ADR-0293 — Steering a process is a right of a role

**Status:** accepted · extends ADR-0131 §3 (rights per role), ADR-0257 (rights of a process) and
ADR-0244 §2 (the value basis) · serves UC-9.1, UC-9.2 · replaces the stand-in of NTC-0270

## Context

UC-9.1 §2 asks that a target can be set for each figure of each process "by a person with the
right to steer the process". A figure outside its target produces a proposal, so whoever sets a
target decides what Taktus proposes.

The targets are part of the **value basis**: the tenant's configuration, stated as a new version
each time (ADR-0244 §2). The basis also carries the transformation plan of UC-9.2, the time a
case takes by hand, the personnel cost rates per role and the potential a person entered. All of
it is what the figures are measured against.

No right of that name existed. NTC-0270 recorded a stand-in: a person holding the role `owner`
states the basis, until a right to steer exists.

## Decision

### 1. One right: `process.steer`

The identity component's rights gain `process.steer`: state the value basis of the tenant, with
its targets per process and figure and its plan. It is granted and withdrawn as every right is
(`taktusctl identity grant`, `/administration/rights`). Each grant is a ledger entry. It is a
right of a role, so no person holds it outside a role (UC-7.3).

### 2. Asked for once the tenant grants it

Stating the basis (`PUT /value/basis`) and reading its versions (`GET /value/basis`) ask for
`process.steer` once any role of the tenant holds it. Until then the stand-in of NTC-0270 holds,
and only a person holding `owner` may do either. This follows ADR-0257 §2: a tenant decides when
its rights hold by granting the first one. A tenant that granted nothing goes on as before, and no
stored record changes.

From the first grant on, only a person whose roles hold `process.steer` may state or read the
basis. That includes the owner: a tenant that grants the right to a role other than `owner`
moves the act to that role.

### 3. A refusal names the right

A person without the right is answered `403`. The answer names `process.steer` once the tenant
grants it, and `owner` before.

## Alternatives

- **A right per process.** UC-9.1 speaks of "the process". But the basis is one document for the
  tenant, versioned as a whole (ADR-0244 §2). A right per process would need the basis split per
  process, and the version digest a figure carries would no longer name one basis.
- **One right for targets and another for rates and the plan.** The parts of the basis are read
  together by every figure. A tenant that wants them apart can still keep `process.steer` to one
  role. Nothing yet asks for the split.
- **The right asked for from the first day.** Every tenant without a grant would lose the act it
  has now. Its owner could not state a target until an administrator granted the right.
- **Granting the right to `owner` by default.** There is no shipped default of rights to put it
  in, and existing tenants would need a migration of their records. Section 2 keeps them working
  without one.

## Consequences

- `identity/domain/model/identity.py`: `Right.PROCESS_STEER`.
- `adapters/driving/rest/figures.py`: `GET` and `PUT /value/basis` ask for it as section 2 says.
- `tests/adapters/rest/test_figures.py`: a role without the right is refused, one with it states
  the basis, and the owner keeps the act until the first grant.

## Where this promise ends

- The right holds for the value basis on the HTTP surface. The basis has no other way in today.
  If a command or a dialogue ever states the basis, it must ask for the same right. This ADR does
  not build that.
- The right covers the whole basis. A target cannot be given to one role for one process alone.
- The configuration of views and reports (UC-6.4, UC-6.2) is not steering a process. It stays with
  `owner`, as ADR-0241 §2 and ADR-0242 decide.
- Raising a process's autonomy level is not part of this right. It stays `autonomy.set`
  (ADR-0257). A simulation of a higher level changes nothing (UC-9.1).
- An identity proves itself as the surface proves it, by its account key or the web app's
  session. A role's holders are whoever the tenant gave the role.
