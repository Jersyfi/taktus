# ADR-0104 — Tenants are created by a command and kept in the database

**Status:** accepted · from DEC-0187 answer 1, issue #318 · amends ADR-0020 §4

## Context
ADR-0020 separates tenants inside one instance. Its §4 says one tenant, `default`, is created by
migration until the identity component exists. Since then nothing else has created a tenant.

An instance learns which tenants it serves from `TAKTUS_TENANTS`, read once at start. The review
of 2026-10-12 (`docs/research/2026-10-12-devops-review.md`, T1) found three faults in that:

- **Nothing creates a tenant.** An operator had to insert a row by hand and then list it.
- **A new tenant needs a restart.** Every role reads the list once.
- **The list has a ceiling.** One environment variable of 128 KiB holds about 3 500 tenant
  identifiers shaped like UUIDs.

The owner answered who creates a tenant (DEC-0187 answer 1). An administrator of the instance
creates it, through a command or the HTTP surface. Taktus generates the identifier. The display
name is separate. A customer never chooses an identifier.

## Decision

### 1. The tenant table is the registry
The table `tenant` of migration 0001 holds every tenant of the instance: its identifier, its
display name and when it was created. No other list exists. The identity component owns it,
as `components/identity/__init__.py` already says.

The persistence port gains `TenantStore`, with two implementations: the database and the
in-memory store.

- `add`, `get` and `rename` work inside a unit of work opened for the tenant they name. The
  row-level security of migration 0001 already lets a transaction write its own tenant's row.
- `every` reads the whole registry outside any unit of work. It is the one read that sees
  more than one tenant's row.

The in-memory store always holds `default`, as the migration does.

### 2. The registry is read through its own policy
The forced row-level security on `tenant` lets a transaction see only the row of the tenant it
names. Migration 0053 adds a second policy for reading only. It admits every row when the
session setting `taktus.registry` is `on`.

Only `TenantStore.every` sets it, in a transaction of its own. A tenant's transaction that forgets
a filter still sees its own row and nothing else.

### 3. Taktus generates the identifier
`taktusctl tenant create NAME` creates a tenant. So does `POST /administration/tenants` on the
HTTP surface. The identifier is `tnt_` followed by 20 random hexadecimal characters, from the
identifier port. Neither surface accepts an identifier from the caller.

The display name is required and at most 200 characters long. `taktusctl tenant rename` and
`PATCH /administration/tenants/{tenant}` change it, and the identifier stays. `taktusctl tenant
list` and `GET /administration/tenants` list the registry, oldest first.

### 4. Who may administer tenants
The command line follows ADR-0040 §6: whoever can run it against the instance's database is
the instance's administrator.

The HTTP surface admits the holder of the instance's administration key. The operator creates
the key and supplies it as configuration key `administration.key`, a file named by
`TAKTUS_ADMINISTRATION_KEY_FILE`. A request proves it with `Authorization: Bearer`, compared in
constant time. Without the key configured, the routes answer `404` and say how to enable them.

An account key of an identity is not admitted. An identity belongs to one tenant. Administering
the instance from inside a tenant would let a tenant reach past its own boundary.

### 5. Every tenant created is an entry of the ledger
The repository has no ledger of the instance. ADR-0020 §4 keeps one hash chain per tenant. Facts
about the whole instance are written to the chain of each tenant they concern, as the capacity
report does.

The smallest shape that follows is this. Creating a tenant inserts its row and appends
`tenant.created` to the new tenant's own chain, in one transaction, as its first entry. A rename
appends `tenant.renamed` to the tenant's chain in the transaction of the change.

Each entry carries the tenant, the acting administrator where one is named, and the digest of
the identifier and the name. It never carries the name itself (ADR-0006). The registry's
`created_at` and each chain's first entry answer "which tenants were created when".

No other tenant's chain is written. An entry there would tell one tenant that another exists.

### 6. Every role reads the current set on every round
Every role asks the registry which tenants it serves each time it visits them:

- the runner, at every claim round;
- the scheduler, at every tick, for triggers, the capacity report, the findings and the broken
  interfaces;
- the automation role, at every pass;
- the identity component, at every resolution, authentication and administrative act.

A tenant created while the daemon runs is therefore served by every role at the role's next
round. That is within one poll interval, `TAKTUS_POLL_SECONDS`. The read returns the identifiers
alone, oldest first.

### 7. `TAKTUS_TENANTS` is deprecated
Unset, an instance serves every tenant of its registry. Set, it narrows the registry to the
tenants it names; a tenant it names that the registry does not hold is not served. The daemon
logs a warning at start while it is set.

The first minor release that carries the registry accepts the variable. The minor release after
it removes it (#517). Neither the chart nor compose sets it.

## Alternatives
- **Keep the list and reread it on a signal.** It removes the restart and keeps the ceiling and
  the hand-inserted row.
- **A separate table of the instance without row-level security.** It would be the first table
  without the tenant boundary. A policy that admits a read only when asked keeps the boundary
  in every other transaction.
- **An instance ledger as a chain of its own.** ADR-0020 §4 keeps one chain per tenant. A chain
  that belongs to no tenant needs a tenant row of its own or a second chain model. Either is
  more than this task needs.
- **Admit an identity with an administrator role on HTTP.** The identity belongs to one tenant.
  Its role would reach every tenant.

## Consequences
- The persistence port gains `TenantEntry`, `TenantExists` and `TenantStore`. The identity port
  gains `ServedTenants`. The identity component gains `TenantRegistry`.
- The runner, the triggers, the reactions, the capacity tick, the findings tick, the interfaces
  tick and the identity directory take a `ServedTenants`, not a fixed list.
- The command line gains `taktusctl tenant`. The HTTP surface gains `/administration/tenants`, and
  `api/openapi.yaml` is regenerated.
- `CREDENTIALS.md` gains the administration key.
- Tests that share one database keep apart by narrowing with `TAKTUS_TENANTS`. Its removal needs
  them to keep apart in another way: since #517 each integration test has a database of its
  own, copied from a migrated template.

## Amendment — the variable is removed before a release carried it (2026-10-28)
§7 accepted `TAKTUS_TENANTS` for the first minor release that carries the registry, and removed
it in the next. No minor release was tagged between the registry (#318) and its removal (#517):
the tags are release candidates of `0.2.0`, and the registry arrived after them. The installed
instances run the chart or compose, and neither sets the variable. The one release the
deprecation was for therefore never existed, and keeping the variable for one would protect
nobody.

The variable is removed now. A daemon that still sets it to a value refuses to start, and its
message names `taktusctl tenant create` and `taktusctl tenant list`. It is not quietly widened
to every tenant of the registry, which would serve tenants its operator had left out. Set empty,
it narrowed nothing, and it is ignored. The command line does not read it. The integration
tests keep apart through a database of each test's own (`tests/integration/conftest.py`).

## Where this promise ends
A tenant is served within one poll interval of its creation by every role that is running a round
at the time. A role that is stopped or stalled serves nobody until it runs again. The registry is
read once per round. An instance with many tenants therefore pays one read of the whole registry
per round per role, and the cost of visiting each tenant stays (#350).

The identifier is generated, and the surfaces accept none. Migration 0001's `default` and a row an
operator inserts with the database's own tools are outside that rule. The administration key on
HTTP is a single secret: whoever holds it administers every tenant of the instance, and the
ledger names only the administrator the request names. This ADR does not suspend, export or
delete a tenant (#351). An operator who set `TAKTUS_TENANTS`
learns of its removal when the upgraded daemon refuses to start, not one release earlier.
