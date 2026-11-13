"""UC-03's six stages, each held to the condition `blueprints/software-operations/stages.yaml`
ships: a ledger that meets it opens the next stage, and one that misses it in one figure keeps
the next stage closed (UC-9.6, UC-03 §5, ADR-0137, ADR-0191; #400, #437, #401, #438, #439,
#440).

The world is `governance.test_stages`'s. The plan is the blueprint's stages, declared verbatim
with the blueprint as its floor. Every process a stage names is registered at level 1, as a
tenant's version would be; what the processes did is written to the ledger as their runs and
the instance's daily report would write it, and every figure is counted from there. Which
system serves a process is not this test's: its bundles run against fakes in
`tests/composition/test_software_operations*.py`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from governance.test_stages import PERSON, ROLE, TENANT, Instructions, World
from taktus.adapters.driving.cli.stage_command import blueprint_stages
from taktus.components.governance.application.service import StagesRefused
from taktus.components.governance.domain.model import StageState
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

ROOT = Path(__file__).resolve().parents[2]
FLOOR = blueprint_stages(ROOT / "blueprints/software-operations/stages.yaml")
STAGES = [s.id for s in FLOOR.stages]

SHIPPED = {
    "control-loop": {"weeks": 4, "missed": 0, "undecided": 0, "reports_missed": 0},
    "operation-without-handwork": {"weeks": 4},
    "customer-contact": {"weeks": 4, "correction_rate": 0.25},
    "release-without-people": {"weeks": 4, "incidents": 0},
    "development-end-to-end": {"weeks": 4},
    "runs-dark": {"weeks": 4},
}
"""The conditions the tests' ledgers are written against. A change of `stages.yaml` fails
`test_the_ledgers_are_written_against_the_conditions_that_ship` until they follow it."""


def processes(stage: str) -> list[str]:
    return sorted(next(s for s in FLOOR.stages if s.id == stage).processes)


def every_process() -> list[str]:
    return sorted({p for s in FLOOR.stages for p in s.processes})


def first_of(stage: str) -> str:
    return f"{processes(stage)[0]}@1"


class Tenant:
    """A tenant that declared UC-03's stages and runs every process they name."""

    def __init__(self) -> None:
        self.w = World(instructions=Instructions(*every_process()))
        self.registered: set[str] = set()

    async def declare(self) -> None:
        document = {
            "responsible": ROLE,
            "blueprint": FLOOR.blueprint,
            "stages": [s.document() for s in FLOOR.stages],
        }
        await self.w.stages.declare(TENANT, document, by=PERSON, floor=FLOOR)

    async def runs(self, stage: str) -> None:
        for process in processes(stage):
            if process not in self.registered:
                await self.w.registered(process, 1)
                self.registered.add(process)

    async def open(self, stage: str) -> None:
        await self.runs(stage)
        opened = await self.w.stages.open(TENANT, stage, by=PERSON)
        assert opened.state is StageState.OPEN

    async def report(self) -> None:
        """The instance's daily report of the day that just began (ADR-0191 §2)."""
        day = self.w.clock.now().strftime("%Y%m%d")
        async with self.w.persistence.transaction(TENANT):
            await self.w.ledger.record(
                TENANT,
                Fact(
                    kind="report.raised",
                    refs=LedgerRefs(tenant=TENANT, report_id=f"signals-{day}"),
                    outcome="daily",
                ),
            )

    async def held(self, stage: str, weeks: int = 4, *, skip_report: int | None = None) -> None:
        """`weeks` of the stage open, day by day: every process the stage adds ran, every
        proposal was decided, and the daily report came each day but the one skipped."""
        await self.report()
        for day in range(weeks * 7):
            self.w.clock.current += timedelta(days=1)
            if day != skip_report:
                await self.report()
            if day % 7 == 0:
                for process in processes(stage):
                    await self.w.ran(f"{process}@1")

    async def walk_to(self, stage: str) -> None:
        """Every stage before `stage` opened and held under its shipped condition, and
        `stage` opened."""
        await self.declare()
        for earlier in STAGES[: STAGES.index(stage)]:
            await self.open(earlier)
            await self.held(earlier)
        await self.open(stage)

    async def opens_next(self, stage: str) -> bool:
        """Whether the stage after `stage` opens now; refused only because `stage` does not
        hold."""
        following = STAGES[STAGES.index(stage) + 1]
        await self.runs(following)
        try:
            await self.w.stages.open(TENANT, following, by=PERSON)
        except StagesRefused as refused:
            assert refused.reason == "predecessor", str(refused)
            assert (await self.w.view(following)).state is StageState.CLOSED
            return False
        return True


def test_the_ledgers_are_written_against_the_conditions_that_ship() -> None:
    shipped = {
        s.id: s.condition.model_dump(exclude_defaults=True, exclude_none=True) for s in FLOOR.stages
    }
    assert shipped == SHIPPED


