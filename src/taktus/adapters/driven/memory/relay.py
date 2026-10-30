"""The relay in memory — DEVELOPMENT AND TEST ONLY, like the rest of this package (ADR-0156).

One process holds every request in flight. Every instance that shares it is in that process,
which is the only place this adapter runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from taktus.ports.relay import Begun, RelayAnswer, RelayChunks, RelayCount
from taktus.ports.worker import RelayRequest


@dataclass
class _Row:
    worker: str
    request: RelayRequest
    created_at: datetime
    taken: bool = False
    answer: RelayAnswer | None = None
    chunks: list[tuple[int, bytes]] = field(default_factory=list)
    ended: bool = False
    answers: int = 0


class MemoryRelay:
    def __init__(self) -> None:
        self._rows: dict[str, _Row] = {}

    async def put(self, worker: str, request: RelayRequest) -> None:
        self._rows[request.request_id] = _Row(worker, request, datetime.now(UTC))

    async def take(self, worker: str) -> RelayRequest | None:
        for row in self._rows.values():
            if row.worker == worker and not row.taken:
                row.taken = True
                return row.request
        return None

    async def begin(
        self, worker: str, request_id: str, status: int, content_type: str | None
    ) -> Begun:
        row = self._rows.get(request_id)
        if row is None or row.worker != worker or not row.taken:
            return "unknown"
        row.answers += 1
        if row.answer is not None:
            return "answered"
        row.answer = RelayAnswer(status=status, content_type=content_type)
        return "begun"

    async def append(self, request_id: str, seq: int, chunk: bytes) -> bool:
        row = self._rows.get(request_id)
        if row is None:
            return False
        row.chunks.append((seq, chunk))
        return True

    async def end(self, request_id: str) -> None:
        row = self._rows.get(request_id)
        if row is not None:
            row.ended = True

    async def answer(self, request_id: str) -> RelayAnswer | None:
        row = self._rows.get(request_id)
        return None if row is None else row.answer

    async def chunks(self, request_id: str, after: int) -> RelayChunks:
        row = self._rows.get(request_id)
        if row is None:
            return RelayChunks(gone=True)
        return RelayChunks(
            chunks=tuple((seq, body) for seq, body in row.chunks if seq > after), ended=row.ended
        )

    async def done(self, request_id: str) -> None:
        self._rows.pop(request_id, None)

    async def counts(self, request_ids: Sequence[str]) -> Sequence[RelayCount]:
        return [
            RelayCount(
                request_id=request_id,
                answers=row.answers,
                status=None if row.answer is None else row.answer.status,
            )
            for request_id in request_ids
            if (row := self._rows.get(request_id)) is not None
        ]

    async def purge(self, before: datetime) -> int:
        old = [key for key, row in self._rows.items() if row.created_at < before]
        for key in old:
            del self._rows[key]
        return len(old)
