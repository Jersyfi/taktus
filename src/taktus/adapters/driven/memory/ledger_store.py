from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from taktus.adapters.driven.memory import _snapshot
from taktus.shared.v1 import LedgerEntry


class MemoryLedgerStore:
    """A list behind the ledger store port. Append-only by construction: nothing here can
    replace or remove an entry."""

    def __init__(self, snapshot: Path | None = None) -> None:
        self._snapshot = snapshot
        self._entries: list[LedgerEntry] = []
        if snapshot is not None:
            for document in _snapshot.read(snapshot) or []:
                self._entries.append(LedgerEntry.model_validate(document))

    async def append(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)
        if self._snapshot is not None:
            await _snapshot.write(self._snapshot, [e.document() for e in self._entries])

    async def last(self) -> LedgerEntry | None:
        return self._entries[-1] if self._entries else None

    async def entries(self) -> Sequence[LedgerEntry]:
        return tuple(self._entries)
