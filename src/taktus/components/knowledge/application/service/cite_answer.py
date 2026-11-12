"""Use case: an answer drawn from knowledge is cited, and the index learns what was read (UC-5.5,
ADR-0265 §3 and §4).

The run's step `cite` hands over the answer, the documents its search read and the versions its
confirmation read. The handler reads the index's entries of those documents, cites the answer
against them (`domain/service/citing.py`) and records every observation into the index
(`domain/service/indexing.py`), in one unit of work. The observations are recorded also where
the answer is refused: what the source held is true whatever the model made of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from taktus.components.knowledge.domain.model.index import KnowledgeEntry, entry_id
from taktus.components.knowledge.domain.service import indexing
from taktus.components.knowledge.domain.service.citing import (
    Refused,
    cite,
    held_now,
    readings,
)
from taktus.ports.persistence import Repository, UnitOfWork


@dataclass(frozen=True)
class CiteAnswer:
    tenant: str
    capability: str
    """The capability the documents were read through."""
    answer: Any
    documents: Any
    """What the search answered: its `documents`."""
    confirmed: Any
    """What the reading of versions answered: its `documents`; None where none was made."""
    read_at: datetime
    """When the search read the documents: when its step finished."""
    confirmed_at: datetime | None


class CiteAnswerHandler:
    def __init__(self, entries: Repository[KnowledgeEntry], work: UnitOfWork) -> None:
        self._entries = entries
        self._work = work

    async def execute(self, command: CiteAnswer) -> dict[str, Any]:
        read = readings(command.documents)
        now = held_now(command.confirmed)
        tenant, capability = command.tenant, command.capability
        async with self._work.transaction(tenant):
            entries: dict[str, KnowledgeEntry] = {}
            for document in read:
                found = await self._entries.get(tenant, entry_id(capability, document))
                if found is not None:
                    entries[document] = found
            refused: Refused | None = None
            cited: dict[str, Any] = {}
            try:
                cited = cite(
                    command.answer,
                    command.documents,
                    command.confirmed,
                    capability=capability,
                    read_at=command.read_at,
                    confirmed_at=command.confirmed_at,
                    entries=entries,
                )
            except Refused as error:
                refused = error
            for document, found_read in read.items():
                entry = indexing.read(
                    entries.get(document),
                    tenant=tenant,
                    capability=capability,
                    found=found_read,
                    at=command.read_at,
                )
                if document in now and command.confirmed_at is not None:
                    entry = indexing.held(entry, now[document], command.confirmed_at)
                await self._entries.put(tenant, entry)
        if refused is not None:
            raise refused
        return cited
