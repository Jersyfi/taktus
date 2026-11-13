"""A tenant is introduced in stages, each opened by a person on a rule's evidence (UC-9.6,
ADR-0137).

The world is the governance component's `Stages` over a memory store and a hash-chained
ledger, the process component's registration asking it for the ceiling, and the composition
root's ports between them. What the processes did is written to the ledger as their runs would
write it; every figure the tests read is counted from there.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fakes import FakeClock
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.adapters.driving.cli.stage_command import blueprint_stages
from taktus.components.governance.application.service import Corrections, Stages, StagesRefused
from taktus.components.governance.domain.model import (
    CorrectionLimits,
    Incident,
    IncidentKind,
    StagePlan,
    StageState,
    StageView,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import Process, ProcessVersion, RaiseRefused
from taktus.composition.stages import (
    CeilingsOfTheStages,
    InstructionsOfTheVersion,
    LevelsOfTheProcess,
)
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs

ROOT = Path(__file__).resolve().parents[2]
TENANT = "t"
PERSON = "idn_person"
ROLE = "operations"


class Known:
    """The identities the tenant knows: a known name is a person's."""

    def __init__(self, *names: str) -> None:
        self.names = set(names)

    async def identity(self, tenant: str, identity: str) -> object | None:
        return identity if identity in self.names else None


class Instructions:
    """Takeover instructions as UC-6.3 will answer them: current for the processes listed."""

    def __init__(self, *current: str) -> None:
        self.current = set(current)

    async def lacking(self, tenant: str, process_id: str) -> str | None:
        return None if process_id in self.current else "none on its active version"


class Reports:
    """The owner-facing channel, as the stages see it: what it carries and what it was told."""

    def __init__(self, *roles: str) -> None:
        self.roles = set(roles)
        self.proposals: list[tuple[str, StageView, StageView | None]] = []
        self.falls: list[tuple[str, StageView, Sequence[Incident]]] = []

    async def carries(self, tenant: str, role: str) -> bool:
        return role in self.roles

    async def proposed(
        self, tenant: str, plan: StagePlan, stage: StageView, before: StageView | None
    ) -> None:
        self.proposals.append((plan.responsible, stage, before))

    async def fell(
        self, tenant: str, plan: StagePlan, stage: StageView, lowered: Sequence[Incident]
    ) -> None:
        self.falls.append((plan.responsible, stage, lowered))


def bundle(process: str, level: int, version: str = "1") -> dict[str, Any]:
    autonomy: dict[str, Any] = {"level": level, "reason": "r", "history": 1}
    if level < 4:
        autonomy["toward_next"] = "t"
    return instructed(
        {
            "id": process,
            "version": version,
            "name": process,
            "autonomy": autonomy,
            "steps": [
                {
                    "id": "read",
                    "method": "rule",
                    "reason": "r",
                    "rejected": [],
                    "exactness": "sourced",
                    "checks": [{"kind": "bounds", "pattern": "^\\{"}],
                    "work": {"rule": "connector", "operation": "files.read"},
                }
            ],
        }
    )


PLAN: dict[str, Any] = {
    "responsible": ROLE,
    "stages": [
        {
            "id": "watch",
            "name": "Taktus watches",
            "processes": {"report": 2},
            "condition": {"weeks": 2, "runs": 3, "missed": 0},
        },
        {
            "id": "routine",
            "name": "Taktus carries the routine",
            "processes": {"cost": 3, "triage": 4},
            "condition": {"weeks": 1, "incidents": 0, "correction_rate": 0.2},
        },
    ],
}


