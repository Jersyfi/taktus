"""The advisory locks, in the two-key form: a namespace per purpose and a key within it.

PostgreSQL keeps the one-key (bigint) and the two-key (int, int) form in separate spaces, and
two purposes never share a namespace, so a ledger lock can neither meet a leadership lock nor
a projection lock. Within the ledger namespace the key is `tenant.lock_key`, unique per
tenant by the registry (migration 0062), not a hash of its id: two tenants never share one.
"""

from __future__ import annotations

LEADERSHIP = 1
"""Namespace of `try_lead`; the key within it is the hash of the role, roles being few and
named by the code."""
LEDGER = 2
"""Namespace of the claim on a tenant's own chain; the key is the tenant's `lock_key`."""
RUN_CHAIN = 3
"""Namespace of the claim on a run's chain (ADR-0164); the key is the hash of the tenant and
the run. Two runs whose keys collide only wait for each other: the claim is a mutual exclusion,
and the chain's places are checked by the verification all the same."""

# A writing transaction's marker (ADR-0164 §3) is one bigint in the one-key form, always
# negative: the bitwise complement of the tenant's `lock_key` in bits 40 and up and a bound
# below the transaction's first reading position in the low 40. No other key of either form is
# negative below -2^31, so the marker meets no other lock (migration 0091).

# A projection's claim (projection_store.py) is one bigint in the one-key form, a key space apart
# from the two-key form above: the tenant's `lock_key` in the high 32 bits, the hash of the
# projection's name in the low 32. Two projections of one tenant may share a key, which only
# makes a try-lock fail for the moment; two tenants never do.
