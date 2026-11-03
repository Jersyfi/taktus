"""What acts for a tenant, what depends on it, and how a process really runs (ADR-0147).

The facts come from five components that never import each other: the catalog's maturity and
removal verdicts, the process versions, the governance component's residency rule, the run's
stops, blocks and provenance, and the identity component's roles. This module gathers them and
hands them to the reporting component's views, which draw and store nothing. Which adapter
serves a step is read from the pools as they are configured now (`Pools.serving`), and what a
step comes to without it by the removal test's own rule (`removal.step_finding`).

Every read takes `visible`, the processes the reader may see (ADR-0055 §5): a process outside
it is left out of every row and every count.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.catalog.domain.service import removal
from taktus.components.governance.application.service import TenantResidency
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model.acting import (
    ActorFacts,
    ActorUse,
    Register,
    RemovalSeen,
    RemoveView,
    ResidencyView,
    WrongResultView,
)
from taktus.components.reporting.domain.service import acting
from taktus.components.reporting.domain.service import variants as variant_views
from taktus.components.run.application.query.blocked_time import BlockedTime
from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import Run, RunError, parse_work
from taktus.composition.maturity import InstanceCatalogue
from taktus.composition.pools import Pools
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import ProvenanceStore, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import EGRESS_KINDS

FAMILIES = ("worker", "connector", "model")


@dataclass(frozen=True)
class _Served:
    """One step of an active version, the adapter that serves it now, and the one without it."""

    version: ProcessVersion
    step: Any
    served: str
    adapter: str


class ActingReads:
    def __init__(
        self,
        *,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        maturities: Repository[AdapterMaturity],
        runs: Repository[Run],
        catalogue: InstanceCatalogue,
        pools: Pools,
        residency: TenantResidency,
        stops: Stops,
        blocked: BlockedTime,
        identities: IdentityDirectory,
        provenance: ProvenanceStore,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._maturities = maturities
        self._runs = runs
        self._catalogue = catalogue
        self._pools = pools
        self._residency = residency
        self._stops = stops
        self._blocked = blocked
        self._identities = identities
        self._provenance = provenance
        self._ledger = ledger
        self._work = work
        self._clock = clock

    # --- the register (ADR-0147 §2) ----------------------------------------------------------

    async def register(self, tenant: Tenant, visible: frozenset[str]) -> Register:
        facts = await self._facts(tenant, visible)
        permitted = (await self._residency.rule(tenant)).location
        return acting.register(tenant, facts, permitted)

    async def inventory(self, tenant: Tenant, visible: frozenset[str]) -> dict[str, Any]:
        return acting.inventory(await self.register(tenant, visible), self._clock.now())

    async def stop(self, tenant: Tenant, adapter: str, actor: str) -> Any:
        """ADR-0138's stop of the adapter, requested by the person: its rule decides which
        runs halt, at their boundary, and records it."""
        return await self._stops.request(tenant, adapter, actor)

    # --- dependencies (ADR-0147 §3) ----------------------------------------------------------

    async def remove(self, tenant: Tenant, adapter: str, visible: frozenset[str]) -> RemoveView:
        facts = {f.adapter: f for f in await self._facts(tenant, visible)}
        return acting.remove_view(adapter, facts.get(adapter))

    async def residency(self, tenant: Tenant, visible: frozenset[str]) -> ResidencyView:
        facts = await self._facts(tenant, visible)
        permitted = (await self._residency.rule(tenant)).location
        return acting.residency_view(facts, permitted)

    async def wrong_result(
        self, tenant: Tenant, run_id: str, step_id: str, visible: frozenset[str]
    ) -> WrongResultView | None:
        """None where the run does not exist or is one the reader may not see."""
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
            if run is None or run.process_version.split("@", 1)[0] not in visible:
                return None
            own = next(
                (p for p in await self._provenance.of_run(tenant, run_id) if p.step_id == step_id),
                None,
            )
            reached = [
                p
                for p in await self._provenance.derived(tenant, run_id, step_id)
                if p.process_version.split("@", 1)[0] in visible
            ]
            touched = {run_id, *(p.run_id for p in reached)}
            egress = [
                e
                for r in sorted(touched)
                for e in await self._ledger.entries(tenant, r)
                if e.kind in EGRESS_KINDS
            ]
        return acting.wrong_result(run_id, step_id, own, reached, egress)

    # --- how a process really runs (ADR-0147 §4) ---------------------------------------------

    async def variants(self, tenant: Tenant, process_id: str) -> variant_views.VariantsView | None:
        """None where the process does not exist."""
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            if process is None:
                return None
            version = (
                None
                if process.active_version is None
                else await self._versions.get(tenant, f"{process_id}@{process.active_version}")
            )
            travelled = await self._ledger.project(tenant, variant_views.VARIANTS)
        blocks = [b for b in await self._blocked.blocks(tenant) if b.process == process_id]
        waits = [
            variant_views.WaitFact(
                step_id=b.step_id,
                account=str(b.account),
                cause=b.cause,
                seconds=b.seconds,
                role=b.role,
            )
            for b in blocks
        ]
        steps = () if version is None else version.ordered()
        performers = {s.id: r for s in steps if (r := s.performer) is not None}
        return variant_views.variants(
            process_id,
            None if version is None else version.version,
            [s.id for s in steps],
            travelled,
            waits,
            await self._identities.role_holders(tenant),
            performers,
        )

    # --- the facts ---------------------------------------------------------------------------

    async def _facts(self, tenant: Tenant, visible: frozenset[str]) -> list[ActorFacts]:
        entries = await self._catalogue.entries(tenant)
        served = await self._served(tenant, visible)
        held = await self._stops.held(tenant)
        async with self._work.transaction(tenant):
            used = await self._ledger.project(tenant, acting.USED)
            records = {m.id: m for m in await self._maturities.list(tenant)}
        since = (self._clock.now() - timedelta(days=acting.PERIOD_DAYS)).date()
        facts: list[ActorFacts] = []
        for entry in entries:
            if entry.family not in FAMILIES:
                continue
            uses = [await self._use(s) for s in served if s.adapter == entry.adapter]
            record = records.get(entry.adapter)
            found = None if record is None else record.removal
            facts.append(
                ActorFacts(
                    adapter=entry.adapter,
                    family=entry.family,  # type: ignore[arg-type]
                    serves=entry.serves,
                    maturity=entry.maturity,
                    missing=entry.missing,
                    removal=None
                    if found is None
                    else RemovalSeen(
                        verdict=found.verdict.value,
                        tested_at=found.tested_at,
                        reason=found.reason,
                    ),
                    location=self._pools.models.location(entry.adapter)
                    if entry.family == "model"
                    else None,
                    uses=tuple(uses),
                    used=used.used(entry.adapter, since),
                    stopped=entry.adapter in held,
                )
            )
        return facts

    async def _served(self, tenant: Tenant, visible: frozenset[str]) -> list[_Served]:
        """Every step of every active version the reader may see, with the adapter that serves
        it now. A step whose work cannot be read is left out, as the removal test leaves it."""
        async with self._work.transaction(tenant):
            processes = await self._processes.list(tenant)
            versions = [
                v
                for p in processes
                if p.active_version is not None and p.id in visible
                if (v := await self._versions.get(tenant, f"{p.id}@{p.active_version}")) is not None
            ]
        found: list[_Served] = []
        for version in sorted(versions, key=lambda v: v.ref):
            examples = {name: given.example for name, given in version.inputs.items()}
            for step in version.ordered():
                try:
                    work = parse_work(step, version.work.get(step.id), examples)
                except RunError:
                    continue
                serving = await self._pools.serving(step, work)
                if serving is None or serving[1] is None:
                    continue
                found.append(_Served(version, step, serving[0], serving[1]))
        return found

    async def _use(self, served: _Served) -> ActorUse:
        version, step = served.version, served.step
        examples = {name: given.example for name, given in version.inputs.items()}
        work = parse_work(step, version.work.get(step.id), examples)
        alternative = await self._pools.without(served.adapter).serving(step, work)
        instead = None if alternative is None else alternative[1]
        finding = removal.step_finding(step, served.served, instead)
        return ActorUse(
            process_id=version.process_id,
            version=version.version,
            step_id=step.id,
            served=served.served,
            level=version.autonomy.level,
            exactness=step.exactness,
            without="breaks" if finding.verdict.value == "broke" else "degrades",
            instead=instead,
            role=step.performer,
            reason=finding.reason,
        )
