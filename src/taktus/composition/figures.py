"""The figures of every owner, gathered once per read for the views, the export, the reports and
a person's own view (ADR-0241 §1, ADR-0244).

The facts come from components that never import each other: the process component's active
versions, value streams, takeover trials and proposals; the catalog's removal verdicts; the
identity component's structure; accounting's spend; the value component's ledger and stated
basis; and the overview level's counts. The value component computes its figures from them;
`reporting` selects among them. Only the processes the reader may see are gathered: a process
outside `visible` contributes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from taktus.components.accounting.application.service.spend import SpendHandler, SpendOfProcess
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.application.service.streams import ValueStreams
from taktus.components.process.domain.model import Process, ProcessVersion, TakeoverTrial
from taktus.components.process.domain.model.proposal import OPEN, Proposal
from taktus.components.reporting.application.query import LevelQueries
from taktus.components.reporting.domain.model.live import Reader
from taktus.components.reporting.domain.model.signal import Corridor, Judged
from taktus.components.reporting.domain.model.views import Shown, ViewConfiguration
from taktus.components.reporting.domain.service import views as selection
from taktus.components.reporting.domain.service import warehouse
from taktus.components.value.application.query import ValueLedger
from taktus.components.value.application.service import ValueBases
from taktus.components.value.domain.model import DiscoveredProcess, Figure, ValueProposal
from taktus.components.value.domain.service import figures as value
from taktus.components.value.domain.service.proposals import proposals as proposed
from taktus.ports.clock import Clock
from taktus.ports.connector import QUERYING
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs, Method

CONFIGURED = "views.configured"
QUERY_SENT = "query.sent"
"""The ledger's record of a query sent to the warehouse, by reference (ADR-0262 §3)."""
RUN_FIGURES = {
    "run.working": "runs of the process working now, by the run component's definition WORKING",
    "run.waiting": "runs of the process waiting now, by the run component's definition WAITING",
}
KNOWN = frozenset({*value.DEFINITIONS, *RUN_FIGURES, warehouse.FIGURE})
"""Every figure an owner hands in: what a view may name."""


@dataclass(frozen=True)
class Gathered:
    shown: list[Shown]
    index: value.Index
    proposals: list[ValueProposal]
    backlog: list[dict[str, Any]]
    facts: value.Facts
    holders: Mapping[str, int]


def shown(figure: Figure) -> Shown:
    return Shown.model_validate(figure.model_dump())


class WarehouseFigures:
    """The warehouse figures among the signals judged now: each signal whose step queries the
    warehouse, with the query by reference (UC-5.6 §2, ADR-0291 §3)."""

    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        ledger: Ledger,
        work: UnitOfWork,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._ledger = ledger
        self._work = work

    async def shown(
        self,
        reader: Reader,
        visible: frozenset[str],
        judged: Sequence[tuple[Corridor, Judged]],
    ) -> list[Shown]:
        """The warehouse figures among the signals judged now: each signal whose step queries
        the warehouse, with the query by reference (UC-5.6 §2, ADR-0291 §3). A process outside
        `visible` contributes nothing."""
        tenant = reader.tenant
        out: list[Shown] = []
        for corridor, one in judged:
            if corridor.tenant != tenant or corridor.process not in visible:
                continue
            async with self._work.transaction(tenant):
                ref = one.process_version
                if ref is None:
                    process = await self._processes.get(tenant, corridor.process)
                    held = None if process is None else process.active_version
                    ref = None if held is None else f"{corridor.process}@{held}"
                version = None if ref is None else await self._versions.get(tenant, ref)
                entries = (
                    [] if one.run_id is None else await self._ledger.entries(tenant, one.run_id)
                )
            step = None if version is None else version.work.get(corridor.step)
            if not isinstance(step, Mapping) or step.get("rule") != "connector":
                continue
            operation = str(step.get("operation", ""))
            if operation.rsplit(".", 1)[0] not in QUERYING:
                continue
            given = step.get("input")
            sent = [
                e
                for e in entries
                if e.kind == QUERY_SENT and e.refs.step_id == corridor.step and e.content_digest
            ]
            newest = sent[-1] if sent else None
            out.append(
                warehouse.figure(
                    corridor,
                    one,
                    warehouse.Reading(
                        operation=operation,
                        fixed=isinstance(given, Mapping) and isinstance(given.get("query"), str),
                        seq=None if newest is None else newest.seq,
                        digest=None if newest is None else newest.content_digest,
                        sent_at=None if newest is None else newest.ts,
                    ),
                )
            )
        return out


