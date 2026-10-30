"""Use case: a tenant declares its value streams, and reads them as they are now (UC-15.6,
ADR-0159 §4).

A declaration names the stream's kind, trigger, outcome, responsible role and processes. It is
refused, naming every finding, where a process it names does not exist in the tenant. A
declaration that says what the stream's current revision says keeps nothing new and records
nothing. Any other is kept as the next revision, and the revision before stays: a stream's
history is never deleted. Each kept revision is the ledger entry `value_stream.declared`, with
the identity that declared it and the digest of what it declares.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    StreamKind,
    ValueStream,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

DECLARED = "value_stream.declared"


@dataclass(frozen=True)
class DeclareStream:
    tenant: Tenant
    stream: str
    name: str
    kind: StreamKind
    trigger: str
    outcome: str
    role: str
    processes: Sequence[str]
    by: str


class ValueStreams:
    def __init__(
        self,
        streams: Repository[ValueStream],
        processes: Repository[Process],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._streams = streams
        self._processes = processes
        self._work = work
        self._ledger = ledger
        self._clock = clock

    async def declare(self, command: DeclareStream) -> ValueStream:
        """The stream as it is now: the new revision, or the current one where nothing
        changed. `InvalidProcess` with every finding where it is refused."""
        async with self._work.transaction(command.tenant):
            known = {p.id for p in await self._processes.list(command.tenant)}
            missing = [p for p in command.processes if p not in known]
            if missing:
                raise InvalidProcess(tuple(f"the tenant has no process {p!r}" for p in missing))
            revisions = [
                s for s in await self._streams.list(command.tenant) if s.stream == command.stream
            ]
            current = max(revisions, key=lambda s: s.revision, default=None)
            revision = 1 if current is None else current.revision + 1
            try:
                declared = ValueStream(
                    id=f"{command.stream}@{revision}",
                    tenant=command.tenant,
                    stream=command.stream,
                    revision=revision,
                    name=command.name,
                    kind=command.kind,
                    trigger=command.trigger,
                    outcome=command.outcome,
                    role=command.role,
                    processes=tuple(command.processes),
                    declared_at=self._clock.now(),
                )
            except ValueError as error:
                raise InvalidProcess((str(error),)) from error
            if current is not None and current.same_as(declared):
                return current
            await self._streams.put(command.tenant, declared)
            canonical = json.dumps(
                declared.model_dump(
                    mode="json", include={"name", "kind", "trigger", "outcome", "role", "processes"}
                ),
                sort_keys=True,
                ensure_ascii=False,
            )
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=DECLARED,
                    refs=LedgerRefs(tenant=command.tenant, actor=command.by),
                    outcome="declared",
                    content_digest="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
                ),
            )
        return declared

    async def current(self, tenant: Tenant) -> list[ValueStream]:
        """Every stream of the tenant at its newest revision, by its identifier."""
        async with self._work.transaction(tenant):
            listed = await self._streams.list(tenant)
        newest: dict[str, ValueStream] = {}
        for stream in listed:
            held = newest.get(stream.stream)
            if held is None or stream.revision > held.revision:
                newest[stream.stream] = stream
        return [newest[k] for k in sorted(newest)]
