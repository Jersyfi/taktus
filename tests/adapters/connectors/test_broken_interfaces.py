"""A broken interface, noticed from Taktus's own calls, against the fake repository service
(issue #100, ADR-0047, DEC-0058).

An engine runs plans whose one step reads an issue through the reference repository connector,
in process, in front of the fake service. The fake is then made to answer as an interface that
changed would: a shape the connector does not foresee, a status that should not occur, an
authentication refused. The owner-facing channel is the one the composition root wires, with a
carrier that records what it was told to deliver (`fakes/owner_channel.py`).

Never against the real repository: the connector's target is the fake's address.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fakes import FakeIdentifiers
from fakes.maturity import VERIFIED
from fakes.owner_channel import CHANNEL, OwnerChannel, owner_channel

from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.reporting.application.service import BrokenInterfaces, Reported
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.run.application.service import ResumeRun, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.interfaces import broken_interfaces
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

from .conftest import WRITE_CREDENTIAL, Service

REPOSITORY = "acme/taktus"
TENANT = "t"
PERSON = "idn_operator"
INTERFACE = "connector.repository"
GOAL = "Triage the payroll export of the customer"
"""Content of the project: it must appear in no report."""


class World:
    def __init__(self, service: Service, given: OwnerChannel) -> None:
        self.service = service
        self.given = given
        persistence = given.persistence
        config = Config(target=service.url, repository=REPOSITORY, timeout=5.0)
        self.engine = RunEngine(
            runs=MemoryRepository(persistence, Run),
            work=persistence,
            objects=MemoryObjectStore(),
            ledger=given.identity.ledger,
            provenance=MemoryProvenanceStore(persistence),
            workers=StaticWorkerPool([]),
            clock=given.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            maturities=VERIFIED,
            connectors=StaticConnectorPool(
                [(INTERFACE, McpActionConnector(build_server(config), timeout=5.0))]
            ),
        )
        self.broken: BrokenInterfaces = broken_interfaces(
            given.identity.ledger, persistence, given.owner, given.clock
        )

    def answer(self, status: int | None, body: Any = None) -> None:
        """The fake answers every request with this status and body; None switches it off."""
        self.service.control(
            "/_fake/answer", {} if status is None else {"status": status, "body": body}
        )

    async def start(self, process: str) -> Run:
        step = Step(
            id="read-issue",
            method=Method.RULE,
            reason="r",
            rejected=(),
            exactness=ExactnessClass.SOURCED,
        )
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal=GOAL,
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=PERSON, at=self.given.clock.now()),
        )
        work = {
            "read-issue": {
                "rule": "connector",
                "operation": "repository.issues.read",
                "input": {"number": 1},
                "credentials": [{"name": WRITE_CREDENTIAL, "injected_as": "env"}],
            }
        }
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

    def later(self, minutes: int) -> None:
        self.given.clock.current += timedelta(minutes=minutes)


@pytest.fixture
def issue(service: Service, credentials: None) -> None:
    """Issue #1 exists, so that a read of it succeeds while the service behaves."""
    httpx.post(
        f"{service.url}/repos/{REPOSITORY}/issues",
        json={"title": "An issue", "body": "b"},
        headers={"Authorization": f"Bearer {service.write_value}"},
        timeout=5.0,
    ).raise_for_status()


