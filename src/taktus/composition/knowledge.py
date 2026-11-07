"""The run's port `Citations` over the knowledge component (UC-5.5, ADR-0265 §3).

The run cites an answer drawn from knowledge through this port; the knowledge component owns
the rule and the index. Components never import each other, so the composition root joins
them here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from taktus.components.knowledge.application.service import CiteAnswer, CiteAnswerHandler
from taktus.components.knowledge.domain.model import KnowledgeEntry
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class IndexedCitations:
    """`run.ports.Citations`: the answer cited, and what was read recorded into the index."""

    def __init__(self, entries: Repository[KnowledgeEntry], work: UnitOfWork) -> None:
        self._handler = CiteAnswerHandler(entries, work)

    async def cite(
        self,
        tenant: Tenant,
        *,
        capability: str,
        answer: Any,
        documents: Any,
        confirmed: Any,
        read_at: datetime,
        confirmed_at: datetime | None,
    ) -> dict[str, Any]:
        return await self._handler.execute(
            CiteAnswer(
                tenant=tenant,
                capability=capability,
                answer=answer,
                documents=documents,
                confirmed=confirmed,
                read_at=read_at,
                confirmed_at=confirmed_at,
            )
        )
