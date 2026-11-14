"""Reports for a role, explanations of a step, and a person's own view, wired across the
components they read (ADR-0242, ADR-0243, ADR-0245).

The rules are `reporting`'s (`domain/service/reports.py`, `explaining.py`, `own.py`); this module
gathers what they read — decision requests, blocked work, escalations, a run with its version,
provenance and spend — and says a report or a line through the reporting port `Deliveries`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from taktus.components.accounting.application.service.spend import SpendHandler, SpendOfRun
from taktus.components.catalog.domain.model import AdapterMaturity, AgentCore
from taktus.components.decision.domain.model import Request
from taktus.components.governance.domain.model.domains import Domain
from taktus.components.governance.domain.model.incident import Incident
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.application.service.streams import ValueStreams
from taktus.components.process.domain.model import (
    Process,
    ProcessVersion,
    TakeoverTrial,
    ValueStream,
)
from taktus.components.process.domain.model.proposal import Proposal
from taktus.components.reporting.application.query import LevelQueries
from taktus.components.reporting.application.service import ChannelOf
from taktus.components.reporting.domain.model.live import Reader, RunRef
from taktus.components.reporting.domain.model.views import (
    OWNER,
    OwnView,
    ReportDefinition,
    ViewConfiguration,
)
from taktus.components.reporting.domain.service import (
    explaining,
    own,
    rendering,
    reports,
    visibility,
)
from taktus.components.reporting.domain.service import views as selection
from taktus.components.reporting.ports import Deliveries, Sent
from taktus.components.run.application.query.blocked_time import BlockedTime
from taktus.components.run.domain.model import Run
from taktus.components.value.application.query import ValueLedger
from taktus.components.value.application.service import Discoveries, ValueBases
from taktus.components.value.domain.model import DiscoveredProcess, ValueBasis
from taktus.composition.figures import FigureReads, Gathered
from taktus.composition.knowledge_value import KnowledgeComparison
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import ProvenanceStore, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

log = structlog.get_logger("taktus.reports")
TEMPLATES = Path(__file__).parent / "explanations"
"""The sentences of an explanation, per language: `en.json`, `de.json` (ADR-0243 §2)."""


def template(language: str) -> dict[str, str]:
    """The shipped template of the language; English where none is shipped."""
    path = TEMPLATES / f"{language}.json"
    if path.parent != TEMPLATES or not path.is_file():
        path = TEMPLATES / "en.json"
    loaded: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


SET = "report_definition.set"
DELIVERED = "report_definition.delivered"
LINE = "own_view.line_delivered"

type Visible = Callable[[Reader], Awaitable[frozenset[str]]]


class ReportBook:
    def __init__(
        self,
        *,
        definitions: Repository[ReportDefinition],
        figures: FigureReads,
        requests: Repository[Request],
        blocked: BlockedTime,
        ledger: Ledger,
        deliveries: Deliveries | None,
        identities: IdentityDirectory,
        work: UnitOfWork,
        clock: Clock,
        channels: ChannelOf | None = None,
    ) -> None:
        """`channels` gives the tenant's phrasebook a scheduled report is said in (ADR-0316
        §5); without it, or without a channel, its own lines are said."""
        self._channels = channels
        self._definitions = definitions
        self._figures = figures
        self._requests = requests
        self._blocked = blocked
        self._ledger = ledger
        self._deliveries = deliveries
        self._identities = identities
        self._work = work
        self._clock = clock

    async def put(
        self, tenant: Tenant, document: Mapping[str, Any], *, by: str
    ) -> ReportDefinition:
        """Store a definition. Raises `ValueError` where it has no reader or does not validate."""
        if not document.get("reader_role"):
            raise ValueError("a report needs a reader: the role that reads it")
        async with self._work.transaction(tenant):
            held = await self._definitions.get(tenant, str(document.get("id")))
        definition = ReportDefinition.model_validate(
            {
                **document,
                "tenant": tenant,
                "set_at": self._clock.now(),
                "last_slot": None if held is None else held.last_slot,
            }
        )
        async with self._work.transaction(tenant):
            await self._definitions.put(tenant, definition)
            await self._ledger.record(
                tenant,
                Fact(kind=SET, refs=LedgerRefs(tenant=tenant, actor=by), outcome="set"),
            )
        return definition

    async def every(self, tenant: Tenant) -> list[ReportDefinition]:
        async with self._work.transaction(tenant):
            return sorted(await self._definitions.list(tenant), key=lambda d: d.id)

    async def get(self, tenant: Tenant, id: str) -> ReportDefinition | None:
        async with self._work.transaction(tenant):
            return await self._definitions.get(tenant, id)

    async def compose(
        self,
        definition: ReportDefinition,
        visible: frozenset[str],
        *,
        since: datetime | None = None,
    ) -> reports.Composed:
        """The report for its reader role over its period: what bears on that role only."""
        tenant = definition.tenant
        now = self._clock.now()
        start = reports.period(definition, now, since)
        role = definition.reader_role
        reader = Reader(tenant=tenant, identity=f"report:{definition.id}", roles=(role,))
        gathered = await self._figures.gather(reader, visible, max(1, (now - start).days or 1))
        configuration = await self._figures.configuration(tenant)
        entitled = {f.id for f in selection.exported((role,), configuration, gathered.shown, {})}
        missed = tuple(
            reports.Item(kind="figure", ref=p.figure or p.kind, text=p.text)
            for p in gathered.proposals
            if p.kind == "target" and p.figure in entitled
        )
        switch_off = tuple(
            reports.Item(kind="switch_off", ref=p.process or "process", text=p.text)
            for p in gathered.proposals
            if p.kind == "switch_off"
        )
        involved = frozenset(
            p.process
            for p in gathered.facts.processes
            if role == OWNER or role == p.owner_role or role in p.roles
        )
        async with self._work.transaction(tenant):
            requests = [r for r in await self._requests.list(tenant) if r.open]
            escalated = await self._ledger.of_kinds(tenant, {"run.escalated"}, since=start)
        waiting = await self._blocked.waiting(tenant)
        facts = reports.ReportFacts(
            reader=role,
            since=start,
            until=now,
            missed=missed,
            decisions=tuple(sorted(r.id for r in requests if r.decider == role)),
            escalated=tuple(
                (e.refs.run_id, e.refs.process_version.rsplit("@", 1)[0])
                for e in escalated
                if e.refs.run_id
                and e.refs.process_version
                and e.refs.process_version.rsplit("@", 1)[0] in involved
                and not e.rehearsal
            ),
            blocked=tuple(
                (w.run_id, w.process_version.rsplit("@", 1)[0], w.step_id)
                for w in waiting
                if str(w.account) == "wait.human"
                and (w.role or "owner") == role
                and w.process_version.rsplit("@", 1)[0] in visible
            ),
            switch_off=switch_off,
        )
        return reports.compose(definition, facts)

    async def tick(self, tenant: Tenant, visible: frozenset[str]) -> list[str]:
        """Say every due scheduled report once per slot. A slot is stored only once the channel
        accepted the report, so a restart repeats nothing and loses nothing."""
        said: list[str] = []
        if self._deliveries is None:
            return said
        now = self._clock.now()
        for definition in await self.every(tenant):
            slot = reports.due(definition, now)
            if slot is None:
                continue
            composed = await self.compose(definition, visible)
            channel = None if self._channels is None else await self._channels.of(tenant)
            text = (
                None
                if channel is None
                else rendering.role_message(composed, definition.reader_role, channel)
            )
            answer = await self._deliveries.say(
                tenant,
                definition.channel,
                definition.address,
                "\n".join(composed.lines) if text is None else text,
                key=f"report:{definition.id}:{slot}",
            )
            if not isinstance(answer, Sent):
                log.warning("a report was not delivered", report=definition.id, reason=answer)
                continue
            async with self._work.transaction(tenant):
                await self._definitions.put(
                    tenant, definition.model_copy(update={"last_slot": slot})
                )
                await self._ledger.record(
                    tenant,
                    Fact(kind=DELIVERED, refs=LedgerRefs(tenant=tenant), outcome="delivered"),
                )
            said.append(definition.id)
        return said


class Explanations:
    def __init__(
        self,
        *,
        runs: Repository[Run],
        versions: Repository[ProcessVersion],
        provenance: ProvenanceStore,
        spend: SpendHandler,
        figures: FigureReads,
        work: UnitOfWork,
    ) -> None:
        self._runs = runs
        self._versions = versions
        self._provenance = provenance
        self._spend = spend
        self._figures = figures
        self._work = work

    async def step(
        self, reader: Reader, run_id: str, step_id: str
    ) -> explaining.Explanation | None:
        """None where the run or the step does not exist or the reader may not see it."""
        async with self._work.transaction(reader.tenant):
            run = await self._runs.get(reader.tenant, run_id)
            version = (
                None
                if run is None
                else await self._versions.get(reader.tenant, run.process_version)
            )
        if run is None or version is None:
            return None
        ref = RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        if not visibility.may_see(reader, ref):
            return None
        step = next((s for s in version.steps if s.id == step_id), None)
        tried = [r for r in run.step_runs if r.step_id == step_id]
        if step is None or not tried:
            return None
        async with self._work.transaction(reader.tenant):
            records = [
                p
                for p in await self._provenance.of_run(reader.tenant, run_id)
                if p.step_id == step_id
            ]
        spent = await self._spend.of_run(SpendOfRun(run_id, reader.tenant))
        cost = next((s for s in spent.steps if s.step_id == step_id), None)
        record = records[-1] if records else None
        last = tried[-1]
        facts = explaining.StepFacts(
            run_id=run.id,
            process_version=run.process_version,
            step_id=step_id,
            method=step.method.value,
            reason=step.reason,
            rejected=tuple(
                explaining.Alternative(method=r.method.value, why=r.why) for r in step.rejected
            ),
            fallback=None
            if step.fallback is None
            else f"{step.fallback.to.value} when {step.fallback.when}",
            exactness=None if step.exactness is None else step.exactness.value,
            state=last.state.value,
            outcome=None if cost is None else cost.outcome,
            money=None if cost is None else cost.amount,
            currency=spent.currency,
            takte=None if cost is None else cost.takte,
            inputs=()
            if record is None
            else tuple(
                explaining.Input(
                    kind=str(i.kind),
                    ref=i.artifact_id or i.ref or i.step_id or str(i.capability or i.kind),
                    read_at=i.observed_at.isoformat(),
                )
                for i in record.inputs
            ),
            result=None if record is None else record.result_digest,
        )
        configuration = await self._figures.configuration(reader.tenant)
        return explaining.explain(
            facts,
            selection.depth(reader.roles, configuration),
            template(selection.language(reader.roles, configuration)),
        )

    async def summary(self, reader: Reader, visible: frozenset[str], days: int) -> dict[str, Any]:
        """What Taktus did in a period, per process, with the figures every view uses."""
        gathered = await self._figures.gather(reader, visible, days)
        configuration = await self._figures.configuration(reader.tenant)
        allowed = selection.exported(reader.roles, configuration, gathered.shown, gathered.holders)
        wanted = ("value.runs_ended", "value.quality", "value.escalation_rate", "value.cost_money")
        per: dict[str, dict[str, Any]] = {}
        for f in allowed:
            if f.scope == "process" and f.id in wanted:
                per.setdefault(f.subject, {})[f.id] = f.document()
        lines = []
        for process, held in sorted(per.items()):
            parts = []
            for id in wanted:
                figure = held.get(id)
                if figure is None or figure["value"] is None:
                    continue
                parts.append(f"{id.removeprefix('value.')} {figure['value']:g}")
            lines.append(f"{process}: " + (", ".join(parts) if parts else "no run ended"))
        return {
            "since": gathered.facts.since.isoformat(),
            "until": gathered.facts.until.isoformat(),
            "processes": per,
            "lines": lines,
        }


class OwnViews:
    def __init__(
        self,
        *,
        settings: Repository[OwnView],
        figures: FigureReads,
        identities: IdentityDirectory,
        deliveries: Deliveries | None,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._settings = settings
        self._figures = figures
        self._identities = identities
        self._deliveries = deliveries
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def settings(self, tenant: Tenant, reader: str) -> OwnView | None:
        async with self._work.transaction(tenant):
            return await self._settings.get(tenant, reader)

    async def set(self, tenant: Tenant, reader: str, document: Mapping[str, Any]) -> OwnView:
        held = await self.settings(tenant, reader)
        kept = {} if held is None else held.model_dump(mode="json")
        view = OwnView.model_validate(
            {
                **kept,
                **{k: v for k, v in document.items() if k not in ("id", "tenant", "reader")},
                "id": reader,
                "tenant": tenant,
                "reader": reader,
                "set_at": self._clock.now(),
                "last_slot": None if held is None else held.last_slot,
            }
        )
        async with self._work.transaction(tenant):
            await self._settings.put(tenant, view)
        return view

    async def relief(self, reader: Reader, visible: frozenset[str], days: int) -> own.OwnRelief:
        gathered = await self._figures.gather(reader, visible, days)
        week = await self._figures.gather(reader, visible, 7)
        return own.relief(
            reader.identity,
            reader.roles,
            gathered.facts.since,
            gathered.facts.until,
            _relieving(gathered, week),
            await self.settings(reader.tenant, reader.identity),
        )

    async def tick(self, tenant: Tenant, visible: frozenset[str]) -> list[str]:
        """Say every person's line that is due, once per slot."""
        said: list[str] = []
        if self._deliveries is None:
            return said
        now = self._clock.now()
        async with self._work.transaction(tenant):
            every = await self._settings.list(tenant)
        for view in every:
            slot = own.line_due(view, now)
            if slot is None or view.channel is None or view.address is None:
                continue
            who = await self._identities.identity(tenant, view.reader)
            if who is None:
                continue
            reader = Reader(tenant=tenant, identity=view.reader, roles=who.roles)
            answer = await self._deliveries.say(
                tenant,
                view.channel,
                view.address,
                own.line(await self.relief(reader, visible, 7)),
                key=f"own:{view.reader}:{slot}",
            )
            if not isinstance(answer, Sent):
                continue
            async with self._work.transaction(tenant):
                await self._settings.put(tenant, view.model_copy(update={"last_slot": slot}))
                await self._ledger.record(
                    tenant, Fact(kind=LINE, refs=LedgerRefs(tenant=tenant), outcome="delivered")
                )
            said.append(view.reader)
        return said