class World:
    def __init__(
        self, *, instructions: Instructions | None = None, known: Sequence[str] = (PERSON,)
    ) -> None:
        self.clock = FakeClock(datetime(2026, 10, 1, tzinfo=UTC))
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.incidents = MemoryRepository(self.persistence, Incident)
        self.corrections = Corrections(
            self.incidents,
            MemoryRepository(self.persistence, CorrectionLimits),
            self.ledger,
            self.persistence,
            self.clock,
        )
        self.reports = Reports(ROLE)
        self.identities = Known(*known)
        self.stages = Stages(
            MemoryRepository(self.persistence, StagePlan),
            self.incidents,
            self.ledger,
            self.persistence,
            self.clock,
            levels=LevelsOfTheProcess(
                self.processes, self.versions, self.persistence, self.corrections
            ),
            instructions=instructions or Instructions("report", "cost", "triage"),
            identities=self.identities,
            reports=self.reports,
        )
        self.register = RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            self.processes,
            ledger=self.ledger,
            stages=CeilingsOfTheStages(self.stages),
        )
        self.runs = 0

    async def registered(self, process: str, level: int, version: str = "1") -> ProcessVersion:
        return await self.register.execute(
            RegisterProcessVersion(
                bundle(process, level, version), tenant=TENANT, approved_by=PERSON
            )
        )

    async def record(
        self, kind: str, version: str, outcome: str | None = None, **refs: Any
    ) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=TENANT, process_version=version, **refs),
                    outcome=outcome,
                ),
            )

    async def ran(self, version: str, times: int = 1) -> None:
        for _ in range(times):
            self.runs += 1
            await self.record("run.created", version, run_id=f"run_{self.runs}")
            await self.record("run.finished", version, "succeeded", run_id=f"run_{self.runs}")

    def weeks(self, n: float) -> None:
        self.clock.current += timedelta(weeks=n)

    async def view(self, stage: str) -> StageView:
        return next(v for v in await self.stages.view(TENANT) if v.stage.id == stage)

    async def entries(self, *kinds: str) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return [e for e in await self.ledger.entries(TENANT) if e.kind in kinds]


async def declared(w: World, plan: dict[str, Any] = PLAN) -> StagePlan:
    return await w.stages.declare(TENANT, plan, by=PERSON)


# --- declared ----------------------------------------------------------------------------------


async def test_a_tenant_declares_ordered_stages_each_with_processes_levels_and_a_condition() -> (
    None
):
    w = World()
    plan = await declared(w)
    assert [s.id for s in plan.stages] == ["watch", "routine"]
    assert dict(plan.stages[1].processes) == {"cost": 3, "triage": 4}
    assert plan.stages[0].condition.runs == 3 and plan.stages[1].condition.correction_rate == 0.2
    [configured] = await w.entries("stages.configured")
    assert configured.refs.actor == PERSON and configured.content_digest is not None
    assert [v.state for v in await w.stages.view(TENANT)] == [StageState.CLOSED] * 2


async def test_a_plan_names_stages_processes_and_roles_never_a_person() -> None:
    w = World(known=(PERSON, "alice"))
    for wrong in (
        {**PLAN, "responsible": "alice"},
        {**PLAN, "stages": [{**PLAN["stages"][0], "processes": {"alice": 2}}]},
    ):
        with pytest.raises(StagesRefused) as refused:
            await declared(w, wrong)
        assert refused.value.reason == "person" and "never a person" in str(refused.value)
    with pytest.raises(StagesRefused, match="carries the role 'finance'"):
        await declared(w, {**PLAN, "responsible": "finance"})
    assert [e.outcome for e in await w.entries("stages.refused")] == ["person", "person", "role"]
    assert await w.stages.plan(TENANT) is None


# --- a stage not open keeps its processes at level 2 -------------------------------------------


async def test_a_process_of_a_stage_not_open_is_refused_above_level_two_naming_the_stage() -> None:
    w = World()
    await declared(w)
    await w.registered("cost", 2)
    with pytest.raises(RaiseRefused) as refused:
        await w.registered("cost", 3, version="2")
    finding = refused.value.findings[0]
    assert "the stage 'routine', which is not open" in finding
    assert "at most at level 2" in finding
    assert "stage 'watch' before it is not open" in finding, "it names the unmet condition"
    [entry] = [e for e in await w.entries("autonomy.refused")]
    assert entry.outcome == "stage_not_open" and entry.refs.process_version == "cost@2"


async def test_a_process_no_stage_names_is_not_capped() -> None:
    w = World()
    await declared(w)
    version = await w.registered("other", 4)
    assert version.autonomy.level == 4


async def test_a_plan_is_refused_while_a_process_already_runs_above_its_ceiling() -> None:
    w = World()
    await w.registered("triage", 3)
    with pytest.raises(StagesRefused) as refused:
        await declared(w)
    assert refused.value.reason == "above_ceiling" and "triage@1 runs at level 3" in str(
        refused.value
    )


# --- a person opens a stage on the rule's figures ----------------------------------------------


