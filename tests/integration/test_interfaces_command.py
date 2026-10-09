"""`taktusctl interfaces` end to end (issue #100, ADR-0047): an instance whose tenant configured
no owner-facing channel still records every broken interface it noticed, and shows it to its
operator as not delivered."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fakes import VERIFIED, FakeConnector, FakeIdentifiers, failure
from fakes.connector import READ

from taktus.adapters.driven.clock import SystemClock
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
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
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .test_first_slice import PLAIN, taktusctl

TENANT = "default"
PERSON = "idn_operator"


async def a_run_whose_interface_answers_unexpectedly(state_dir: Path) -> Run:
    """A run in the development store whose one read is answered in a way its connector does
    not foresee."""
    persistence = MemoryPersistence(state_dir)
    clock = SystemClock()
    connector = FakeConnector()
    connector.fail_next[READ] = failure("unexpected")
    engine = RunEngine(
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(state_dir / "objects"),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        provenance=MemoryProvenanceStore(persistence),
        workers=StaticWorkerPool([]),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        maturities=VERIFIED,
        connectors=StaticConnectorPool([("connector.records", connector)]),
    )
    step = Step(
        id="read",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
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
    work = {"read": {"rule": "connector", "operation": READ, "input": {"id": "x"}}}
    return await engine.start(
        StartRun(
            plan=plan,
            work=work,
            budget=Limits(
                compute=ComputeLimit(seconds=10, resource_class="cpu.small"),
                quota=QuotaLimit(units=5),
            ),
            process_version="intake@1",
            actor=PERSON,
            tenant=TENANT,
        )
    )


def interfaces(state_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_")}
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "interfaces", *args],
        capture_output=True,
        text=True,
        env={**inherited, **PLAIN, "TAKTUS_STATE_DIR": str(state_dir)},
        check=False,
    )


def test_without_a_channel_the_operator_sees_it_recorded_and_not_delivered(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    nothing = interfaces(state)
    assert nothing.returncode == 0 and "no broken interfaces" in nothing.stdout

    run = asyncio.run(a_run_whose_interface_answers_unexpectedly(state))
    assert run.state is RunState.ESCALATED
    shown = interfaces(state)
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout.startswith("Broken interface: connector.records")
    assert run.id in shown.stdout and "step read" in shown.stdout
    assert "not delivered: this tenant configured no owner-facing channel" in shown.stdout
    assert PERSON not in shown.stdout

    (document,) = json.loads(interfaces(state, "--json").stdout)
    assert (document["interface"], document["cause"]) == ("connector.records", "unexpected")
    assert (document["delivered"], document["reason"]) == (False, "no_channel")
    assert document["calls"][0]["run_id"] == run.id
