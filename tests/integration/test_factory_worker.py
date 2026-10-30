"""A whole software factory as a worker: residency holds and removal changes, it breaks nothing
(#411, ADR-0157, UC-8.15).

Two factory workers run as processes behind the worker contract, each against a stand-in factory
of its own (`tests/fakes/factory_service.py`): `worker.factory` hands its tasks to a factory that
stores elsewhere, `worker.factory-eu` to one that stores in the European Union. Both offer
`change.implement`.

- A tenant whose residency rule is `eu` is never handed to the factory that stores elsewhere:
  the step runs on the other, and the first factory receives nothing. With only that factory
  configured, the step fails before anything is sent, naming the rule (principle 11).
- The removal test S-01 withholds `worker.factory`. The step it served is served by the other,
  which the finding names as its alternative, and the verdict is *changed*. The step reaches a
  factory's host, so the rehearsals do not run it for real (ADR-0030): the verdict rests on
  which worker would serve it.

What is not proven here: a real factory, which needs its operator's credential and profile.
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
from fakes.factory_service import FakeFactory

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
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.ports.model import Permitted
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

ABROAD = "worker.factory"
INSIDE = "worker.factory-eu"
WORKER = ROOT / "workers" / "factory" / "worker.py"
CREDENTIAL = "FACTORY_TOKEN"
AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


@dataclass
class Running:
    endpoint: str
    factory: FakeFactory


@pytest.fixture
def factories(tmp_path: Path) -> Iterator[dict[str, Running]]:
    """Both factory workers, each against its own stand-in factory with a token of its own."""
    started: list[subprocess.Popen[bytes]] = []
    running: dict[str, Running] = {}
    try:
        for adapter, stores in ((ABROAD, "elsewhere"), (INSIDE, "eu")):
            token = "fake-" + secrets.token_hex(8)
            factory = FakeFactory(token=token, stage_seconds=0.1, stage_cost=0.2).start()
            port = free_port()
            name = adapter.removeprefix("worker.")
            log = tmp_path / f"{name}.log"
            with log.open("wb") as handle:
                process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                    [
                        sys.executable,
                        str(WORKER),
                        "--port",
                        str(port),
                        "--factory",
                        factory.url,
                        "--stores",
                        stores,
                        "--state-dir",
                        str(tmp_path / f"{name}-state"),
                        "--estimate-amount",
                        "1.0",
                        "--poll-seconds",
                        "0.05",
                    ],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, CREDENTIAL: token},
                )
            started.append(process)
            running[adapter] = Running(f"http://127.0.0.1:{port}", factory)
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
            each.factory.stop()


def work(hosts: list[str]) -> dict[str, Any]:
    return {
        "task": {"goal": "write hello", "acceptance": ["hello.txt exists"]},
        "max_steps": 20,
        "allowed_hosts": hosts,
        "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
    }


def bundle(hosts: list[str]) -> dict[str, Any]:
    """A process whose one step delegates a change to whichever worker implements one."""
    return {
        "id": "delegated-change",
        "version": "1",
        "name": "A change delegated to a software factory",
        "autonomy": {
            "level": 2,
            "reason": "a test process: every result is looked at",
            "toward_next": "nothing; it exists for the removal test",
        },
        "author": "the test",
        "reason": "the shape of a step a software factory serves",
        "limits": {"currency": {"eur": 5.0}},
        "steps": [
            {
                "id": "implement",
                "method": "worker",
                "reason": "a change implemented as a whole is what a factory offers",
                "rejected": [{"method": "llm", "why": "a completion changes no repository"}],
                "exactness": "tolerant",
                "fallback": {"when": "no factory may be handed the change", "to": "human"},
                "requires": ["change.implement"],
                "work": work(hosts),
            }
        ],
    }


class Rule:
    def __init__(self, own: Permitted) -> None:
        self.own = own

    async def permitted(self, tenant: str, data_class: str | None) -> Permitted:
        return self.own


async def run_under(pool: StaticWorkerPool, rule: Rule, hosts: list[str]) -> Run:
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
        residency=rule,
    )
    step = Step(
        id="implement",
        method=Method.WORKER,
        reason="a change implemented as a whole is what a factory offers",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="no factory may be handed the change", to=Method.HUMAN),
        requires=("change.implement",),
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
            budget=Limits.model_validate({"currency": {"eur": 5.0}}),
            process_version="delegated-change@1",
            actor="idn_operator",
            tenant="t",
        )
    )


async def test_an_eu_tenant_is_never_handed_to_a_factory_that_stores_elsewhere(
    factories: dict[str, Running],
) -> None:
    abroad, inside = factories[ABROAD], factories[INSIDE]
    hosts = [abroad.factory.host, inside.factory.host]
    pool = StaticWorkerPool(
        [(ABROAD, HttpWorker(abroad.endpoint)), (INSIDE, HttpWorker(inside.endpoint))]
    )
    run = await run_under(pool, Rule("eu"), hosts)
    assert run.state is RunState.FINISHED, run.reason
    assert abroad.factory.submissions == [], "nothing reached the factory outside the rule"
    assert len(inside.factory.submissions) == 1

    alone = StaticWorkerPool([(ABROAD, HttpWorker(abroad.endpoint))])
    run = await run_under(alone, Rule("eu"), hosts)
    step_run = run.step_run("implement")
    assert step_run.state is StepState.FAILED
    assert "residency rule admits (eu)" in (step_run.reason or "")
    assert abroad.factory.submissions == []


async def test_withholding_the_factory_changes_the_step_to_the_other(
    factories: dict[str, Running],
) -> None:
    hosts = [factories[ABROAD].factory.host, factories[INSIDE].factory.host]
    pool = StaticWorkerPool([(a, HttpWorker(factories[a].endpoint)) for a in (ABROAD, INSIDE)])
    services = connector_services(FakeConnector(), workers=pool)
    await services.register_version.execute(RegisterProcessVersion(bundle(hosts), tenant=TENANT))
    run = await run_removal(services, ABROAD)
    assert run.state is RunState.FINISHED, run.reason

    described = (await result_of(services, run, "describe"))["output"]
    assert described["family"] == "worker"
    assert described["alternatives"]["change.implement"] == [INSIDE]

    result = (await result_of(services, run, "exercise"))["output"]
    assert result["verdict"] == "changed", result
    (process,) = result["processes"]
    (finding,) = process["steps"]
    assert (finding["step"], finding["alternative"], finding["verdict"]) == (
        "implement",
        INSIDE,
        "changed",
    )
    assert all(f.factory.submissions == [] for f in factories.values()), (
        "a rehearsal hands no task to a factory"
    )

    async with services.work.transaction(TENANT):
        entries = list(await services.ledger.entries(TENANT))
    tested = [(e.adapter, e.outcome) for e in entries if e.kind == REMOVAL_TESTED]
    assert tested == [(ABROAD, "changed")]