async def test_opening_needs_the_predecessor_to_hold_and_a_persons_approval() -> None:
    w = World()
    await declared(w)
    await w.registered("report", 2)
    with pytest.raises(StagesRefused) as refused:
        await w.stages.open(TENANT, "routine", by=PERSON)
    assert refused.value.reason == "out_of_order"
    with pytest.raises(StagesRefused) as refused:
        await w.stages.open(TENANT, "watch", by=None)
    assert refused.value.reason == "no_approval"
    with pytest.raises(StagesRefused) as refused:
        await w.stages.open(TENANT, "watch", by="idn_stranger")
    assert refused.value.reason == "unknown"
    opened = await w.stages.open(TENANT, "watch", by=PERSON)
    assert opened.state is StageState.OPEN and not opened.holds
    with pytest.raises(StagesRefused) as refused:
        await w.stages.open(TENANT, "routine", by=PERSON)
    assert refused.value.reason == "predecessor"
    assert "open 0.0 of 2 week(s)" in str(refused.value) and "0 of 3 run(s)" in str(refused.value)
    w.weeks(2)
    await w.ran("report@1", 3)
    assert (await w.view("watch")).holds
    with pytest.raises(StagesRefused) as refused:
        await w.stages.open(TENANT, "routine", by=PERSON)
    assert refused.value.reason == "not_run", "a stage opens only over processes that run"
    assert "runs no version of cost" in str(refused.value)
    await w.registered("cost", 2)
    await w.registered("triage", 2)
    routine = await w.stages.open(TENANT, "routine", by=PERSON)
    assert routine.state is StageState.OPEN
    reasons = [e.outcome for e in await w.entries("stage.refused")]
    assert reasons == ["out_of_order", "no_approval", "unknown", "predecessor", "not_run"]
    assert [(e.refs.stage_id, e.refs.actor) for e in await w.entries("stage.opened")] == [
        ("watch", PERSON),
        ("routine", PERSON),
    ]
    # Once open, the stage lifts the ceiling; the raise itself still needs its approval and
    # its history.
    await w.ran("cost@1")
    assert (await w.registered("cost", 3, version="2")).autonomy.level == 3


async def test_taktus_proposes_the_opening_with_the_figures_and_never_opens_a_stage() -> None:
    w = World()
    await declared(w)
    looked = await w.stages.look(TENANT)
    assert looked.proposed == ("watch",), "the first stage is proposed once declared"
    assert (await w.view("watch")).state is StageState.CLOSED, "proposed, never opened"
    assert (await w.stages.look(TENANT)).proposed == (), "proposed once"
    await w.registered("report", 2)
    await w.stages.open(TENANT, "watch", by=PERSON)
    assert (await w.stages.look(TENANT)).proposed == ()
    w.weeks(2)
    await w.ran("report@1", 3)
    looked = await w.stages.look(TENANT)
    assert looked.held == ("watch",) and looked.proposed == ("routine",)
    role, stage, before = w.reports.proposals[-1]
    assert role == ROLE and stage.stage.id == "routine" and stage.state is StageState.CLOSED
    assert before is not None and before.figures is not None and before.figures.runs == 3
    assert (await w.view("routine")).state is StageState.CLOSED
    assert await w.entries("stage.opened") != [] and all(
        e.refs.actor == PERSON for e in await w.entries("stage.opened")
    )


# --- a stage that stops holding falls back by rule ---------------------------------------------


