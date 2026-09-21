"""A fixed set of configured workers, resolved by capability.

Configuration maps a capability to a worker; the ledger records the configuration's identifier
and never a product. This pool is the simplest such configuration: a list of (identifier,
worker), the first whose declared capabilities cover what a step requires wins. Capabilities
are read once and kept, and so is the version the worker declares, which the provenance of
every result the worker produces carries.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.ports.worker import ResolvedWorker, Worker
from taktus.shared.v1 import Capability


class StaticWorkerPool:
    def __init__(self, workers: Sequence[tuple[str, Worker]]) -> None:
        self._workers = list(workers)
        self._declared: dict[str, tuple[frozenset[str], str | None]] = {}

    async def resolve(self, required: Sequence[Capability]) -> ResolvedWorker | None:
        needed = set(required)
        for adapter, worker in self._workers:
            if adapter not in self._declared:
                declared = await worker.capabilities()
                self._declared[adapter] = (frozenset(declared.capabilities), declared.version)
            capabilities, version = self._declared[adapter]
            if needed <= capabilities:
                return ResolvedWorker(adapter=adapter, worker=worker, version=version)
        return None

    async def members(self) -> list[tuple[str, frozenset[str]]]:
        """Every configured worker with the capabilities it declares — what the removal test
        reads to know what is configured."""
        found = []
        for adapter, worker in self._workers:
            if adapter not in self._declared:
                declared = await worker.capabilities()
                self._declared[adapter] = (frozenset(declared.capabilities), declared.version)
            found.append((adapter, self._declared[adapter][0]))
        return found

    def without(self, adapter: str) -> StaticWorkerPool:
        """The same configuration with one worker withheld: what the removal test runs a
        process against. The original is untouched; restoring is not using this one."""
        pool = StaticWorkerPool([(a, w) for a, w in self._workers if a != adapter])
        pool._declared = {a: d for a, d in self._declared.items() if a != adapter}
        return pool