@pytest.mark.parametrize("stage", STAGES[:-1])
async def test_a_stage_that_held_its_shipped_condition_opens_the_next(stage: str) -> None:
    t = Tenant()
    await t.walk_to(stage)
    await t.held(stage)
    assert (await t.w.view(stage)).holds, (await t.w.view(stage)).missing
    assert await t.opens_next(stage)


async def test_the_last_stage_holds_once_its_shipped_condition_held() -> None:
    t = Tenant()
    await t.walk_to("runs-dark")
    await t.held("runs-dark", weeks=3)
    assert "runs-dark" not in (await t.w.stages.look(TENANT)).held
    await t.held("runs-dark", weeks=1)
    assert "runs-dark" in (await t.w.stages.look(TENANT)).held, "the business runs dark"


async def missed_run(t: Tenant, stage: str) -> None:
    await t.w.record("incident.raised", first_of(stage), "missed", incident_id="inc_missed")


async def undecided(t: Tenant, stage: str) -> None:
    await t.w.record("step.awaiting", first_of(stage), "confirmation", run_id="run_w", step_id="s")


async def corrected_half(t: Tenant, stage: str) -> None:
    for outcome in ("released", "corrected", "released", "corrected"):
        await t.w.record("proposal.decided", first_of(stage), outcome, run_id="run_d", step_id="s")


async def incident(t: Tenant, stage: str) -> None:
    await t.w.record("incident.raised", first_of(stage), "signal_red", incident_id="inc_red")


Spoiler = Callable[[Tenant, str], Awaitable[None]]

MISSING: list[tuple[str, str, Spoiler | None, dict[str, Any]]] = [
    ("control-loop", "three weeks", None, {"weeks": 3}),
    ("control-loop", "a missed run", missed_run, {}),
    ("control-loop", "a proposal undecided", undecided, {}),
    ("control-loop", "a day without the report", None, {"skip_report": 10}),
    ("operation-without-handwork", "three weeks", None, {"weeks": 3}),
    ("customer-contact", "three weeks", None, {"weeks": 3}),
    ("customer-contact", "half corrected", corrected_half, {}),
    ("release-without-people", "three weeks", None, {"weeks": 3}),
    ("release-without-people", "an incident", incident, {}),
    ("development-end-to-end", "three weeks", None, {"weeks": 3}),
]


@pytest.mark.parametrize(
    ("stage", "spoiler", "held"),
    [pytest.param(s, spoil, held, id=f"{s}: {why}") for s, why, spoil, held in MISSING],
)
async def test_a_stage_that_missed_its_shipped_condition_keeps_the_next_closed(
    stage: str, spoiler: Spoiler | None, held: dict[str, Any]
) -> None:
    t = Tenant()
    await t.walk_to(stage)
    await t.held(stage, **held)
    if spoiler is not None:
        await spoiler(t, stage)
    view = await t.w.view(stage)
    assert not view.holds and len(view.missing) == 1, view.missing
    assert not await t.opens_next(stage)


async def test_stage_one_holds_four_weeks_whatever_else_its_processes_did() -> None:
    """Stage 1's condition is the four weeks alone: every missed run raises an incident
    (UC-4.16), so the figure that binds is the time (stages.yaml)."""
    t = Tenant()
    await t.walk_to("operation-without-handwork")
    await t.held("operation-without-handwork")
    await missed_run(t, "operation-without-handwork")
    assert await t.opens_next("operation-without-handwork")


async def test_a_correction_rate_at_the_shipped_limit_still_holds() -> None:
    t = Tenant()
    await t.walk_to("customer-contact")
    await t.held("customer-contact")
    for outcome in ("released", "corrected", "released", "released"):
        await t.w.record("proposal.decided", first_of("customer-contact"), outcome, run_id="r")
    figures = (await t.w.view("customer-contact")).figures
    assert figures is not None and figures.correction_rate == 0.25
    assert await t.opens_next("customer-contact")


SERVED_INSIDE = {"b-3-03", "b-3-12", "b-4-01", "b-4-02", "b-4-04", "b-4-05", "b-4-06"}
"""Rows of stage 2 declared inside B-3.02's bundle; a tenant's plan names `b-3-02` for them
(NTC-0263, NTC-0266)."""


def test_stages_zero_to_two_name_only_processes_a_shipped_bundle_serves() -> None:
    """ADR-0191 §1: a stage opens only over processes that run. Stages 0 and 1 name only
    processes whose bundle the blueprint ships, so a tenant can declare them verbatim
    (NTC-0280); stage 2's other rows are served inside B-3.02, or are a document of the
    business (B-4.07)."""
    bundles = {
        yaml.safe_load(p.read_text(encoding="utf-8"))["id"]
        for p in (ROOT / "blueprints/software-operations/processes").glob("*.yaml")
    }
    for stage in STAGES[:2]:
        assert set(processes(stage)) <= bundles, set(processes(stage)) - bundles
    assert set(processes("customer-contact")) - bundles == SERVED_INSIDE | {"b-4-07"}