def _relieving(gathered: Gathered, week: Gathered) -> list[own.Relieving]:
    def figure(of: Gathered, id: str, process: str) -> float | None:
        found = next(
            (f for f in of.shown if f.id == id and f.scope == "process" and f.subject == process),
            None,
        )
        return None if found is None else found.value

    out = []
    for p in gathered.facts.processes:
        stated = gathered.facts.basis.of(p.process) if gathered.facts.basis else None
        by_hand = () if stated is None else stated.roles_by_hand
        runs = next(
            (
                f.basis.get("runs_finished", 0)
                for f in gathered.shown
                if f.id == "value.runs_ended" and f.subject == p.process
            ),
            0,
        )
        out.append(
            own.Relieving(
                process=p.process,
                roles=tuple(sorted({*p.roles, *by_hand})),
                runs_finished=int(runs),
                minutes_by_hand=None if stated is None else stated.minutes_by_hand,
                hours=figure(gathered, "value.time_saved_hours", p.process),
                week_hours=figure(week, "value.time_saved_hours", p.process),
                takeover=f"processes/{p.process}/takeover",
            )
        )
    return out


@dataclass(frozen=True)
class ReadingWiring:
    """Views, the export, reports, explanations, the value ledger and a person's own view,
    built once (ADR-0241 to ADR-0245)."""

    figures: FigureReads
    reports: ReportBook
    explanations: Explanations
    own: OwnViews
    bases: ValueBases
    discoveries: Discoveries
    knowledge: KnowledgeComparison


