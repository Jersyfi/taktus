"""Recorded responses (ADR-0030): what a rehearsal run answers an outward connector operation
with, instead of calling it.

A recording is the stored result of the most recent real call of the same operation through
the same adapter in the same tenant. The choice is the domain's rule (`domain.service.
rehearsal.recording`); this query reads the tenant's runs to apply it, and the object store
for the result the chosen step run kept. The engine asks it while rehearsing; the removal
test asks it beforehand, to know whether a process can be rehearsed at all.
"""

from __future__ import annotations

import json
from typing import Any

from taktus.components.run.domain.model import Run
from taktus.components.run.domain.service.rehearsal import Recording, recording
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class RecordedResponses:
    def __init__(self, runs: Repository[Run], work: UnitOfWork, objects: ObjectStore) -> None:
        self._runs = runs
        self._work = work
        self._objects = objects

    async def find(self, tenant: Tenant, adapter: str, operation: str) -> Recording | None:
        """Where the recording is, or None when the operation was never called for real
        through the adapter in this tenant."""
        async with self._work.transaction(tenant):
            runs = await self._runs.list(tenant)
        return recording(runs, adapter, operation)

    async def response(
        self, tenant: Tenant, adapter: str, operation: str
    ) -> tuple[Recording, dict[str, Any]] | None:
        """The recording and the result document it kept: `{output, effect, consumption}`.
        None when there is none, or when its content is no longer available."""
        found = await self.find(tenant, adapter, operation)
        if found is None:
            return None
        content = await self._objects.get(found.digest)
        if content is None:
            return None
        document = json.loads(content)
        if not isinstance(document, dict):
            return None
        return found, document
