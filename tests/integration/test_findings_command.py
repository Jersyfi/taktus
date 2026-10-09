"""`taktusctl findings` end to end (UC-6.12 §2): an instance that does not send its findings
records them and shows them to its operator, who can send one by hand."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fakes import FakeIdentifiers, FakeMaturities, FakeWorker

from taktus.adapters.driven.clock import SystemClock
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
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service.ready import missing_sections
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .test_first_slice import PLAIN, taktusctl

TENANT = "default"
PERSON = "idn_operator"


async def a_run_that_lacks_a_worker(state_dir: Path) -> Run:
    """A run in the development store whose step needs a worker no configured one offers."""
    persistence = MemoryPersistence(state_dir)
    clock = SystemClock()
    engine = RunEngine(
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(state_dir / "objects"),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        provenance=MemoryProvenanceStore(persistence),
        workers=StaticWorkerPool([("worker.shell", FakeWorker())]),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        options=EngineOptions(uncalibrated_margin=0.0),
        maturities=FakeMaturities(),
    )
    step = Step(
        id="review",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("code.review",),
    )
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=(step,),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=PERSON, at=datetime.now(UTC)),
    )
    return await engine.start(
        StartRun(
            plan=plan,
            work={"review": {"task": {"goal": "g", "acceptance": ["a"], "inputs": {}}}},
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="intake@1",
            actor=PERSON,
            tenant=TENANT,
        )
    )


def findings(state_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_")}
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "findings", *args],
        capture_output=True,
        text=True,
        env={**inherited, **PLAIN, "TAKTUS_STATE_DIR": str(state_dir)},
        check=False,
    )


def test_the_operator_sees_each_finding_ready_to_send_by_hand(tmp_path: Path) -> None:
    state = tmp_path / "state"
    nothing = findings(state)
    assert nothing.returncode == 0 and "no product findings" in nothing.stdout

    run = asyncio.run(a_run_that_lacks_a_worker(state))
    assert run.state is RunState.ESCALATED
    shown = findings(state)
    assert shown.returncode == 0, shown.stderr
    title, _, body = shown.stdout.partition("\n\n")
    assert title == "Product finding: no worker offers code.review"
    assert missing_sections(body) == [], "the body has the form's sections"
    assert run.id in body and PERSON not in shown.stdout

    (document,) = json.loads(findings(state, "--json").stdout)
    assert document["lack"] == {"cause": "no_worker", "lacking": "code.review"}
    assert document["occurrences"][0]["run_id"] == run.id