class FigureReads:
    def __init__(
        self,
        *,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        streams: ValueStreams,
        identities: IdentityDirectory,
        spend: SpendHandler,
        trials: Repository[TakeoverTrial],
        maturities: Repository[AdapterMaturity],
        proposals: Repository[Proposal],
        discovered: Repository[DiscoveredProcess],
        configurations: Repository[ViewConfiguration],
        value_ledger: ValueLedger,
        bases: ValueBases,
        levels: LevelQueries,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._streams = streams
        self._identities = identities
        self._spend = spend
        self._trials = trials
        self._maturities = maturities
        self._proposals = proposals
        self._discovered = discovered
        self._configurations = configurations
        self._value = value_ledger
        self._bases = bases
        self.levels = levels
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._warehouse = WarehouseFigures(processes, versions, ledger, work)

    # --- the view configuration (ADR-0241 §2) ------------------------------------------------

    async def configuration(self, tenant: Tenant) -> ViewConfiguration:
        async with self._work.transaction(tenant):
            held = await self._configurations.get(tenant, tenant)
        return held or selection.default(tenant, KNOWN, self._clock.now())

    async def configure(
        self, tenant: Tenant, document: Mapping[str, Any], *, by: str
    ) -> ViewConfiguration:
        """Store the tenant's configuration. Raises `ValueError` with the findings where it
        does not validate or names a figure no owner computes; nothing is stored then."""
        configuration = ViewConfiguration.model_validate(
            {**document, "id": tenant, "tenant": tenant, "configured_at": self._clock.now()}
        )
        findings = selection.refused(configuration, KNOWN)
        if findings:
            raise ValueError("; ".join(findings))
        async with self._work.transaction(tenant):
            await self._configurations.put(tenant, configuration)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=tenant, actor=by),
                    outcome="configured",
                    content_digest=_digest(configuration.document()),
                ),
            )
        return configuration

    async def every_process(self, tenant: Tenant) -> list[Process]:
        """The tenant's processes: what a report for a role sees, inside the tenant boundary
        the one predicate holds (ADR-0055 §5)."""
        async with self._work.transaction(tenant):
            return list(await self._processes.list(tenant))

    # --- the figures ------------------------------------------------------------------------

    async def gather(
        self, reader: Reader, visible: frozenset[str], days: int, *, until: datetime | None = None
    ) -> Gathered:
        tenant = reader.tenant
        end = until or self._clock.now()
        since = end - timedelta(days=days)
        stated = await self._bases.current(tenant)
        basis = None if stated is None else stated.basis
        facts = value.Facts(
            tenant=tenant,
            since=since,
            until=end,
            basis=basis,
            basis_set={}
            if stated is None
            else {
                "version": stated.basis.version,
                "set_at": stated.basis.set_at.isoformat(),
                "set_by": stated.set_by,
            },
            processes=tuple(
                await self._process_facts(
                    tenant, visible, since, end, None if basis is None else basis.currency
                )
            ),
            suppliers=tuple(await self._suppliers(tenant)),
            backlog=(),
        )
        activity = await self._value.activity(tenant)
        dependence = await self._value.dependence(tenant)
        per_process = value.process_figures(facts, activity)
        facts = facts.model_copy(update={"backlog": tuple(await self._backlog(tenant, facts))})
        index = value.bus_factor(facts, dependence)
        units, backlog = value.transformation(facts, activity, per_process)
        figures = [
            *per_process,
            *value.proof_of_value(facts, per_process),
            *index.figures,
            *units,
        ]
        out = [shown(f) for f in figures] + await self._run_figures(reader, visible)
        return Gathered(
            shown=out,
            index=index,
            proposals=proposed(facts, per_process, dependence),
            backlog=backlog,
            facts=facts,
            holders=await self._identities.role_holders(tenant),
        )

    async def warehouse(
        self,
        reader: Reader,
        visible: frozenset[str],
        judged: Sequence[tuple[Corridor, Judged]],
    ) -> list[Shown]:
        """The warehouse figures among the signals judged now (ADR-0291 §3)."""
        return await self._warehouse.shown(reader, visible, judged)

    async def _run_figures(self, reader: Reader, visible: frozenset[str]) -> list[Shown]:
        """The overview's own counts, read from the overview level itself (UC-6.10)."""
        level = await self.levels.overview(reader)
        out: list[Shown] = []
        for area in level.areas:
            for p in area.processes:
                if p.id not in visible:
                    continue
                for id, count in (("run.working", p.working), ("run.waiting", p.waiting)):
                    out.append(
                        Shown(
                            id=id,
                            component="run",
                            definition=RUN_FIGURES[id],
                            unit="runs",
                            scope="process",
                            subject=p.id,
                            value=count,
                            method="counted now, as the overview counts it",
                        )
                    )
        return out

    async def _process_facts(
        self,
        tenant: Tenant,
        visible: frozenset[str],
        since: datetime,
        until: datetime,
        currency: str | None,
    ) -> list[value.ProcessFacts]:
        async with self._work.transaction(tenant):
            processes = sorted(
                (p for p in await self._processes.list(tenant) if p.id in visible),
                key=lambda p: p.id,
            )
            versions = [
                v
                for p in processes
                if p.active_version is not None
                and (v := await self._versions.get(tenant, f"{p.id}@{p.active_version}"))
                is not None
            ]
            trials = await self._trials.list(tenant)
        streams = await self._streams.current(tenant)
        units = await self._identities.role_units(tenant)
        out = []
        for v in versions:
            steps = v.ordered()
            stream = next((s for s in streams if v.process_id in s.processes), None)
            tried = sorted((t for t in trials if t.process_version == v.ref), key=lambda t: t.at)
            spent = await self._spend.of_process(
                SpendOfProcess(v.process_id, tenant, since=since, until=until)
            )
            roles = {s.role for s in steps if s.role} | {
                s.fallback.role
                for s in steps
                if s.fallback is not None and s.fallback.to is Method.HUMAN and s.fallback.role
            }
            takte = [s.takte for s in spent.steps if s.takte is not None]
            out.append(
                value.ProcessFacts(
                    process=v.process_id,
                    version=v.ref,
                    level=v.autonomy.level,
                    methods=tuple(s.method.value for s in steps),
                    variable_steps=tuple(s.id for s in steps if s.method.value in value.VARIABLE),
                    roles=tuple(sorted(r for r in roles if r)),
                    instructions=v.takeover is not None,
                    owner_role=stream.role if stream is not None else "owner",
                    stream=None if stream is None else stream.stream,
                    unit=None
                    if stream is None or not units.get(stream.role)
                    else units[stream.role][0],
                    cost_money=spent.amounts.get(currency or "EUR"),
                    cost_takt=None if not takte else sum(takte),
                    trial_passed=None if not tried else tried[-1].passed,
                )
            )
        return out

    async def _suppliers(self, tenant: Tenant) -> list[value.SupplierFacts]:
        async with self._work.transaction(tenant):
            held = await self._maturities.list(tenant)
        out = []
        for m in sorted(held, key=lambda m: m.id):
            removal = m.removal
            if removal is None:
                out.append(value.SupplierFacts(integration=m.id))
                continue
            broke = {
                p.process: tuple(
                    s.step for s in p.steps if s.alternative is None and s.fallback is None
                )
                or tuple(s.step for s in p.steps)
                for p in removal.processes
                if p.verdict == "broke"
            }
            out.append(
                value.SupplierFacts(
                    integration=m.id,
                    verdict=str(removal.verdict),
                    current=removal.configuration is not None,
                    broke=broke,
                )
            )
        return out

    async def _backlog(self, tenant: Tenant, facts: value.Facts) -> list[value.BacklogSource]:
        async with self._work.transaction(tenant):
            proposals = [p for p in await self._proposals.list(tenant) if p.state in OPEN]
            discovered = [
                d
                for d in await self._discovered.list(tenant)
                if d.reader is None and d.stage != "automated"
            ]
        unit_of = {p.process: p.unit for p in facts.processes}
        out = []
        for p in proposals:
            stated = facts.basis.of(p.process_id) if facts.basis else None
            out.append(
                value.BacklogSource(
                    kind="proposal",
                    id=p.id,
                    unit=unit_of.get(p.process_id),
                    title=f"{p.process_id} version {p.version}",
                    hours_per_month=None,
                    basis=(
                        f"{stated.minutes_by_hand:g} minutes by hand per case, stated"
                        if stated is not None and stated.minutes_by_hand is not None
                        else "no expected benefit yet: state the minutes by hand per case"
                    ),
                )
            )
        for d in discovered:
            hours = (
                None
                if d.minutes_by_hand is None or d.cases_per_month is None
                else d.minutes_by_hand * d.cases_per_month / 60
            )
            out.append(
                value.BacklogSource(
                    kind="discovered",
                    id=d.id,
                    title=d.title,
                    hours_per_month=hours,
                    basis=(
                        f"{d.minutes_by_hand:g} minutes by hand, "
                        f"{d.cases_per_month:g} cases a month"
                        if hours is not None
                        else f"discovered, at the stage {d.stage}: not valued yet"
                    ),
                )
            )
        for b in facts.basis.backlog if facts.basis else ():
            out.append(
                value.BacklogSource(
                    kind="entered",
                    id=b.id,
                    unit=b.unit,
                    title=b.title,
                    hours_per_month=b.hours_per_month,
                    basis=b.basis,
                )
            )
        return out


def _digest(document: Mapping[str, Any]) -> str:
    import hashlib
    import json

    text = json.dumps(document, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def known() -> Sequence[str]:
    return sorted(KNOWN)
