"""The product finding against the fake repository service (issue #86; UC-6.12 §2; ADR-0046).

An engine runs plans over fakes of every port but one: the repository the findings go to is the
reference connector in process, in front of the fake service. A step meets something the product
lacks — no worker offers what it requires — and its run waits. The finding is sent, the same lack
is met again by another run, the lack is then configured away and both blocks end. What the
service holds afterwards is read back: one issue, two occurrences, the waiting summed, and in no
text a person, a project's content or a secret.

Never against the real repository: the connector's target is the fake's address.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers, FakeMaturities, FakeWorker

from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
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
from taktus.components.reporting.application.service import SENT, ProductFindings, Sending, Sent
from taktus.components.reporting.domain.service import texts
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.application.service import EngineOptions, ResumeRun, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service.ready import missing_sections
from taktus.composition.findings import RepositoryChannel, RunBlocks
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
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

from .conftest import Service

REPOSITORY = "acme/taktus"
TENANT = "t"
PERSON = "idn_operator"
AT = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
LACKING = "code.review"
GOAL = "Review the payroll export of the customer"
"""Content of the project: it must appear in no text the finding sends."""


def review(id: str) -> Step:
    return Step(
        id=id,
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=(LACKING,),
    )


class Pool(StaticWorkerPool):
    """The configured workers, to which the test adds one once the lack is configured away."""

    def add(self, adapter: str, worker: FakeWorker) -> None:
        self._workers.append((adapter, worker))


class World:
    def __init__(self, service: Service) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.pool = Pool([("worker.shell", FakeWorker())])  # offers shell.script, not the lack
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=self.pool,
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            maturities=FakeMaturities(),
        )
        self.accounts = BlockedTime(self.ledger, self.objects, self.persistence, self.runs)
        self.service = service

    def findings(self, *, sending: bool = True) -> ProductFindings:
        """A fresh connector each time: a restart, with no memory of what was sent before."""
        config = Config(target=self.service.url, repository=REPOSITORY, timeout=5.0)
        channel = RepositoryChannel(McpActionConnector(build_server(config), timeout=5.0))
        return ProductFindings(
            RunBlocks(self.accounts),
            Sending(channel, self.ledger, self.objects, self.persistence) if sending else None,
        )

    async def start(self, process: str) -> Run:
        step = review("review")
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal=GOAL,
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=PERSON, at=AT),
        )
        work = {"review": {"task": {"goal": GOAL, "acceptance": ["a"], "inputs": {"n": 1}}}}
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=work,
                budget=Limits(
                    compute=ComputeLimit(seconds=10, resource_class="cpu.small"),
                    quota=QuotaLimit(units=20),
                ),
                process_version=f"{process}@1",
                actor=PERSON,
                tenant=TENANT,
            )
        )

    async def resume(self, run: Run) -> Run:
        return await self.engine.resume(ResumeRun(run_id=run.id, actor=PERSON, tenant=TENANT))

    def later(self, by: timedelta) -> None:
        self.clock.current += by


async def held(w: World) -> Sequence[Any]:
    config = Config(target=w.service.url, repository=REPOSITORY, timeout=5.0)
    return await RepositoryChannel(McpActionConnector(build_server(config), timeout=5.0)).held(
        TENANT
    )


@pytest.mark.usefixtures("credentials")
async def test_one_lack_met_twice_is_one_issue_with_two_occurrences(service: Service) -> None:
    w = World(service)

    # A step needs a worker that offers what no configured worker offers: it fails, its run
    # escalates, and the step carries a block for the lack.
    first = await w.start("intake")
    assert first.state is RunState.ESCALATED
    step = first.step_run("review")
    assert step.state is StepState.FAILED and step.block is not None
    assert (step.block.cause, step.block.lacking) == ("no_worker", LACKING)

    assert await w.findings().send(TENANT) == Sent(opened=1)
    (issue,) = await held(w)
    assert issue.open and texts.MARK in issue.texts[0]
    assert missing_sections(issue.texts[0]) == [], "the issue has the form's sections"
    assert first.id in issue.texts[0] and "`review`" in issue.texts[0]
    assert "still waiting" in issue.texts[0]

    # The same lack, met by another run of another process ten minutes later.
    w.later(timedelta(minutes=10))
    second = await w.start("billing")
    assert second.state is RunState.ESCALATED
    assert await w.findings().send(TENANT) == Sent(added=1)

    # The lack is configured away; both runs resume five minutes later and their blocks end.
    w.later(timedelta(minutes=5))
    w.pool.add("worker.review", FakeWorker(capabilities_offered=(LACKING,)))
    for run in (first, second):
        assert (await w.resume(run)).state is RunState.FINISHED
    blocks = [b for b in await w.accounts.blocks(TENANT) if b.cause == "no_worker"]
    waited = sorted(b.seconds for b in blocks)
    assert waited[0] >= 300 and waited[1] >= 900, "each block lasted until its run resumed"
    assert await w.accounts.waiting(TENANT) == ()

    # Their ends are added to the same finding; nothing opens a second one.
    assert await w.findings().send(TENANT) == Sent(added=2)
    (issue,) = await held(w)
    known = texts.latest(texts.reported(issue.texts))
    assert len(known) == 2, "one issue, two occurrences"
    assert all(r.state == "ended" for r in known.values())
    total = sum(round(s) for s in waited)
    assert sum(r.seconds or 0 for r in known.values()) == total, "the waiting is summed"
    assert f"In all: 2 occurrences, {total} s waited over the 2 that ended." in issue.texts[-1]
    for run in (first, second):
        assert any(run.id in text for text in issue.texts), "each occurrence carries its run"

    # Sent again, and by a restarted instance: nothing new.
    assert await w.findings().send(TENANT) == Sent()
    assert len(await held(w)) == 1

    # No person, no content of the project, no secret value, in any text sent.
    for text in issue.texts:
        for forbidden in (PERSON, GOAL, "payroll", service.write_value, service.read_value):
            assert forbidden not in text

    # Every text sent is in the ledger, about its run and step.
    async with w.persistence.transaction(TENANT):
        sent = [e for e in await w.ledger.entries(TENANT) if e.kind == SENT]
    assert [e.outcome for e in sent] == ["opened", "added", "added", "added"]
    assert all(e.refs.actor is None and e.content_digest is not None for e in sent)


@pytest.mark.usefixtures("credentials")
async def test_an_instance_not_enabled_records_and_shows_and_sends_nothing(
    service: Service,
) -> None:
    w = World(service)
    run = await w.start("intake")
    assert run.state is RunState.ESCALATED
    findings = w.findings(sending=False)
    assert not findings.enabled
    assert await findings.send(TENANT) == Sent()
    assert await held(w) == []
    (finding,) = await findings.findings(TENANT)
    shown = texts.shown(finding)
    assert shown.startswith(f"Product finding: no worker offers {LACKING}")
    assert run.id in shown and PERSON not in shown and GOAL not in shown
