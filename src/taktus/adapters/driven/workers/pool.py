"""A fixed set of configured workers, resolved by capability.

Configuration maps a capability to a worker; the ledger records the configuration's identifier
and never a product. This pool is the simplest such configuration: a list of (identifier,
worker), the first whose declared capabilities cover what a step requires wins. Capabilities
are read once and kept, and so is the version the worker declares, which the provenance of
every result the worker produces carries. A worker that cannot be asked is not passed over
for the next one: the pool raises UnaskedWorker naming it, and the step that needed it fails or
waits with that cause (#589).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from taktus.ports.worker import ResolvedWorker, UnaskedWorker, Worker, WorkerError
from taktus.shared.v1 import Capability


class StaticWorkerPool:
    def __init__(
        self,
        workers: Sequence[tuple[str, Worker]],
        *,
        hosts: Mapping[str, tuple[str, ...]] | None = None,
        environment: Mapping[str, tuple[str, ...]] | None = None,
        connected: frozenset[str] = frozenset(),
    ) -> None:
        self._workers = list(workers)
        self._declared: dict[str, tuple[frozenset[str], str | None]] = {}
        self._hosts = dict(hosts or {})
        self._environment = dict(environment or {})
        self._connected = connected

    def hosts(self, adapter: str) -> tuple[str, ...]:
        """The hosts the configuration lets one worker's own service reach, beyond a step's
        frame (ADR-0089); empty when it names none."""
        return self._hosts.get(adapter, ())

    def environment(self, adapter: str) -> tuple[str, ...]:
        """The names of the variables the configuration gives one worker's unit (ADR-0090);
        empty when it names none."""
        return self._environment.get(adapter, ())

    def outbound(self, adapter: str) -> bool:
        """Whether the worker connects outbound and is reached over the binding (ADR-0156)."""
        return adapter in self._connected

    async def resolve(self, required: Sequence[Capability]) -> ResolvedWorker | None:
        needed = set(required)
        for adapter, worker in self._workers:
            if adapter not in self._declared:
                try:
                    declared = await worker.capabilities()
                except WorkerError as error:
                    raise UnaskedWorker(adapter, error) from error
                self._declared[adapter] = (frozenset(declared.capabilities), declared.version)
            capabilities, version = self._declared[adapter]
            if needed <= capabilities:
                return ResolvedWorker(adapter=adapter, worker=worker, version=version)
        return None

    def identifiers(self) -> list[str]:
        """The identifier of every configured member, in order, without reading a declaration."""
        return [adapter for adapter, _ in self._workers]

    async def members(self) -> list[tuple[str, frozenset[str], str | None]]:
        """Every configured worker with the capabilities and the version it declares — what
        the removal test reads to know what is configured, and records its verdict under."""
        found = []
        for adapter, worker in self._workers:
            if adapter not in self._declared:
                declared = await worker.capabilities()
                self._declared[adapter] = (frozenset(declared.capabilities), declared.version)
            capabilities, version = self._declared[adapter]
            found.append((adapter, capabilities, version))
        return found

    async def member(self, adapter: str) -> tuple[frozenset[str], str | None] | None:
        """The capabilities and the version one configured worker declares, read as `resolve`
        reads them; None when no worker has the identifier."""
        for configured, worker in self._workers:
            if configured != adapter:
                continue
            if adapter not in self._declared:
                declared = await worker.capabilities()
                self._declared[adapter] = (frozenset(declared.capabilities), declared.version)
            return self._declared[adapter]
        return None

    def without(self, adapter: str) -> StaticWorkerPool:
        """The same configuration with one worker withheld: what the removal test runs a
        process against. The original is untouched; restoring is not using this one."""
        pool = StaticWorkerPool(
            [(a, w) for a, w in self._workers if a != adapter],
            hosts={a: h for a, h in self._hosts.items() if a != adapter},
            environment={a: e for a, e in self._environment.items() if a != adapter},
            connected=self._connected - {adapter},
        )
        pool._declared = {a: d for a, d in self._declared.items() if a != adapter}
        return pool

    def first(self, adapter: str) -> StaticWorkerPool:
        """The same configuration with one worker moved to the front: what the removal test
        runs its baseline against, so that a worker standing behind another one serves every
        step it can serve (ADR-0078). The original is untouched."""
        ordered = sorted(self._workers, key=lambda entry: entry[0] != adapter)
        pool = StaticWorkerPool(
            ordered, hosts=self._hosts, environment=self._environment, connected=self._connected
        )
        pool._declared = dict(self._declared)
        return pool
