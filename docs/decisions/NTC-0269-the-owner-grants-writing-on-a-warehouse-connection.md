# NTC-0269 — The owner grants writing on a warehouse connection

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-07
**Raised in:** branch `area/knowledge-warehouse` of `concept/release-1-0` (release 1.0, concept mode, DEC-0228)
**How it follows:** UC-5.6 §2 asks that writing be "a grant on that connection, made by a person
with the right to make it", and names no role. The vision's guiding principle 10 keeps the whole
autonomy range with guardrails, and section 8 of CLAUDE.md keeps with a person every act that
sets where a tenant's system goes. The role that already decides such acts by default is
`owner`: the shipped owner channel takes the requests addressed to it (`OwnerChannel.roles`),
and a corridor's red value reaches it in the shipped bundles. UC-5.6 names one connection whose
writes must wait for a grant, the warehouse's; the strict reading keeps every other connection
as it is, since UC-5.6 does not reach them.

## 1. What was decided

- **The right to grant writing on a connection is held by the role `owner`**
  (`GRANTING_ROLE` in `components/governance/domain/model/connections.py`). A run, a worker's
  assignment, an identity the tenant does not know and a person without the role are refused,
  and the refusal is recorded as `connection.refused`.
- **One connection reads until granted: that of `warehouse.queries`** (`READ_UNLESS_GRANTED` in
  `ports/connector.py`). Every other connection writes as before.
- **One capability is querying: `warehouse.queries`** (`QUERYING`). Its queries are recorded by
  reference, and where its figures may go is a rule of registration (ADR-0262 §3, §4).

## 2. The evidence

- `tests/components/governance/test_connection_grants.py`: the owner grants and withdraws;
  a process, a worker, an unknown identity and an analyst are refused, each recorded.
- `tests/adapters/rest/test_connections.py`: the same on the HTTP surface, 403 for an analyst.
- `tests/components/run/test_warehouse.py`: a write without the grant reaches nothing.

## 3. What was considered

- **A right of its own, given to roles by the tenant.** The rights a role holds today are the
  agent surface's (ADR-0131 §3); a right for connections would be a new piece of the rights
  model (UC-7.3). It is the place a finer rule goes later; one role is the strict default now.
- **Every connection reads until granted.** Every process that writes would stop at once; UC-5.6
  does not ask for it (ADR-0262, *Alternatives*).
- **A decision request.** The use case and the existing defaults give the direction; nothing
  strategic is set.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

**M2.14** — *A right a use case names without naming the role that holds it is held by the
role `owner`, until a tenant's rights model names another; the role is a constant beside the
record the right acts on.*
