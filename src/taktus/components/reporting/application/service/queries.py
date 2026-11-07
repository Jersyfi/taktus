"""The queries a step sent, read by a person entitled to the step (ADR-0262 §3, UC-5.6 §2).

The run records every query it sends through a querying capability as `query.sent`, with the
run and the step and the digest of the request; the request itself — the operation and its
input, the query's text among it — is in the object store. A query is read only where its run
is read: the run level's records answer whether there is such a run and step, and the one
predicate whether the reader may see it. A step the reader may not see is answered as one that
does not exist.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.components.reporting.domain.model.live import Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.ports.levels import LevelRecords
from taktus.ports.ledger import Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import UnitOfWork
from taktus.shared.v1 import StepId, Value

SENT = "query.sent"


class SentQuery(Value):
    """One query a step sent, as it was sent."""

    seq: int = Field(ge=1)
    """The position of its ledger entry in the run's chain."""
    sent_at: datetime
    operation: str = Field(min_length=1)
    query: str | None = None
    """The query's text; None where the request named none."""
    parameters: dict[str, Any] | None = None
    digest: str = Field(min_length=1)
    """The digest of the request in the object store, which the ledger entry names."""


class StepQueriesView(Value):
    run_id: str = Field(min_length=1)
    step_id: StepId
    queries: tuple[SentQuery, ...] = ()


class StepQueries:
    def __init__(
        self, *, records: LevelRecords, ledger: Ledger, objects: ObjectStore, work: UnitOfWork
    ) -> None:
        self._records = records
        self._ledger = ledger
        self._objects = objects
        self._work = work

    async def read(self, reader: Reader, run_id: str, step_id: str) -> StepQueriesView | None:
        """Every query the step sent, oldest first; None when there is no such step, or the
        reader may not see its run."""
        run = await self._records.run(reader.tenant, run_id)
        if run is None or not any(s.id == step_id for s in run.steps):
            return None
        ref = RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        if not visibility.may_see(reader, ref):
            return None
        async with self._work.transaction(reader.tenant):
            entries = await self._ledger.entries(reader.tenant, run_id)
        sent: list[SentQuery] = []
        for entry in entries:
            if entry.kind != SENT or entry.refs.step_id != step_id or not entry.content_digest:
                continue
            content = await self._objects.get(entry.content_digest)
            try:
                request = json.loads(content) if content is not None else {}
            except ValueError:
                request = {}
            given = request.get("input") if isinstance(request, dict) else None
            input = given if isinstance(given, dict) else {}
            query = input.get("query")
            parameters = input.get("parameters")
            sent.append(
                SentQuery(
                    seq=entry.seq,
                    sent_at=entry.ts,
                    operation=str(request.get("operation") or "unknown"),
                    query=query if isinstance(query, str) else None,
                    parameters=parameters if isinstance(parameters, dict) else None,
                    digest=entry.content_digest,
                )
            )
        return StepQueriesView(run_id=run_id, step_id=step_id, queries=tuple(sent))
