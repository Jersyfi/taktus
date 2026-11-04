"""A foreign agent as a worker: a run uses it and removal changes the step (#349, ADR-0172,
UC-14.5).

Two A2A bindings run as processes behind the worker contract, each in front of a reference
agent of its own (`tests/fakes/a2a_agent.py`), a small server of the agent-to-agent protocol
that knows nothing of Taktus. Both offer `report.draft`.

- A run whose step requires `report.draft` is served by the first binding: the agent receives
  the task, the step finishes with the agent's report, and the run's compute budget is what
  the binding holds its estimate against.
- The removal test S-01 withholds the first binding. The step it served is served by the
  second, which the finding names as its alternative, and the verdict is *changed*. The step
  reaches an agent's host, so the rehearsals do not run it for real (ADR-0030): the verdict
  rests on which worker would serve it, and no agent receives anything.

What is not proven here: a real agent, which needs its operator's address and credential.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClock, FakeConnector, FakeIdentifiers, FakeMaturities
from fakes.a2a_agent import ReferenceAgent
from fakes.takeover import instructed

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import REMOVAL_TESTED
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.worker import Limits
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

from .conftest import ROOT, free_port
from .test_dev_orchestration import wait_ready
from .test_removal_test import TENANT, connector_services, result_of, run_removal

FIRST = "worker.agent"
SECOND = "worker.agent-other"
BINDING = ROOT / "workers" / "a2a" / "worker.py"
CREDENTIAL = "A2A_AGENT_TOKEN"
CAPABILITY = "report.draft"
BUDGET: dict[str, Any] = {"compute": {"seconds": 60, "resource_class": "agent.remote"}}
AT = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)


@dataclass
class Running:
    endpoint: str
    agent: ReferenceAgent


@pytest.fixture
def bindings(tmp_path: Path) -> Iterator[dict[str, Running]]:
    """Both bindings, each in front of its own reference agent with a token of its own."""
    started: list[subprocess.Popen[bytes]] = []
    running: dict[str, Running] = {}
    try:
        for adapter in (FIRST, SECOND):
            token = "fake-" + secrets.token_hex(8)
            agent = ReferenceAgent(token=token, turn_seconds=0.1).start()
            port = free_port()
            name = adapter.removeprefix("worker.")
            log = tmp_path / f"{name}.log"
            with log.open("wb") as handle:
                process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                    [
                        sys.executable,
                        str(BINDING),
                        "--port",
                        str(port),
                        "--agent",
                        agent.url,
                        "--capability",
                        CAPABILITY,
                        "--stores",
                        "eu",
                        "--state-dir",
                        str(tmp_path / f"{name}-state"),
                        "--estimate-seconds",
                        "5",
                        "--poll-seconds",
                        "0.05",
                    ],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, CREDENTIAL: token},
                )
            started.append(process)
            running[adapter] = Running(f"http://127.0.0.1:{port}", agent)
            wait_ready(process, f"{running[adapter].endpoint}/v1/health", log, name)
        yield running
    finally:
        for process in started:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for each in running.values():
            each.agent.stop()


def work(hosts: list[str]) -> dict[str, Any]:
    return {
        "task": {"goal": "draft the weekly report", "acceptance": ["a report exists"]},
        "max_steps": 20,
        "allowed_hosts": hosts,
        "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
    }


def bundle(hosts: list[str]) -> dict[str, Any]:
    """A process whose one step hands a report to whichever worker drafts one."""
    return {
        "id": "delegated-report",
        "version": "1",
        "name": "A report delegated to a foreign agent",
        "autonomy": {
            "level": 2,
            "reason": "a test process: every result is looked at",
            "toward_next": "nothing; it exists for the removal test",
        },
        "author": "the test",
        "reason": "the shape of a step a foreign agent serves",
        "limits": BUDGET,
        "steps": [
            {
                "id": "draft",
                "method": "worker",
                "reason": "drafting a report is what the agent offers",
                "rejected": [{"method": "rule", "why": "a report is not computed by a rule"}],
                "exactness": "free",
                "fallback": {"when": "no agent may be handed the report", "to": "human"},
                "requires": [CAPABILITY],
                "work": work(hosts),
            }
        ],
    }


async def run_on(pool: StaticWorkerPool, hosts: list[str]) -> Run:
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    engine = RunEngine(
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        provenance=MemoryProvenanceStore(persistence),
        workers=pool,
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        maturities=FakeMaturities(),
    )
    step = Step(
        id="draft",
        method=Method.WORKER,
        reason="drafting a report is what the agent offers",
        rejected=(),
        exactness=ExactnessClass.FREE,
        fallback=Fallback(when="no agent may be handed the report", to=Method.HUMAN),
        requires=(CAPABILITY,),
    )
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=(step,),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_operator", at=AT),
    )
    return await engine.start(
        StartRun(
            plan=plan,
            work={step.id: work(hosts)},
            budget=Limits.model_validate(BUDGET),
            process_version="delegated-report@1",
            actor="idn_operator",
            tenant="t",
        )
    )


async def test_a_run_hands_its_step_to_the_foreign_agent(bindings: dict[str, Running]) -> None:
    first = bindings[FIRST]
    pool = StaticWorkerPool([(FIRST, HttpWorker(first.endpoint))])
    run = await run_on(pool, [first.agent.host])
    assert run.state is RunState.FINISHED, run.reason
    (sent,) = first.agent.received
    assert sent["parts"][0]["text"].startswith("draft the weekly report")
    assert all(not task.further for task in first.agent.tasks.values())


async def test_withholding_the_binding_changes_the_step_to_the_other(
    bindings: dict[str, Running],
) -> None:
    hosts = [bindings[FIRST].agent.host, bindings[SECOND].agent.host]
    pool = StaticWorkerPool([(a, HttpWorker(bindings[a].endpoint)) for a in (FIRST, SECOND)])
    services = connector_services(FakeConnector(), workers=pool)
    await services.register_version.execute(
        RegisterProcessVersion(instructed(bundle(hosts)), tenant=TENANT)
    )
    run = await run_removal(services, FIRST)
    assert run.state is RunState.FINISHED, run.reason

    described = (await result_of(services, run, "describe"))["output"]
    assert described["family"] == "worker"
    assert described["alternatives"][CAPABILITY] == [SECOND]

    result = (await result_of(services, run, "exercise"))["output"]
    assert result["verdict"] == "changed", result
    (process,) = result["processes"]
    (finding,) = process["steps"]
    assert (finding["step"], finding["alternative"], finding["verdict"]) == (
        "draft",
        SECOND,
        "changed",
    )
    assert all(b.agent.received == [] for b in bindings.values()), (
        "a rehearsal hands no task to an agent"
    )

    async with services.work.transaction(TENANT):
        entries = list(await services.ledger.entries(TENANT))
    tested = [(e.adapter, e.outcome) for e in entries if e.kind == REMOVAL_TESTED]
    assert tested == [(FIRST, "changed")]
