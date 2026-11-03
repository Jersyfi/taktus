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

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers, FakeMaturities, FakeWorker
from taktus_connectors.github.server import Config, build_server

from taktus.adapters.driven.clock import SystemRandomness
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
from taktus.components.reporting.application.service import (
    DISABLED,
    ENABLED,
    SENT,
    Kept,
    ProductFindings,
    Sending,
    Sent,
)
from taktus.components.reporting.domain.service import leaving, texts
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.application.service import EngineOptions, ResumeRun, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service.ready import missing_sections
from taktus.composition.findings import READ_KEY, RepositoryChannel, RunBlocks, RunContent
from taktus.ports.connector import CallContext
from taktus.ports.worker import ComputeLimit, CredentialReference, Limits, QuotaLimit
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
ROOT = Path(__file__).resolve().parents[3]
FORM = texts.form((ROOT / ".github" / "finding-form.md").read_text(encoding="utf-8"))
"""A configured form: the sections of one repository's issue form `Task`, which its operator
gives the instance (`TAKTUS_FINDINGS_FORM`, ADR-0092)."""
TENANT = "t"
PERSON = "idn_operator"
AT = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
LACKING = "code.review"
GOAL = "Review the payroll export of the customer"
"""Content of the project: it must appear in no text the finding sends."""


def review(id: str, lacking: str = LACKING) -> Step:
    return Step(
        id=id,
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=(lacking,),
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
        channel = RepositoryChannel(
            McpActionConnector(build_server(config), timeout=5.0), labels=("task",)
        )
        return ProductFindings(
            RunBlocks(self.accounts),
            Kept(
                self.ledger,
                self.objects,
                self.persistence,
                SystemRandomness(),
                RunContent(self.runs, self.persistence),
            ),
            Sending(channel, self.service.url) if sending else None,
            shape=FORM,
        )

    async def start(
        self,
        process: str,
        *,
        step_id: str = "review",
        lacking: str = LACKING,
        goal: str = GOAL,
        inputs: Mapping[str, Any] | None = None,
        run_id: str | None = None,
    ) -> Run:
        step = review(step_id, lacking)
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal=goal,
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=PERSON, at=AT),
        )
        work = {step_id: {"task": {"goal": goal, "acceptance": ["a"], "inputs": {"n": 1}}}}
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
                inputs=inputs or {},
                run_id=run_id,
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
    assert missing_sections(issue.texts[0]) == [], "the issue has the configured form's sections"
    named = await w.findings().pseudonyms(TENANT)
    assert named.run(first.id) in issue.texts[0] and named.step("review") in issue.texts[0]
    assert first.id not in issue.texts[0], "the run leaves by pseudonym (ADR-0112)"
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
    assert (
        f"In all: 2 occurrences from 1 sender, {total} s waited over the 2 that ended."
        in issue.texts[-1]
    )
    for run in (first, second):
        assert any(named.run(run.id) in text for text in issue.texts), "each carries its run"

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
    async with w.persistence.transaction(TENANT):
        kinds = {e.kind for e in await w.ledger.entries(TENANT)}
    assert not kinds & {ENABLED, DISABLED, SENT}, "off by default: nothing enabled, nothing sent"
    (one,) = await findings.outgoing(TENANT)
    shown = one.text
    assert "### What must be achieved" in shown, "shown in the configured form"
    assert shown.startswith(f"Product finding: no worker offers {LACKING}")
    named = await findings.pseudonyms(TENANT)
    assert named.run(run.id) in shown and PERSON not in shown and GOAL not in shown
    assert one.finding.occurrences[0].run_id == run.id, "the operator can tell which run it is"


CUSTOMER = "Erika Mustermann"
AMOUNT = "4.711,00 EUR"
ADDRESS = "Heidestraße 17, 51147 Köln"


@pytest.mark.usefixtures("credentials")
async def test_a_finding_from_an_instance_outside_carries_nothing_of_its_tenant(
    service: Service,
) -> None:
    """Issue #446: a customer's name, an amount and an address planted in a run — in what it
    was given, in its goal and its work, in the run's and the step's identifiers — reach no
    text of the issue."""
    w = World(service)
    goal = f"Bill {CUSTOMER} {AMOUNT} at {ADDRESS}"
    run = await w.start(
        "billing",
        step_id="bill-erika-mustermann",
        goal=goal,
        inputs={"customer": CUSTOMER, "amount": AMOUNT, "address": ADDRESS},
        run_id="run_erika-mustermann-4711",
    )
    assert run.state is RunState.ESCALATED
    assert await w.findings().send(TENANT) == Sent(opened=1)
    (issue,) = await held(w)
    config = Config(target=w.service.url, repository=REPOSITORY, timeout=5.0)
    listed = await McpActionConnector(build_server(config), timeout=5.0).call(
        "repository.issues.list",
        CallContext(
            tenant=TENANT,
            identity="taktus",
            run_id="read",
            step_id="read",
            attempt=1,
            idempotency_key=READ_KEY,
            credentials=(CredentialReference(name="REPOSITORY_TOKEN", injected_as="env"),),
        ),
        {"state": "all"},
    )
    titles = [str(i.get("title", "")) for i in listed.output["issues"]]
    everything = "\n".join([*titles, *issue.texts])
    folded = leaving.fold(everything)
    for planted in (CUSTOMER, AMOUNT, ADDRESS, "Mustermann", "Heidestraße", "51147", "4711"):
        assert planted not in everything and leaving.fold(planted) not in folded, planted
    assert leaving.check([everything], leaving.values([CUSTOMER, AMOUNT, ADDRESS])) == ()


@pytest.mark.usefixtures("credentials")
async def test_a_lack_that_names_the_tenants_content_is_withheld_and_shown(
    service: Service,
) -> None:
    w = World(service)
    await w.start("billing", lacking="crm.erika-mustermann", inputs={"customer": CUSTOMER})
    findings = w.findings()
    assert await findings.send(TENANT) == Sent(withheld=1)
    assert await held(w) == [], "nothing of it left the instance"
    (one,) = await findings.outgoing(TENANT)
    assert [m.kind for m in one.withheld] == ["tenant_value"]


@pytest.mark.usefixtures("credentials")
async def test_the_same_lack_on_two_instances_is_one_finding(service: Service) -> None:
    """Two instances outside the project, each its own state, send to the same repository:
    the second adds an occurrence to the finding the first opened, under its own sender."""
    one, other = World(service), World(service)
    await one.start("intake")
    other.later(timedelta(minutes=3))
    await other.start("intake")
    assert await one.findings().send(TENANT) == Sent(opened=1)
    assert await other.findings().send(TENANT) == Sent(added=1)
    (issue,) = await held(one)
    senders = {r.source for r in texts.reported(issue.texts)}
    first = await one.findings().pseudonyms(TENANT)
    second = await other.findings().pseudonyms(TENANT)
    assert senders == {first.source, second.source} and len(senders) == 2
    assert "In all: 2 occurrences from 2 senders" in issue.texts[-1]
    assert (
        await one.findings().send(TENANT) == Sent()
        and await other.findings().send(TENANT) == Sent()
    )
