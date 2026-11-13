"""Partner interfaces under a data contract, at run time (UC-15.3, ADR-0273, ADR-0303), over the
memory stores.

What is real: registration with its contract rule, the run engine with its checks, residency
rule and egress entries, the escalation watch and the owner-facing channel as the composition
root wires them, the governance component's situation package. What stands in: the partner's
system and the organisation's own, a fake connector built from the action port's contract.

What is proven: an import whose message lacks a field the contract requires is escalated with
that field and the clause it breaks, and nothing after the check maps, completes or guesses it;
an export whose document breaks its contract is not sent, at run time; a document that holds it
is sent, and the send is recorded as data that has left the system with the location it went
to; partner data is held to the tenant's residency rule — a partner exchange through a connector
outside it reads and sends nothing.
"""

from __future__ import annotations

from typing import Any

from fakes import FakeConnector, FakeIdentifiers
from fakes.connector import READ, WRITE
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT, owner_channel
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryObjectStore, MemoryProvenanceStore, MemoryRepository
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.escalations import EscalationWatch, report_id
from taktus.ports.model import Location, Permitted
from taktus.ports.worker import Limits
from taktus.shared.v1 import EGRESS_KINDS, Commissioned, Plan, PlanResult, PlanStatus

FIELDS = ["number", "issue_date", "currency", "seller"]
INVOICE = {"number": "R-1", "issue_date": "2026-11-01", "currency": "EUR", "seller": "S"}
LACKING = {k: v for k, v in INVOICE.items() if k != "currency"}
RESPONSIBLE = {"ours": "owner", "theirs": "the supplier's accounts receivable"}


def contract(direction: str, steps: list[str]) -> dict[str, Any]:
    return {
        "partner": "a supplier",
        "direction": direction,
        "standard": "EN 16931",
        "fields": [{"name": f} for f in FIELDS],
        "responsible": RESPONSIBLE,
        "steps": steps,
    }


def shape() -> list[dict[str, Any]]:
    return [{"kind": "source_shape", "columns": FIELDS}]


def importing() -> dict[str, Any]:
    """A supplier's invoice read through a connector, checked against the contract, then
    mapped into the organisation's own data."""
    return instructed(
        {
            "id": "supplier-invoice-in",
            "version": "1",
            "name": "Receive a supplier's invoice",
            "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
            "limits": {"quota": {"units": 10}},
            "contracts": {"supplier-invoices": contract("import", ["read"])},
            "steps": [
                {
                    "id": "read",
                    "method": "rule",
                    "reason": "the partner's message is read as it is",
                    "rejected": [],
                    "exactness": "sourced",
                    "checks": shape(),
                    "work": {
                        "checking": {"select": "output"},
                        "rule": "connector",
                        "operation": READ,
                        "input": {"id": "R-1"},
                        "data_class": "partner",
                    },
                },
                {
                    "id": "map",
                    "method": "rule",
                    "reason": "the message's fields map onto the organisation's own by rule",
                    "rejected": [],
                    "exactness": "exact",
                    "checks": [{"kind": "recomputation"}],
                    "depends_on": ["read"],
                    "work": {"rule": "constant", "value": {"booked": True}},
                },
            ],
        }
    )


def exporting(document: dict[str, Any]) -> dict[str, Any]:
    """An invoice to a customer prepared, checked against the contract, then sent."""
    return instructed(
        {
            "id": "customer-invoice-out",
            "version": "1",
            "name": "Send an invoice to a customer",
            "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
            "limits": {"quota": {"units": 10}},
            "contracts": {
                "customer-invoices": {
                    **contract("export", ["send"]),
                    "partner": "a customer",
                    "responsible": {"ours": "owner", "theirs": "the customer's accounts payable"},
                }
            },
            "steps": [
                {
                    "id": "prepare",
                    "method": "rule",
                    "reason": "the invoice document is assembled by rule",
                    "rejected": [],
                    "exactness": "sourced",
                    "checks": shape(),
                    "work": {"rule": "constant", "value": document},
                },
                {
                    "id": "send",
                    "method": "rule",
                    "reason": "the checked document is sent through the partner's channel",
                    "rejected": [],
                    "exactness": "tolerant",
                    "depends_on": ["prepare"],
                    "work": {
                        "rule": "connector",
                        "operation": WRITE,
                        "input": {"document": "R-1"},
                        "data_class": "partner",
                    },
                },
            ],
        }
    )


class Rule:
    """A tenant's residency rule that narrows partner data to `partner`."""

    def __init__(self, partner: Permitted) -> None:
        self.partner = partner

    async def permitted(
        self, tenant: str, data_class: str | None, process: str | None = None
    ) -> Permitted:
        return self.partner if data_class == "partner" else "anywhere"


