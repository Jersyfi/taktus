"""The overview of UC-6.10, drawn from a tenant's processes and runs (ADR-0067, issue #191).

How busy a process is counts its runs by the run component's own definitions; only a step
running right now moves; an idle tenant draws no motion; a process or a run the predicate
withholds is absent and not counted; no element can hold a person.
"""

from __future__ import annotations

import pytest

from taktus.components.reporting.application.query import LevelQueries
from taktus.components.reporting.domain.model import (
    OverviewFacts,
    PlannedStep,
    ProcessFacts,
    ProcessRef,
    ProcessSummary,
    Reader,
    RunActivity,
    RunFacts,
    RunningStep,
    RunRef,
)
from taktus.components.reporting.domain.model.vocabulary import Motion
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.domain.service.drawing import Step, check
from taktus.components.reporting.domain.service.levels import (
    AreaElement,
    OverviewLevel,
    ProcessSummaryElement,
    RunningStepElement,
    by_family,
    overview_level,
)
from taktus.components.run.domain.model import WAITING, WORKING, RunState
from taktus.shared.v1 import ExactnessClass, Method

READER = Reader(tenant="default", identity="idn_ada")


def activity(
    name: str, process: str, state: str, *running: RunningStep, tenant: str = "default"
) -> RunActivity:
    return RunActivity(
        id=name,
        tenant=tenant,
        process_version=f"{process}@1",
        state=state,
        working=RunState(state) in WORKING,
        waiting=RunState(state) in WAITING,
        running=running,
    )


DRAFT = RunningStep(id="draft", method=Method.LLM, exactness=ExactnessClass.FREE)
SCORE = RunningStep(id="score", method=Method.STATISTICS, exactness=ExactnessClass.SOURCED)


def facts(*runs: RunActivity) -> OverviewFacts:
    return OverviewFacts(
        tenant="default",
        processes=(
            ProcessSummary(id="invoices", name="Invoices", active_version="2", autonomy_level=2),
            ProcessSummary(id="orders", name="Orders", active_version="1", autonomy_level=3),
        ),
        runs=runs,
    )


BUSY = facts(
    activity("r1", "invoices", "running", DRAFT),
    activity("r2", "invoices", "waiting_human"),
    activity("r3", "invoices", "finished"),
    activity("r4", "orders", "admitted"),
    activity("r5", "imports", "running", SCORE),
)


def processes(level: OverviewLevel) -> dict[str, ProcessSummaryElement]:
    return {p.id: p for p in level.areas[0].processes}


def test_how_busy_a_process_is_counts_its_runs_by_the_run_components_definitions() -> None:
    found = processes(overview_level(BUSY))
    assert (found["invoices"].working, found["invoices"].waiting) == (1, 1)
    assert (found["orders"].working, found["orders"].waiting) == (1, 0)
    area = overview_level(BUSY).areas[0]
    assert (area.working, area.waiting) == (3, 1)
    assert set(WORKING).isdisjoint(WAITING) and RunState.FINISHED not in WORKING | WAITING


def test_a_run_of_a_process_not_registered_is_still_shown_under_its_process() -> None:
    found = processes(overview_level(BUSY))
    assert found["imports"].name == "imports" and found["imports"].working == 1


def test_only_a_step_running_now_moves_and_its_glyph_is_the_vocabularys() -> None:
    level = overview_level(BUSY)
    running = [s for p in level.areas[0].processes for s in p.running]
    assert {(s.run, s.step) for s in running} == {("r1", "draft"), ("r5", "score")}
    for motion in (True, False):
        drawn = [
            (
                Step(name=s.step, method=s.method, exactness=s.exactness, state="running"),
                s.drawn.moving if motion else s.drawn.still,
            )
            for s in running
        ]
        assert check(drawn, motion=motion) == ()
    assert {s.drawn.moving.motion for s in running} == {Motion.SHIMMER, Motion.PULSE}


def test_an_idle_tenant_draws_no_motion() -> None:
    idle = overview_level(facts(activity("r3", "invoices", "finished")))
    assert all(not p.running for p in idle.areas[0].processes)
    assert (idle.areas[0].working, idle.areas[0].waiting) == (0, 0)


def test_every_element_has_a_text_with_the_same_figures() -> None:
    level = overview_level(BUSY)
    found = processes(level)
    assert found["invoices"].text == (
        "Process Invoices (invoices@2) at autonomy level 2: 1 run working, 1 waiting; "
        "running now: draft in r1."
    )
    assert level.areas[0].text == "Area default: 3 processes, 3 runs working, 1 waiting."


def test_no_element_can_hold_a_person() -> None:
    for kind in (AreaElement, ProcessSummaryElement, RunningStepElement, RunActivity):
        assert not {"identity", "actor", "person", "by", "decided_by"} & set(kind.model_fields)