@pytest.mark.usefixtures("issue")
async def test_failures_the_contract_does_not_foresee_make_one_report_per_interface_and_cause(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = World(service, owner_channel())
    await w.given.configure()

    healthy = await w.start("triage")
    assert healthy.state is RunState.FINISHED

    # A shape the connector does not foresee, then a status that should not occur.
    w.answer(200, {"unexpected": "shape"})
    shape = await w.start("triage")
    w.later(5)
    w.answer(418, {"message": "I'm a teapot"})
    status = await w.start("billing")
    w.later(5)
    w.answer(None)
    # An authentication refused: the credential's value is no longer accepted.
    monkeypatch.setenv(WRITE_CREDENTIAL, "revoked-" + service.read_value)
    refused = [await w.start("triage"), await w.start("intake")]
    for run in (shape, status, *refused):
        assert run.state is RunState.ESCALATED
    for run in (shape, status):
        assert "unexpected" in (run.step_run("read-issue").reason or "")

    # One broken interface per interface and cause, not one per call.
    noticed = await w.broken.noticed(TENANT)
    assert [(n.found.interface, n.found.cause, len(n.found.calls)) for n in noticed] == [
        (INTERFACE, "unexpected", 2),
        (INTERFACE, "unauthenticated", 2),
    ]
    unexpected, _ = (n.found for n in noticed)
    assert (unexpected.first.run_id, unexpected.last.run_id) == (shape.id, status.id)
    assert unexpected.first.step_id == unexpected.last.step_id == "read-issue"
    assert unexpected.first.at < unexpected.last.at

    # Each reaches the configured channel once, with the run, the step, first and last.
    assert await w.broken.report(TENANT) == Reported(raised=2, delivered=2)
    said = w.given.deliveries.said
    assert [s.channel for s in said] == [CHANNEL, CHANNEL]
    first_message = said[0].text
    assert unexpected.id in first_message
    for run in (shape, status):
        assert run.id in first_message
    assert "read-issue" in first_message
    assert unexpected.first.at.isoformat(timespec="seconds") in first_message
    assert unexpected.last.at.isoformat(timespec="seconds") in first_message
    assert all(r.id in said[1].text for r in refused)

    # A later failure adds to the broken interface; nothing is said again.
    w.later(5)
    again = await w.start("triage")
    assert again.state is RunState.ESCALATED
    assert await w.broken.report(TENANT) == Reported()
    assert len(w.given.deliveries.said) == 2
    noticed = await w.broken.noticed(TENANT)
    assert [len(n.found.calls) for n in noticed] == [2, 3]
    assert all(n.delivered for n in noticed)

    # The reports are of kind failure, carry no person, no content and no secret.
    reports = await w.given.owner.queries.reports(TENANT)
    assert {r.kind for r in reports} == {ReportKind.FAILURE}
    for text in (s.text for s in said):
        for forbidden in (PERSON, GOAL, "payroll", service.write_value, service.read_value):
            assert forbidden not in text


@pytest.mark.usefixtures("issue")
async def test_a_transient_failure_a_retry_resolves_raises_nothing(service: Service) -> None:
    w = World(service, owner_channel())
    await w.given.configure()

    service.control("/_fake/outage", {"on": True})
    try:
        run = await w.start("triage")
    finally:
        service.control("/_fake/outage", {"on": False})
    assert run.state is RunState.ESCALATED
    assert "unavailable" in (run.step_run("read-issue").reason or "")
    resumed = await w.resume(run)
    assert resumed.state is RunState.FINISHED

    assert await w.broken.noticed(TENANT) == ()
    assert await w.broken.report(TENANT) == Reported()
    assert w.given.deliveries.said == []


@pytest.mark.usefixtures("issue")
async def test_a_transient_failure_a_retry_does_not_resolve_is_reported(service: Service) -> None:
    w = World(service, owner_channel())
    await w.given.configure()

    service.control("/_fake/outage", {"on": True})
    try:
        run = await w.start("triage")
        assert await w.broken.noticed(TENANT) == (), "one failure is not yet a broken interface"
        w.later(10)
        run = await w.resume(run)
    finally:
        service.control("/_fake/outage", {"on": False})
    assert run.state is RunState.ESCALATED

    (one,) = await w.broken.noticed(TENANT)
    assert (one.found.cause, len(one.found.calls)) == ("unavailable", 2)
    assert await w.broken.report(TENANT) == Reported(raised=1, delivered=1)


@pytest.mark.usefixtures("issue")
async def test_without_a_channel_it_is_recorded_shown_and_says_it_was_not_delivered(
    service: Service,
) -> None:
    w = World(service, owner_channel())  # no owner-facing channel configured
    w.answer(404, {"message": "Not Found"})  # foreseen: the service answers about the input
    assert (await w.start("triage")).state is RunState.ESCALATED
    w.answer(301, {"message": "Moved Permanently"})
    run = await w.start("triage")
    w.answer(None)
    assert run.state is RunState.ESCALATED

    assert await w.broken.report(TENANT) == Reported()
    assert w.given.deliveries.said == []
    (one,) = await w.broken.noticed(TENANT)
    assert one.found.cause == "unexpected" and one.found.first.run_id == run.id
    assert not one.delivered and one.reason == "no_channel"
    shown = one.text()
    assert "not delivered" in shown and "owner-facing channel" in shown
    assert run.id in shown and INTERFACE in shown

    # Recorded: once a channel is configured, the next look reports it.
    await w.given.configure()
    assert await w.broken.report(TENANT) == Reported(raised=1, delivered=1)
