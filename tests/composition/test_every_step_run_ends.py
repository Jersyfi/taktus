"""No execution ends without a recorded outcome (UC-4.6 §2, last condition).

Every process bundle of this repository — the examples, every blueprint's and the gallery's —
is parsed as registration parses it and run once, as a rehearsal, by the run engine over memory
stores, with the inputs its bundle gives as examples. What is real: parsing and validation as
registration applies them, the plan, the engine, admission, the ledger. What stands in: a fake
worker; no connector and no model is configured, so a step that needs one is blocked or fails,
as it would on an instance that lacks it. That is not what is tested: whatever a step's run
did, the ledger must say how it ended.

What is proven: for every step run that left `planned`, the ledger holds an entry of that step
stating where it ended — `step.finished` with the step run's state as its outcome, or, for a
step that has not ended, the entry that says what it waits on — and the run's own last state
is recorded as an entry of the run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from fakes import FakeClock, FakeIdentifiers, FakeWorker
from fakes.maturity import VERIFIED

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, StepState
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import Commissioned, Plan, PlanResult, PlanStatus

ROOT = Path(__file__).resolve().parents[2]
BUNDLES = sorted(
    [
        *ROOT.glob("blueprints/*/processes/*.yaml"),
        *ROOT.glob("blueprints/gallery/*/processes/*.yaml"),
        *ROOT.glob("examples/processes/*.yaml"),
    ]
)
AT = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
TENANT = "t"
BUDGET = Limits(compute=ComputeLimit(seconds=600, resource_class="cpu.small"))


def test_every_bundle_is_found() -> None:
    assert len(BUNDLES) > 50


DOCUMENTS = {path: path.read_text(encoding="utf-8") for path in BUNDLES}


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: str(p.relative_to(ROOT)))
async def test_every_step_run_of_every_bundle_ends_with_a_recorded_outcome(path: Path) -> None:
    document: dict[str, Any] = yaml.safe_load(DOCUMENTS[path])
    version = parse_bundle(document)
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    runs = MemoryRepository(persistence, Run)
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    engine = RunEngine(
        maturities=VERIFIED,
        runs=runs,
        work=persistence,
        objects=MemoryObjectStore(),
        ledger=ledger,
        provenance=MemoryProvenanceStore(persistence),
        workers=StaticWorkerPool([("worker.fake.0", FakeWorker())]),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        options=EngineOptions(uncalibrated_margin=0.0),
    )
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal=f"run {version.ref}",
        autonomy_level=version.autonomy_level,
        steps=version.ordered(),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=AT),
    )
    budget = Limits.model_validate(dict(version.limits)) if version.limits else BUDGET
    run = await engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=budget,
            process_version=version.ref,
            actor="idn_t",
            tenant=TENANT,
            inputs={name: given.example for name, given in version.inputs.items()},
            rehearsal=True,
            actions=version.autonomy.action_levels,
        )
    )
    async with persistence.transaction(TENANT):
        entries = list(await ledger.entries(TENANT, run.id))
    said = [(e.kind, e.refs.step_id, e.outcome) for e in entries]
    for step_run in run.step_runs:
        if step_run.state is StepState.PLANNED:
            continue
        own = [(kind, outcome) for kind, step, outcome in said if step == step_run.step_id]
        if step_run.done:
            assert ("step.finished", str(step_run.state)) in own, (
                f"{path.name}: {step_run.step_id} ended {step_run.state} and no `step.finished` "
                f"says so: {own}"
            )
        else:
            assert own and own[-1][0] != "step.started", (
                f"{path.name}: {step_run.step_id} is {step_run.state} and the ledger does not "
                f"say what it waits on: {own}"
            )
    ran = [kind for kind, step, _ in said if step is None and kind.startswith("run.")]
    assert f"run.{run.state}" in ran, f"{path.name}: the run is {run.state}, unrecorded: {ran}"