def reading_wiring(
    of: Callable[[Any], Any],
    *,
    ledger: Ledger,
    provenance: ProvenanceStore,
    spend: SpendHandler,
    blocked: BlockedTime,
    identities: IdentityDirectory,
    levels: LevelQueries,
    deliveries: Deliveries | None,
    work: UnitOfWork,
    clock: Clock,
    identifiers: Identifiers,
    channels: ChannelOf | None = None,
) -> ReadingWiring:
    """`of` gives the repository of an aggregate, as the entry point stores it."""
    bases = ValueBases(of(ValueBasis), ledger, work, clock)
    figures = FigureReads(
        processes=of(Process),
        versions=of(ProcessVersion),
        streams=ValueStreams(of(ValueStream), of(Process), work, ledger, clock),
        identities=identities,
        spend=spend,
        trials=of(TakeoverTrial),
        maturities=of(AdapterMaturity),
        proposals=of(Proposal),
        discovered=of(DiscoveredProcess),
        configurations=of(ViewConfiguration),
        value_ledger=ValueLedger(ledger, work),
        bases=bases,
        levels=levels,
        ledger=ledger,
        work=work,
        clock=clock,
        domains=of(Domain),
        agents=of(AgentCore),
        runs=of(Run),
        incidents=of(Incident),
    )
    return ReadingWiring(
        figures=figures,
        reports=ReportBook(
            definitions=of(ReportDefinition),
            figures=figures,
            requests=of(Request),
            blocked=blocked,
            ledger=ledger,
            deliveries=deliveries,
            identities=identities,
            work=work,
            clock=clock,
            channels=channels,
        ),
        explanations=Explanations(
            runs=of(Run),
            versions=of(ProcessVersion),
            provenance=provenance,
            spend=spend,
            figures=figures,
            work=work,
        ),
        own=OwnViews(
            settings=of(OwnView),
            figures=figures,
            identities=identities,
            deliveries=deliveries,
            ledger=ledger,
            work=work,
            clock=clock,
        ),
        bases=bases,
        discoveries=Discoveries(of(DiscoveredProcess), ledger, work, clock, identifiers),
        knowledge=KnowledgeComparison(
            versions=of(ProcessVersion),
            ledger=ledger,
            spend=spend,
            bases=bases,
            work=work,
            clock=clock,
        ),
    )


def reading_tick(
    reading: ReadingWiring, tenants: Callable[[], Awaitable[Sequence[Tenant]]]
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant's due reports and lines are said
    once per slot. A failure is logged and tried again at the next tick."""

    async def tick() -> None:
        for tenant in await tenants():
            try:
                visible = frozenset(p.id for p in await reading.figures.every_process(tenant))
                said = await reading.reports.tick(tenant, visible)
                lines = await reading.own.tick(tenant, visible)
            except Exception as error:  # a report must never take the scheduler down
                log.error(
                    "reports not said; the next tick tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            if said or lines:
                log.info("reports said", tenant=tenant, reports=said, lines=len(lines))

    return tick