class World:
    def __init__(self, *, location: Location = "eu", rule: Rule | None = None) -> None:
        self.given = owner_channel()
        self.persistence = self.given.persistence
        self.clock = self.given.clock
        self.ledger = self.given.identity.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.partner = FakeConnector()
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            connectors=StaticConnectorPool(
                [("connector.partner", self.partner)],
                locations={"connector.partner": location},
            ),
            residency=rule,
            options=EngineOptions(uncalibrated_margin=0.0),
        )
        self.register = RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
        )
        self.watch = EscalationWatch(
            ledger=self.ledger,
            runs=self.runs,
            versions=self.versions,
            work=self.persistence,
            clock=self.clock,
            channels=self.given.owner.channel,
            raising=self.given.owner.raising,
            reports=self.given.owner.queries,
        )

    async def run(self, bundle: dict[str, Any]) -> Run:
        await self.given.configure()
        version = await self.register.execute(
            RegisterProcessVersion(bundle, tenant=TENANT, by=OWNER)
        )
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal=version.name,
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=OWNER, at=self.clock.now()),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=OWNER,
                tenant=TENANT,
            )
        )

    async def kinds(self, run: Run) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [e.kind for e in await self.ledger.entries(TENANT, run.id)]

    async def outcomes(self, run: Run, kind: str) -> list[str | None]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT, run.id)
        return [e.outcome for e in entries if e.kind == kind]


async def test_a_deviating_import_is_escalated_with_the_field_and_the_clause_it_breaks() -> None:
    w = World()
    w.partner.reads["R-1"] = LACKING
    run = await w.run(importing())
    assert run.state is RunState.ESCALATED
    assert run.step_run("read").state is StepState.FAILED
    assert run.step_run("map").state is StepState.PLANNED, "nothing of the message is mapped"
    await w.watch.look(TENANT)
    report = await w.given.owner.queries.one(TENANT, report_id(run.id, 1))
    assert report is not None
    assert "the field 'currency' is missing" in report.title, "the field"
    assert "the clause `fields.currency: required`" in report.title, "the clause"
    assert "the data contract 'supplier-invoices' with a supplier, after EN 16931" in report.title
    assert "the supplier's accounts receivable on theirs" in report.title
    assert "Nothing of the message was mapped, completed or guessed" in report.title
    assert any(
        "Ask the partner for a message that holds the data contract" in s for s in (report.steps)
    ), "the option the package offers is the partner's, never a correction by Taktus"


async def test_an_import_that_holds_its_contract_is_mapped() -> None:
    w = World()
    w.partner.reads["R-1"] = INVOICE
    run = await w.run(importing())
    assert run.state is RunState.FINISHED
    assert run.step_run("map").state is StepState.SUCCEEDED


async def test_an_export_that_breaks_its_contract_is_not_sent_at_run_time() -> None:
    w = World()
    run = await w.run(exporting(LACKING))
    assert run.state is RunState.ESCALATED
    assert run.step_run("send").state is StepState.PLANNED
    assert w.partner.calls == [] and w.partner.acted == 0, "nothing was sent"
    assert not [k for k in await w.kinds(run) if k in EGRESS_KINDS], "nothing left the system"
    await w.watch.look(TENANT)
    report = await w.given.owner.queries.one(TENANT, report_id(run.id, 1))
    assert report is not None
    assert "The export breaks the data contract 'customer-invoices'" in report.title
    assert "the field 'currency' is missing" in report.title


async def test_every_send_is_recorded_as_data_that_left_the_system_with_where_it_went() -> None:
    w = World()
    run = await w.run(exporting(INVOICE))
    assert run.state is RunState.FINISHED and w.partner.acted == 1
    kinds = await w.kinds(run)
    assert "egress.write" in kinds, "the send is data that has left the system (ADR-0022)"
    assert kinds[kinds.index("egress.write") + 1] == "residency.egress"
    assert await w.outcomes(run, "residency.egress") == ["eu"]


async def test_partner_data_is_held_to_the_tenants_residency_rule() -> None:
    abroad = World(location="elsewhere", rule=Rule("eu"))
    sent = await abroad.run(exporting(INVOICE))
    assert sent.step_run("send").state is StepState.FAILED
    assert "residency rule admits (eu)" in (sent.step_run("send").reason or "")
    assert abroad.partner.acted == 0
    assert not [k for k in await abroad.kinds(sent) if k in EGRESS_KINDS]
    reading = World(location="elsewhere", rule=Rule("eu"))
    reading.partner.reads["R-1"] = INVOICE
    read = await reading.run(importing())
    assert read.step_run("read").state is StepState.FAILED, "a partner's data is not fetched"
    assert reading.partner.calls == [], "from where the rule does not admit"
    inside = World(location="eu", rule=Rule("eu"))
    assert (await inside.run(exporting(INVOICE))).state is RunState.FINISHED