async def test_a_stage_that_stops_holding_is_reported_and_its_processes_fall_by_rule() -> None:
    w = World()
    await declared(w)
    await w.registered("report", 2)
    await w.stages.open(TENANT, "watch", by=PERSON)
    w.weeks(2)
    await w.ran("report@1", 3)
    await w.registered("cost", 2)
    await w.registered("triage", 2)
    await w.stages.open(TENANT, "routine", by=PERSON)
    await w.ran("cost@1")
    await w.registered("cost", 3, version="2")
    w.weeks(1)
    assert (await w.stages.look(TENANT)).held == ("watch", "routine")
    await w.record("incident.raised", "cost@2", "missed", incident_id="inc_1")
    looked = await w.stages.look(TENANT)
    assert looked.fell == ("routine",)
    [incident] = looked.lowered
    assert incident.kind is IncidentKind.STAGE and incident.process_version == "cost@2"
    assert incident.facts["level_before"] == "3" and incident.facts["level_after"] == "2"
    assert "1 incident(s) raised, at most 0" in str(incident.facts["missing"])
    lowered = await w.entries("autonomy.lowered")
    assert [(e.refs.process_version, e.outcome, e.refs.stage_id) for e in lowered] == [
        ("cost@2", "level_2", "routine")
    ]
    assert lowered[0].refs.actor is None, "nobody approves a fall"
    assert (await w.corrections.lowered(TENANT, "cost@2")).level == 2, "the run reads it"
    role, stage, fallen = w.reports.falls[-1]
    assert role == ROLE and stage.stage.id == "routine" and list(fallen) == [incident]
    view = await w.view("routine")
    assert view.state is StageState.NOT_HOLDING and not view.holds
    # A stage that stopped holding grants nothing: the level rises only once it holds again.
    with pytest.raises(RaiseRefused, match="at most at level 2"):
        await w.registered("cost", 3, version="3")
    assert (await w.stages.look(TENANT)).fell == (), "it falls once"


# --- the view, computed from the ledger --------------------------------------------------------


async def test_the_view_shows_condition_figures_and_what_is_missing_from_the_ledger() -> None:
    w = World()
    await declared(w)
    await w.registered("report", 2)
    await w.stages.open(TENANT, "watch", by=PERSON)
    w.weeks(1)
    await w.ran("report@1", 2)
    await w.ran("other@1", 5)
    await w.record("incident.raised", "report@1", "missed", incident_id="inc_1")
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="run.finished",
                refs=LedgerRefs(tenant=TENANT, process_version="report@1", run_id="run_r"),
                rehearsal=True,
            ),
        )
    watch, routine = await w.stages.view(TENANT)
    assert watch.figures is not None
    assert (watch.figures.runs, watch.figures.missed, watch.figures.incidents) == (2, 1, 1)
    assert round(watch.figures.weeks) == 1
    assert watch.missing == (
        "open 1.0 of 2 week(s)",
        "2 of 3 run(s) finished",
        "1 expected run(s) missed, at most 0",
    )
    assert routine.figures is None
    assert routine.missing[0].startswith("stage 'watch' does not hold: open 1.0 of 2")
    assert routine.missing[-1] == "a person's approval"
    assert watch.stage.condition.described() == [
        "open for at least 2 week(s)",
        "at least 3 run(s) finished",
        "at most 0 expected run(s) missed",
    ]


async def test_the_correction_rate_and_proposals_waiting_are_read_per_process() -> None:
    w = World()
    plan = {
        "responsible": ROLE,
        "stages": [
            {
                "id": "watch",
                "name": "Watch",
                "processes": {"report": 2},
                "condition": {"correction_rate": 0.4, "undecided": 0},
            }
        ],
    }
    await declared(w, plan)
    await w.registered("report", 2)
    await w.stages.open(TENANT, "watch", by=PERSON)
    for outcome in ("released", "corrected", "released", "released"):
        await w.record("proposal.decided", "report@1", outcome, run_id="run_1", step_id="s")
    await w.record("step.awaiting", "report@1", "confirmation", run_id="run_2", step_id="s")
    [watch] = await w.stages.view(TENANT)
    assert watch.figures is not None
    assert watch.figures.correction_rate == 0.25 and watch.figures.undecided == 1
    assert watch.missing == ("1 proposal(s) waiting for a person, at most 0",)
    await w.record("step.confirmed", "report@1", "confirmed", run_id="run_2", step_id="s")
    [watch] = await w.stages.view(TENANT)
    assert watch.holds


# --- the blueprint is a floor ------------------------------------------------------------------


async def test_a_condition_may_be_stricter_than_its_blueprint_and_never_looser() -> None:
    w = World()
    floor = blueprint_stages(ROOT / "blueprints/software-operations/stages.yaml")
    proposed = floor.document()
    first = proposed["stages"][0]
    stricter = {
        "responsible": ROLE,
        "blueprint": "software-operations",
        "stages": [{**first, "condition": {**first["condition"], "weeks": 6, "runs": 20}}],
    }
    plan = await w.stages.declare(TENANT, stricter, by=PERSON, floor=floor)
    assert plan.stages[0].condition.weeks == 6
    looser = {
        **stricter,
        "stages": [{**first, "condition": {"weeks": 2, "undecided": 3}}],
    }
    with pytest.raises(StagesRefused) as refused:
        await w.stages.declare(TENANT, looser, by=PERSON, floor=floor)
    detail = str(refused.value)
    assert refused.value.reason == "looser"
    assert "`weeks` is 2, below the blueprint's 4" in detail
    assert "`missed` is left out" in detail and "`undecided` is 3, above" in detail
    with pytest.raises(StagesRefused, match="its stages were not given"):
        await w.stages.declare(TENANT, stricter, by=PERSON)


