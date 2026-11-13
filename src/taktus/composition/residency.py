"""Registration's port `ResidencyBindings`, answered from the pools and the tenant's rule
(ADR-0281 §4, UC-11.1).

The process component registers a version; the governance component keeps the residency rule;
the pools know where each configured adapter is. None of them imports another. This module reads
each step's work as the run would, asks the rule for the step's data class in the version's
process, and names every step that only an adapter or a host outside the permitted location
would serve.
"""

from __future__ import annotations

from collections.abc import Mapping

from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.domain.model import (
    ConnectorRule,
    LlmWork,
    RunError,
    WaitWork,
    WorkerWork,
    parse_work,
)
from taktus.components.run.ports.residency import Residency
from taktus.composition.pools import Pools
from taktus.ports.model import Location, Permitted, admits, host_location
from taktus.ports.persistence import Tenant
from taktus.ports.worker import UnaskedWorker
from taktus.shared.v1 import Step


class PoolBindings:
    """Which steps of a version would be bound outside the tenant's residency rule."""

    def __init__(
        self, pools: Pools, residency: Residency, host_locations: Mapping[str, Location]
    ) -> None:
        self._pools = pools
        self._residency = residency
        self._hosts = dict(host_locations)

    async def outside(self, tenant: Tenant, version: ProcessVersion) -> list[str]:
        examples = {name: given.example for name, given in version.inputs.items()}
        findings: list[str] = []
        for step in version.ordered():
            try:
                work = parse_work(step, version.work.get(step.id), examples)
            except RunError:
                continue  # a work that cannot be read is refused by the run, not here
            data_class = getattr(work, "data_class", None)
            permitted = await self._residency.permitted(tenant, data_class, version.process_id)
            if permitted == "anywhere":
                continue
            handled = f"data of class {data_class!r}" if data_class else "data of no declared class"
            for what, location in await self._bound(step, work, permitted):
                findings.append(
                    f"step {step.id!r} handles {handled}, and {what} is at {location}, outside "
                    f"the location the residency rule permits ({permitted}) (ADR-0281 §4)"
                )
        return findings

    async def _bound(self, step: Step, work: object, permitted: Permitted) -> list[tuple[str, str]]:
        """What the step would be bound to outside `permitted`: (what, its location)."""
        if isinstance(work, LlmWork):
            chain = await self._pools.models.chain(work.purpose)
            if chain and not any(admits(permitted, m.location) for m in chain):
                return [(f"the model {chain[0].adapter}", chain[0].location)]
            return []
        if isinstance(work, ConnectorRule):
            return await self._connector(work.capability, permitted, work.connector)
        if isinstance(work, WaitWork) and work.until is not None:
            return await self._connector(work.until.capability, permitted)
        if isinstance(work, WorkerWork):
            return await self._worker(step, work, permitted)
        return []

    async def _connector(
        self, capability: str, permitted: Permitted, named: str | None = None
    ) -> list[tuple[str, str]]:
        connectors = self._pools.connectors
        resolved = (
            await connectors.resolve(capability)
            if named is None
            else await connectors.named(named, capability)
        )
        if resolved is None or admits(permitted, resolved.location):
            return []
        return [(f"the connector {resolved.adapter}", resolved.location)]

    async def _worker(
        self, step: Step, work: WorkerWork, permitted: Permitted
    ) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        hosts: tuple[str, ...] = work.allowed_hosts
        try:
            chosen = await self._pools.workers.resolve(step.required_capabilities, permitted)
            if chosen is None:
                beyond = await self._pools.workers.resolve(step.required_capabilities)
                if beyond is not None:
                    found.append((f"the worker {beyond.adapter}", beyond.location))
            else:
                hosts = (*hosts, *chosen.hosts)
        except UnaskedWorker:
            pass  # a worker that cannot be asked now is held by the run when it is assigned
        for host in dict.fromkeys(hosts):
            location = host_location(self._hosts, host)
            if not admits(permitted, location):
                found.append((f"the host {host}", location))
        return found
