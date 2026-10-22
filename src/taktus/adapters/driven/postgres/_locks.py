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
"""Namespace of the ledger chain claim; the key is the tenant's `lock_key`."""