# --- takeover instructions ------------------------------------------------------------------------


async def test_a_stage_never_opens_while_a_process_it_adds_lacks_takeover_instructions() -> None:
    w = World(instructions=Instructions("cost"))
    await declared(w)
    await w.registered("report", 2)
    with pytest.raises(StagesRefused) as refused:
        await w.stages.open(TENANT, "watch", by=PERSON)
    assert refused.value.reason == "instructions"
    assert "takeover instructions of report" in str(refused.value)
    assert (await w.view("watch")).state is StageState.CLOSED


async def test_a_process_has_instructions_when_its_active_version_carries_them() -> None:
    """ADR-0180 §6: the port reads the active version; one stored before carries none."""
    persistence = MemoryPersistence()
    processes = MemoryRepository(persistence, Process)
    versions = MemoryRepository(persistence, ProcessVersion)
    port = InstructionsOfTheVersion(processes, versions, persistence)
    assert "no active version" in (await port.lacking(TENANT, "report") or "")
    version = parse_bundle(bundle("report", 2))
    async with persistence.transaction(TENANT):
        await versions.put(TENANT, version.model_copy(update={"takeover": None}))
        await processes.put(
            TENANT, Process(id="report", name="report", active_version=version.version)
        )
    assert "carries no takeover instructions" in (await port.lacking(TENANT, "report") or "")
    async with persistence.transaction(TENANT):
        await versions.put(TENANT, version)
    assert await port.lacking(TENANT, "report") is None


# --- UC-03's six stages --------------------------------------------------------------------------


async def test_uc_03s_six_stages_are_declared_and_shown_with_their_conditions() -> None:
    w = World()
    floor = blueprint_stages(ROOT / "blueprints/software-operations/stages.yaml")
    document = {
        "responsible": ROLE,
        "blueprint": floor.blueprint,
        "stages": [s.document() for s in floor.stages],
    }
    await w.stages.declare(TENANT, document, by=PERSON, floor=floor)
    view = await w.stages.view(TENANT)
    assert [v.stage.id for v in view] == [
        "control-loop",
        "operation-without-handwork",
        "customer-contact",
        "release-without-people",
        "development-end-to-end",
        "runs-dark",
    ]
    assert all(v.state is StageState.CLOSED for v in view)
    assert view[0].stage.condition.described() == [
        "open for at least 4 week(s)",
        "at most 0 expected run(s) missed",
        "at most 0 proposal(s) waiting for a person",
        "at most 0 day(s) without the daily report",
    ]
    assert "no correction rate above 25%" in view[2].stage.condition.described()
    assert "at most 0 incident(s)" in view[3].stage.condition.described()
    assert max(view[0].stage.processes.values()) <= 2, "stage 0 runs at level 1 to 2"
    every = {p for v in view[1:] for p in v.stage.processes}
    assert len(every) == 85, "every process of UC-03 §4.1 to §4.10 belongs to a stage"
    assert not {"b-2-05", "b-4-03"} & every, "the trial and the correction rate are the instance's"
    assert not any(p.startswith("b-11-") for p in every), "the steering is Taktus itself"
    assert "b-9-01" not in {p for v in view for p in v.stage.processes}, (
        "the daily report is the instance's, counted by `reports_missed`"
    )


def test_every_bundle_of_the_blueprint_is_named_by_its_stages_and_starts_at_most_at_level_two() -> (
    None
):
    """ADR-0191 §4: a stage names a process by its bundle's identifier, or it names nothing
    the tenant registers; and every process of UC-03 starts at level 1 or 2 (UC-03 §4)."""
    floor = blueprint_stages(ROOT / "blueprints/software-operations/stages.yaml")
    named = {p for s in floor.stages for p in s.processes}
    bundles = sorted((ROOT / "blueprints/software-operations/processes").glob("*.yaml"))
    assert bundles
    for path in bundles:
        bundle = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert bundle["id"] in named, f"{path.name}: {bundle['id']} is named by no stage"
        assert bundle["autonomy"]["level"] <= 2, f"{path.name} starts above level 2"
        number = path.name.split("-", 2)[1]  # B-1.01-daily-cost.yaml -> 1.01
        assert bundle["id"] == "b-" + number.replace(".", "-"), path.name


