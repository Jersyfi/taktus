# ADR-0123 — An advisory lock is taken in the two-key form, under the tenant registry's key

**Status:** accepted · extends ADR-0104 (the tenant registry) and ADR-0093 (rolling updates) · issue #317, DEC-0187

## Context

The ledger's chain claim was `pg_advisory_xact_lock(hashtext('taktus.ledger:<tenant>'))`, the
leadership lock `pg_try_advisory_lock(hashtext('taktus.lead:' || role))`, and a projection's
claim a hash of tenant and name. Each key is 32 bits, and all lived in one key space.
Two tenants whose keys are equal wait for each other's chain. A tenant id is generated
(DEC-0187, answer 1), so equality happens by chance: at 10 000 tenants a collision is 1.2 %
likely. A tenant id whose key equals the leadership key could not write while the leader lived.

## Decision

1. **Two-key form with a namespace per purpose.** `pg_advisory_*lock(namespace, key)`. The
   namespaces are constants in `adapters/driven/postgres/_locks.py`: leadership is 1, the
   ledger is 2. Two purposes never share a namespace, so one cannot meet the other.
2. **The ledger's key is the tenant's `lock_key`.** A column of the registry table `tenant`,
   an identity the database assigns, unique by constraint (migration 0062). Two tenants never
   share a key.
3. **The leadership key stays the hash of the role** within its own namespace. Roles are few
   and named by the code, never by a tenant.
4. **A projection's claim** is a single bigint, the tenant's `lock_key` in the high 32 bits and
   the hash of the projection's name in the low 32. The one-key form is a key space apart from
   the two-key form.

## Alternatives

- **A row lock on a chain-head row.** It needs no key at all and could not collide. Rejected:
  it adds a row that every append updates, on a table the application role may otherwise only
  insert into (the ledger is append-only by trigger), and the claim is needed before the first
  entry exists. The registry row exists from the tenant's creation.
- **A wider hash (64 bits).** It lowers the chance of a collision and does not remove it.
  Rejected: the requirement is that none can happen.

## Consequences

- The key is read with the claim, in the same statement, from the tenant's own row.
- A tenant created before the migration receives a key when the column is added.

## Where this promise ends

- No two tenants share a ledger claim, and no ledger claim meets the leadership claim. Two
  projections of one tenant may share a claim. A try-lock of one then fails for the moment.
- During a rolling update an old instance still takes the old one-key locks. Old and new
  forms exclude nobody from each other until the old instances are gone; the chain's primary
  key `(tenant, seq)` stays the backstop for the ledger (ADR-0093).
- A key is unique within the 2^31 identity range. The chain's shape is not touched (#341).
