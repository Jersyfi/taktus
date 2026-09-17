"""In-memory persistence — DEVELOPMENT AND TEST ONLY. Not a supported deployment.

Everything lives in the process; nothing survives it unless a snapshot directory is given, in
which case every committed transaction writes the stores it touched to JSON files there and
reads them back on start. That is what lets `taktusctl run --resume` find a run from an earlier
invocation on a developer's machine without a database. It is not durable, not shared between
instances, and not what ADR-0013 A asks for; the database adapter is.

It answers the same repository test suite as the database adapter (`tests/adapters/persistence`):
a tenant on every call, a unit of work around every call, and a transaction that leaves nothing
behind when it fails.
"""

from taktus.adapters.driven.memory.ledger_store import MemoryLedgerStore
from taktus.adapters.driven.memory.object_store import MemoryObjectStore
from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.adapters.driven.memory.provenance_store import MemoryProvenanceStore
from taktus.adapters.driven.memory.repository import MemoryRepository

__all__ = [
    "MemoryLedgerStore",
    "MemoryObjectStore",
    "MemoryPersistence",
    "MemoryProvenanceStore",
    "MemoryRepository",
]
