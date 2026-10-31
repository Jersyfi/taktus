"""The invoice-to-payment blueprint's first process, B-10.03, end to end against fakes of an
inbox and an accounting system (UC-04, ADR-0169, ADR-0170, UC-03 B-10.03 and B-6.06).

What is real: the bundle as shipped (`blueprints/invoice-to-payment/processes/
B-10.03-incoming-invoice.yaml`), registration, the run engine over memory stores, the documents
and the accounting connectors served over MCP, the `invoice` rule, the shipped anchors and the
decision requests, wired as the daemon wires them. What is faked: the inbox folder over WebDAV
(`tests/fakes/document_inbox_service.py`), the accounting interface
(`tests/fakes/accounting_service.py`) and the owner's chat.

What is proven: an invoice that holds is read, checked and proposed for booking once a person
confirmed the proposal (the action at level 2 of a level-3 process); the payment then halts at
the legal anchor whatever the level, and is handed to the payment run only after a person
decided, with the amount the rule computed. An invoice whose account to be paid differs from
the one the books hold goes to a person, and nothing is booked or paid. A tenant's risk class
at level 1 holds the booking at level 1 in this process without editing the bundle.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fakes import FakeIdentifiers, FakeWorker, accounting_service, document_inbox_service
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT, owner_channel, people
from taktus_connectors.accounting.operations import Config as AccountingConfig
from taktus_connectors.accounting.server import build_server as accounting_server
from taktus_connectors.einvoice.operations import Config as InboxConfig
from taktus_connectors.einvoice.server import build_server as inbox_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.decision.application.service import AnswerRequest, ConfirmRequest
from taktus.components.governance.application.service import ConfigureAnchors
from taktus.components.governance.domain.model.anchors import SHIPPED_ANCHORS
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import (
    ConfirmSteps,
    DecideSteps,
    EngineOptions,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.ports.worker import Limits
from taktus.shared.v1 import Commissioned, Plan, PlanResult, PlanStatus

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "blueprints" / "invoice-to-payment" / "processes" / "B-10.03-incoming-invoice.yaml"
TOKEN = "tok-" + secrets.token_hex(12)


def _serve(make: Any) -> Iterator[str]:
    server = make("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DOCUMENTS_TOKEN", "ACCOUNTING_TOKEN"):
        path = tmp_path / name
        path.write_text(TOKEN, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))


@pytest.fixture
def inbox() -> Iterator[str]:
    yield from _serve(document_inbox_service.make_server)


@pytest.fixture
def books() -> Iterator[str]:
    yield from _serve(accounting_service.make_server)


class World:
    def __init__(self, inbox: str, books: str) -> None:
        self.books = books
        self.given = owner_channel()
        self.persistence = self.given.persistence
        self.clock = self.given.clock
        self.objects = MemoryObjectStore()
        self.ledger = self.given.identity.ledger
        self.decisions = self.given.decisions
        documents = McpActionConnector(inbox_server(InboxConfig(inbox, timeout=5.0)), timeout=10.0)
        accounting = McpActionConnector(
            accounting_server(AccountingConfig(books, timeout=5.0)), timeout=10.0
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(
                [("connector.documents", documents), ("connector.accounting", accounting)]
            ),
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
            levels=self.decisions.levels,
        )
        self.register = RegisterProcessVersionHandler(
            self.of(ProcessVersion), self.persistence, self.of(Process), ledger=self.ledger,
            clock=self.clock,
        )  # fmt: skip
        self.version: ProcessVersion | None = None

    def of(self, kind: Any) -> Any:
        return MemoryRepository(self.persistence, kind)

    async def ready(self) -> World:
        await people(self.given)
        bundle = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
        self.version = await self.register.execute(RegisterProcessVersion(bundle, tenant=TENANT))
        return self

    async def start(self, document: str) -> Run:
        version = self.version
        assert version is not None
        plan = Plan(
            id="pln_invoice",
            command_id="cmd_invoice",
            goal="check and pay one incoming invoice",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=OWNER, at=self.clock.current),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=OWNER,
                tenant=TENANT,
                inputs={"document": document},
                actions=version.autonomy.action_levels,
            )
        )

    async def confirm(self, run: Run, step: str) -> Run:
        return await self.engine.confirm(
            ConfirmSteps(run_id=run.id, steps=(step,), actor=OWNER, tenant=TENANT)
        )

    async def release(self, run: Run, step: str) -> Run:
        anchoring = run.step_run(step).anchoring
        assert anchoring is not None
        (request_id,) = anchoring.requests
        await self.decisions.answer.execute(
            AnswerRequest(tenant=TENANT, request_id=request_id, identity=OWNER, option="A")
        )
        await self.decisions.confirm.execute(
            ConfirmRequest(tenant=TENANT, request_id=request_id, identity=OWNER, confirmed=True)
        )
        return await self.engine.decide(DecideSteps(run_id=run.id, actor=OWNER, tenant=TENANT))

    async def result(self, run: Run, step: str) -> Any:
        checkpoint = run.step_run(step).checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None
        return json.loads(await self.objects.get(checkpoint.result_digest) or b"null")

    def held(self) -> dict[str, Any]:
        state: dict[str, Any] = httpx.get(f"{self.books}/_fake/state", timeout=5.0).json()
        return state


def states(run: Run) -> dict[str, StepState]:
    return {s.step_id: s.state for s in run.step_runs}


async def test_an_invoice_that_holds_is_booked_on_confirmation_and_paid_only_on_release(
    inbox: str, books: str
) -> None:
    w = await World(inbox, books).ready()
    run = await w.start("invoice-ubl.xml")

    # Level 3 reads and checks; the booking proposal, at level 2, waits for a person.
    assert run.state is RunState.WAITING_HUMAN
    assert states(run)["check"] is StepState.SUCCEEDED
    assert states(run)["propose-booking"] is StepState.WAITING_HUMAN
    checked = await w.result(run, "check")
    assert (checked["net"], checked["tax"], checked["gross"], checked["payable"]) == (
        "100.00",
        "19.00",
        "119.00",
        "119.00",
    )
    assert checked["account"] == "4930"
    assert w.held()["bookings"] == []
    booking = run.step_run("propose-booking")
    assert booking.reason is not None and "held by the action accounting.bookings" in booking.reason

    # Confirmed, the proposal is handed over; the release halts at the legal anchor.
    run = await w.confirm(run, "propose-booking")
    assert run.state is RunState.WAITING_HUMAN
    assert states(run)["release-payment"] is StepState.WAITING_HUMAN
    held = w.held()
    assert [b["gross"] for b in held["bookings"]] == ["119.00"] and held["payments"] == []
    anchoring = run.step_run("release-payment").anchoring
    assert anchoring is not None and anchoring.requests, "a decision request, not a confirmation"

    # Released by a person, the payment is submitted with the rule's amount, once.
    run = await w.release(run, "release-payment")
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    (payment,) = w.held()["payments"]
    assert payment["amount"] == "119.00" and payment["booking"] == held["bookings"][0]["id"]
    assert "account" not in payment, "the system pays the account it holds"


async def test_an_invoice_whose_payee_differs_from_the_books_goes_to_a_person(
    inbox: str, books: str
) -> None:
    orders = accounting_service.default_orders()
    orders["PO-8"]["supplier"]["account"] = "DE02120300000000202051"
    async with httpx.AsyncClient(timeout=5.0) as client:
        await client.post(f"{books}/_fake/orders", content=json.dumps(orders))
    w = await World(inbox, books).ready()
    run = await w.start("invoice-cii.xml")
    assert run.state is RunState.ESCALATED, "the step's fallback is a person, who is told why"
    check = run.step_run("check")
    assert check.state is StepState.FAILED
    assert check.reason is not None and "account to be paid" in check.reason
    assert states(run)["propose-booking"] is StepState.PLANNED
    assert w.held()["bookings"] == [] and w.held()["payments"] == []


async def test_a_tenant_caps_the_booking_without_editing_the_bundle(inbox: str, books: str) -> None:
    w = await World(inbox, books).ready()
    await w.decisions.configure.execute(
        ConfigureAnchors(
            tenant=TENANT,
            document={
                "anchors": [a.document() for a in SHIPPED_ANCHORS],
                "risk_classes": {"books": ["accounting.bookings.*"]},
                "levels": {"books": 1},
            },
            actor=OWNER,
        )
    )
    run = await w.start("invoice-ubl.xml")
    assert run.actions["accounting.bookings.propose"] == 1
    booking = run.step_run("propose-booking")
    assert booking.state is StepState.WAITING_HUMAN
    assert booking.reason is not None and "level 1" in booking.reason
    assert w.held()["bookings"] == [], "at level 1 Taktus proposes and a person acts"
