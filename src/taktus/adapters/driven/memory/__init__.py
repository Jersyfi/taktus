"""In-memory persistence — DEVELOPMENT AND TEST ONLY. Not a supported deployment.

Everything lives in the process; nothing survives it unless a snapshot path is given, in which
case each store writes its whole content to one JSON file after every change and reads it back
on start. That is what lets `taktusctl run --resume` find a run from an earlier invocation on
a developer's machine. It is not durable, not concurrent, and not what ADR-0013 A asks for; the
database adapter is.
"""

from taktus.adapters.driven.memory.ledger_store import MemoryLedgerStore
from taktus.adapters.driven.memory.object_store import MemoryObjectStore
from taktus.adapters.driven.memory.repository import MemoryRepository

__all__ = ["MemoryLedgerStore", "MemoryObjectStore", "MemoryRepository"]