class Records:
    def __init__(self, found: OverviewFacts) -> None:
        self.found = found

    async def run(self, tenant: str, run_id: str) -> RunFacts | None:
        return None

    async def process(
        self, tenant: str, process_id: str, version: str | None
    ) -> ProcessFacts | None:
        return None

    async def overview(self, tenant: str) -> OverviewFacts:
        return self.found


async def test_a_process_or_run_the_predicate_withholds_is_absent_and_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    may_see, may_see_process = visibility.may_see, visibility.may_see_process

    def runs(reader: Reader, ref: RunRef) -> bool:
        return may_see(reader, ref) and ref.id != "r2"

    def procs(reader: Reader, ref: ProcessRef) -> bool:
        return may_see_process(reader, ref) and ref.id != "orders"

    monkeypatch.setattr(visibility, "may_see", runs)
    monkeypatch.setattr(visibility, "may_see_process", procs)
    level = await LevelQueries(Records(BUSY)).overview(READER)
    found = processes(level)
    assert "orders" not in found
    assert (found["invoices"].working, found["invoices"].waiting) == (1, 0)
    assert (level.areas[0].working, level.areas[0].waiting) == (2, 0)


async def test_another_tenants_runs_are_not_counted() -> None:
    elsewhere = BUSY.model_copy(
        update={"runs": (*BUSY.runs, activity("x1", "invoices", "running", tenant="other"))}
    )
    level = await LevelQueries(Records(elsewhere)).overview(READER)
    assert processes(level)["invoices"].working == 1


# The overview opens with a sentence and draws every process as its cells (ADR-0067, amended
# 2026-10-12, DEC-0185).

READ = PlannedStep(id="read", method=Method.RULE, exactness=ExactnessClass.EXACT)
WRITE = PlannedStep(
    id="draft", method=Method.LLM, exactness=ExactnessClass.FREE, depends_on=("read",)
)
PIPELINE = PlannedStep(id="pipeline", method=Method.WAIT, exactness=None, depends_on=("draft",))


def body(*runs: RunActivity) -> OverviewFacts:
    invoices = ProcessSummary(
        id="invoices",
        name="Invoices",
        active_version="2",
        autonomy_level=2,
        steps=(READ, WRITE, PIPELINE),
    )
    return OverviewFacts(tenant="default", processes=(invoices,), runs=runs)


def test_the_families_are_counted_in_words() -> None:
    methods = [Method.RULE, Method.STATISTICS, Method.LLM, Method.HUMAN, Method.WAIT]
    assert by_family(methods) == "2 reproducible, 1 variable, 1 with a person, 1 waiting"


def test_the_overview_opens_with_what_works_now_and_names_a_waiting_step_apart() -> None:
    assert overview_level(BUSY).summary == (
        "2 steps at work in 2 processes: 1 reproducible, 1 variable. 1 run waits."
    )
    idle = overview_level(facts(activity("r3", "invoices", "finished")))
    assert idle.summary == "Nothing is working right now."
    waiting = RunningStep(id="pipeline", method=Method.WAIT, exactness=None)
    outside = overview_level(body(activity("r1", "invoices", "running", waiting)))
    assert outside.summary == "Nothing is working right now. 1 step waits on something outside."


def test_every_process_is_drawn_as_its_cells_and_only_a_running_cell_moves() -> None:
    running = RunningStep(id="draft", method=Method.LLM, exactness=ExactnessClass.FREE)
    this = activity("r1", "invoices", "running", running)
    # A run of another version runs the same step: it does not make the cell move.
    other = activity("r2", "invoices", "running", running)
    level = overview_level(
        body(
            this.model_copy(update={"process_version": "invoices@2"}),
            other.model_copy(update={"process_version": "invoices@1"}),
        )
    )
    (invoices,) = level.areas[0].processes
    cells = {c.id: c for c in invoices.cells}
    assert list(cells) == ["read", "draft", "pipeline"]
    assert cells["draft"].running_in == ("r1",)
    assert cells["draft"].depends_on == ("read",)
    assert cells["draft"].drawn.moving.motion is Motion.SHIMMER
    assert cells["read"].drawn.moving.motion is Motion.NONE
    assert cells["pipeline"].drawn.moving.motion is Motion.NONE
    for motion in (True, False):
        drawn = [
            (
                Step(
                    name=c.id,
                    method=c.method,
                    exactness=c.exactness,
                    state="running" if c.running_in else "planned",
                ),
                c.drawn.moving if motion else c.drawn.still,
            )
            for c in invoices.cells
        ]
        assert check(drawn, motion=motion) == ()


def test_an_idle_body_draws_no_motion() -> None:
    level = overview_level(body(activity("r3", "invoices", "finished")))
    assert all(c.drawn.moving.motion is Motion.NONE for c in level.areas[0].processes[0].cells)