# --- a stage counts only processes that run (ADR-0191) -------------------------------------------


async def deactivated(w: World, process: str) -> None:
    async with w.persistence.transaction(TENANT):
        found = await w.processes.get(TENANT, process)
        assert found is not None
        await w.processes.put(TENANT, found.model_copy(update={"active_version": None}))


async def test_a_stage_opens_only_once_every_process_it_adds_runs_for_the_tenant() -> None:
    w = World()
    await declared(w)
    watch = await w.view("watch")
    assert "t runs no version of report" in watch.missing
    with pytest.raises(StagesRefused) as refused:
        await w.stages.open(TENANT, "watch", by=PERSON)
    assert refused.value.reason == "not_run"
    assert (await w.view("watch")).state is StageState.CLOSED
    await w.registered("report", 2)
    assert "t runs no version of report" not in (await w.view("watch")).missing
    assert (await w.stages.open(TENANT, "watch", by=PERSON)).state is StageState.OPEN


async def test_an_open_stage_does_not_hold_while_a_process_it_adds_runs_no_version() -> None:
    w = World()
    await declared(w)
    await w.registered("report", 2)
    await w.stages.open(TENANT, "watch", by=PERSON)
    w.weeks(2)
    await w.ran("report@1", 3)
    assert (await w.stages.look(TENANT)).held == ("watch",)
    await deactivated(w, "report")
    watch = await w.view("watch")
    assert not watch.holds and watch.missing == ("t runs no version of report",)
    assert (await w.stages.look(TENANT)).fell == ("watch",)


async def test_the_view_shows_each_process_with_its_version_level_and_what_it_did() -> None:
    w = World()
    await declared(w)
    await w.registered("report", 2)
    await w.stages.open(TENANT, "watch", by=PERSON)
    w.weeks(1)
    await w.ran("report@1", 2)
    await w.record("incident.raised", "report@1", "missed", incident_id="inc_1")
    watch, routine = await w.stages.view(TENANT)
    [report] = watch.processes
    assert (report.process, report.version, report.level, report.granted) == (
        "report",
        "report@1",
        2,
        2,
    )
    assert (report.runs, report.missed, report.incidents) == (2, 1, 1)
    assert report.last_finished is not None and watch.opened_at is not None
    assert watch.opened_at < report.last_finished <= w.clock.now()
    assert [(p.process, p.version, p.level, p.runs) for p in routine.processes] == [
        ("cost", None, None, 0),
        ("triage", None, None, 0),
    ], "a stage not open shows what runs, and counts nothing"
    assert "idn_" not in str(watch.document()), "no figure names a person"


async def test_the_days_without_the_daily_report_are_counted_and_bind() -> None:
    w = World()
    plan = {
        "responsible": ROLE,
        "stages": [
            {
                "id": "watch",
                "name": "Watch",
                "processes": {"report": 2},
                "condition": {"reports_missed": 0},
            }
        ],
    }
    await declared(w, plan)
    await w.registered("report", 2)
    await w.stages.open(TENANT, "watch", by=PERSON)  # 2026-10-01, 00:00 UTC
    for day in ("20261001", "20261002", "20261004"):
        async with w.persistence.transaction(TENANT):
            await w.ledger.record(
                TENANT,
                Fact(
                    kind="report.raised",
                    refs=LedgerRefs(tenant=TENANT, report_id=f"signals-{day}"),
                    outcome="daily",
                ),
            )
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="report.raised",
                refs=LedgerRefs(tenant=TENANT, report_id="red-inc_1"),
                outcome="red",
            ),
        )
    w.clock.current += timedelta(days=4, hours=7)
    [watch] = await w.stages.view(TENANT)
    assert watch.figures is not None and watch.figures.reports_missed == 1, "the third day"
    assert watch.missing == ("1 day(s) without the daily report, at most 0",)
    assert watch.stage.condition.described()[-1] == "at most 0 day(s) without the daily report"
