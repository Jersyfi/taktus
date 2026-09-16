"""A fixed set of configured workers, resolved by capability.

Configuration maps a capability to a worker; the ledger records the configuration's identifier
and never a product. This pool is the simplest such configuration: a list of (identifier,
worker), the first whose declared capabilities cover what a step requires wins. Capabilities
are read once and kept.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.ports.worker import Worker
from taktus.shared.v1 import Capability


class StaticWorkerPool:
    def __init__(self, workers: Sequence[tuple[str, Worker]]) -> None:
        self._workers = list(workers)
        self._declared: dict[str, frozenset[str]] = {}

    async def resolve(self, required: Sequence[Capability]) -> tuple[str, Worker] | None:
        needed = set(required)
        for adapter, worker in self._workers:
            if adapter not in self._declared:
                declared = await worker.capabilities()
                self._declared[adapter] = frozenset(declared.capabilities)
            if needed <= self._declared[adapter]:
                return adapter, worker
        return None
