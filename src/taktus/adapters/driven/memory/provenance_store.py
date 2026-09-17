from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import DuplicateProvenance, Tenant
from taktus.shared.v1 import Provenance


class MemoryProvenanceStore:
    """A list per tenant behind the provenance store port. Written once by construction:
    nothing here can replace or remove a record, and a step run recorded twice is refused."""

    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence

    async def append(self, tenant: Tenant, record: Provenance) -> None:
        transaction = self._persistence.current(tenant)
        key = (record.run_id, record.step_id)
        if any((r.run_id, r.step_id) == key for r in self._all(tenant)):
            transaction.spoilt = True  # as a database would: the transaction is done for
            raise DuplicateProvenance(tenant, record.run_id, record.step_id)
        transaction.recorded.append(record)

    async def of_run(self, tenant: Tenant, run_id: str) -> Sequence[Provenance]:
        self._persistence.current(tenant)
        return sorted(
            (r for r in self._all(tenant) if r.run_id == run_id), key=lambda r: r.ledger_seq
        )

    async def chain(self, tenant: Tenant, run_id: str, artifact_id: str) -> Sequence[Provenance]:
        self._persistence.current(tenant)
        records = self._all(tenant)
        by_step = {(r.run_id, r.step_id): r for r in records}
        start = next((r for r in records if r.run_id == run_id and r.produced(artifact_id)), None)
        if start is None:
            return []
        # Breadth first from the producer through what it read; each record once.
        found: dict[str, Provenance] = {start.id: start}
        queue = deque([start])
        while queue:
            for key in queue.popleft().reads_from():
                producer = by_step.get(key)
                if producer is not None and producer.id not in found:
                    found[producer.id] = producer
                    queue.append(producer)
        return sorted(found.values(), key=lambda r: r.ledger_seq, reverse=True)

    def _all(self, tenant: Tenant) -> list[Provenance]:
        transaction = self._persistence.current(tenant)
        return [*self._persistence.provenance(tenant), *transaction.recorded]
