# ruff: noqa: F811 — every test requests the imported fixtures `outside` and `provider` by name
"""Recurring revenue, failed payments, outgoing invoices and lost webhooks of the blueprint
`software-operations`, on the payment provider connectors of this repository (UC-03 B-6.02,
B-6.03, B-6.04, B-6.06; ADR-0214, ADR-0231).

The world of `test_software_operations_payments.py`: the connector behind the payment
capabilities is each provider's in turn where the process runs on every provider, and the first
provider's where only it serves the capability. What is faked: each provider's API and the
mailbox. The bundles are the shipped ones.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeIdentifiers, FakeWorker, package_index_service, payment_service
from fakes import app_subscriptions_service as in_app
from fakes import billing_plans_service as plans
from fakes.maturity import VERIFIED
from fakes.owner_channel import TENANT
from taktus_connectors.depsdev.operations import Config as PackagesConfig
from taktus_connectors.depsdev.server import build_server as packages_server
from taktus_connectors.github.server import Config as RepositoryConfig
from taktus_connectors.github.server import build_server as repository_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.reporting.domain.model import Level
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState

from .test_software_operations import (
    REPOSITORY,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
)
from .test_software_operations_payments import (
    PaymentsWorld,
    Provider,
    provider,  # noqa: F401 — the fixture
)
from .test_software_operations_repository import advance_main

DAY = 86_400
CUSTOMERS = tuple(f"cus_fake{n}" for n in range(1, 6))


def posted(url: str, kind: str, records: list[dict[str, Any]]) -> None:
    httpx.post(f"{url}/_fake/{kind}", content=json.dumps(records), timeout=5.0)


def failed(run: Any) -> list[tuple[str, str | None]]:
    return [(s.step_id, s.reason) for s in run.step_runs]


# --- B-6.03 recurring revenue and churn ------------------------------------------------------


async def test_b_6_03_counts_revenue_and_churn_on_every_provider(
    outside: Outside, provider: Provider
) -> None:
    w = await PaymentsWorld(outside, provider).ready()
    version = await w.registered("B-6.03-recurring-revenue.yaml")
    run = await w.start(version)
    assert run.state is RunState.FINISHED, failed(run)
    figures = await w.result(run, "figures")
    assert len(figures["revenue"]) == 8 and figures["currency"] == "EUR"
    if provider.name == "in-app":
        assert (figures["mrr"], figures["unpriced"]) == ("0", 5), "the store gives no price"
    else:
        assert figures["mrr"] == "3996", "four active subscriptions of 9.99 EUR a month"
    revenue = await w.result(run, "revenue")
    assert revenue["ratio"] == (None if provider.name == "in-app" else 1.0)
    assert (await w.result(run, "cancelled"))["change"] == 0.0


async def test_b_6_03_raises_red_when_yesterday_lost_a_customer(outside: Outside) -> None:
    first = Provider("first", outside.payments, CUSTOMERS, "prod_plan", ())
    records = payment_service.default_subscriptions()
    records[0]["status"] = "canceled"
    records[0]["ended_at"] = int(time.time()) - DAY
    posted(outside.payments, "subscriptions", records)
    w = await PaymentsWorld(outside, first).ready()
    version = await w.registered("B-6.03-recurring-revenue.yaml")
    for signal, step, select, direction, yellow, red in (
        ("payments.revenue", "revenue", "ratio", "below", 0.98, 0.95),
        ("payments.cancellations", "cancelled", "change", "above", 0.5, 0.9),
    ):
        await w.corridor(
            signal,
            version.process_id,
            step=step,
            select=select,
            bounds="fixed",
            direction=direction,
            yellow=yellow,
            red=red,
        )
    run = await w.start(version)
    assert run.state is RunState.FINISHED, failed(run)
    revenue = await w.result(run, "revenue")
    assert (revenue["total_text"], revenue["median_text"]) == ("2997", "3996")
    assert (await w.result(run, "cancelled"))["change_text"] == "1"
    looked = await w.signals.watch.look(TENANT)
    assert {j.level for j in looked.judged} == {Level.RED}
    assert len(looked.incidents) == 2


# --- B-6.04 failed payments -----------------------------------------------------------------


async def test_b_6_04_reminds_on_the_third_day_with_the_page_to_pay_or_names_it_for_a_person(
    outside: Outside, provider: Provider
) -> None:
    if provider.name == "in-app":
        records = [in_app.subscription(n) for n in (1, 2)]
        records.append(in_app.subscription(3, "in_billing_retry"))
        posted(provider.url, "subscriptions", records)
    w = await PaymentsWorld(outside, provider).ready()
    version = await w.registered("B-6.04-failed-payments.yaml")
    customer = provider.customers[2]
    run = await w.confirmed(await w.start(version, customer=customer))
    assert run.state is RunState.FINISHED, failed(run)
    stage, unreachable = await w.result(run, "stage"), await w.result(run, "unreachable")
    if provider.name == "first":
        assert stage["count"] == 1 and stage["first"]["days_failing"] == 3
        assert "https://invoice.stripe.example/i/9" in await w.result(run, "compose")
        assert outside.submitted() == 1, "one reminder, after a person confirmed it"
    elif provider.name == "second":
        assert (stage["count"], unreachable["count"]) == (0, 1), "no page: to a person"
        assert outside.submitted() == 0
    else:
        assert (stage["count"], unreachable["count"]) == (0, 0), "the store reminds"
        assert outside.submitted() == 0


async def test_b_6_04_sends_nothing_on_a_day_that_is_no_reminder_day(outside: Outside) -> None:
    first = Provider("first", outside.payments, CUSTOMERS, "prod_plan", ())
    records = payment_service.default_invoices(int(time.time()) - DAY)
    posted(outside.payments, "invoices", records)
    w = await PaymentsWorld(outside, first).ready()
    version = await w.registered("B-6.04-failed-payments.yaml")
    run = await w.confirmed(await w.start(version, customer="cus_fake3"))
    assert run.state is RunState.FINISHED, failed(run)
    assert (await w.result(run, "stage"))["count"] == 0, "the fourth day is no reminder day"
    assert outside.submitted() == 0


# --- B-6.02 lost webhooks -------------------------------------------------------------------


async def test_b_6_02_names_an_event_undelivered_for_an_hour_and_replays_nothing(
    outside: Outside,
) -> None:
    now = int(time.time())
    events = [
        payment_service.event(1, 0, now - 3 * DAY),
        payment_service.event(2, 1, now - 7200),
        payment_service.event(3, 1, now - 60),
    ]
    posted(outside.payments, "events", events)
    w = await PaymentsWorld(outside, Provider("first", outside.payments, CUSTOMERS, "", ())).ready()
    version = await w.registered("B-6.02-lost-webhooks.yaml")
    await w.corridor(
        "payments.lost_events",
        version.process_id,
        step="lost",
        select="count",
        bounds="fixed",
        direction="above",
        yellow=0.25,
        red=0.5,
    )
    run = await w.start(version)
    assert run.state is RunState.FINISHED, failed(run)
    lost = await w.result(run, "lost")
    assert [e["id"] for e in lost["items"]] == ["evt_fake2"], "a minute old is still retried"
    looked = await w.signals.watch.look(TENANT)
    assert len(looked.incidents) == 1


# --- B-6.06 outgoing invoices ---------------------------------------------------------------

OCTOBER = 1790812800
"""2026-10-01 00:00 UTC."""


async def test_b_6_06_collects_the_months_invoices_and_names_those_owed(
    outside: Outside, provider: Provider
) -> None:
    if provider.name == "in-app":
        return  # the in-app service lists no invoices of a project (ADR-0214)
    if provider.name == "first":
        records = [
            payment_service.invoice(1, "cus_fake1", created=OCTOBER + DAY),
            payment_service.invoice(2, "cus_fake2", status="open", created=OCTOBER + 2 * DAY,
                                    failed=True),
            payment_service.invoice(3, "cus_fake3", status="void", created=OCTOBER + 3 * DAY),
            payment_service.invoice(4, "cus_fake4", created=OCTOBER - 1),
        ]  # fmt: skip
    else:
        records = [
            plans.invoice(1, "2026-10-02"),
            plans.invoice(2, "2026-10-03", status="SENT"),
            plans.invoice(3, "2026-10-04", status="DRAFT"),
            plans.invoice(4, "2026-09-30"),
        ]
    posted(provider.url, "invoices", records)
    w = await PaymentsWorld(outside, provider).ready()
    version = await w.registered("B-6.06-outgoing-invoices.yaml")
    run = await w.start(version, month="2026-10")
    assert run.state is RunState.FINISHED, failed(run)
    issued = await w.result(run, "issued")
    assert issued["count"] == 2 and issued["first"]["total"] == 999
    owed = await w.result(run, "owed")
    assert owed["count"] == 1 and owed["first"]["remaining"] == 999


# --- B-10.04 licences of dependencies -------------------------------------------------------

LOCK = json.dumps(
    {
        "name": "product",
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "product", "version": "1.0.0"},
            "node_modules/react": {"version": "18.3.1"},
            "node_modules/copyleft-lib": {"version": "2.0.0"},
            "node_modules/@colors/colors": {"version": "1.5.0", "dev": True},
            "node_modules/unheard-of": {"version": "9.9.9"},
        },
    }
)


class LicencesWorld(World):
    """The world, with the repository and the package index behind their capabilities."""

    def __init__(self, outside: Outside, index: str) -> None:
        super().__init__(outside)
        connectors = [
            (
                "connector.repository",
                McpActionConnector(
                    repository_server(
                        RepositoryConfig(outside.repository, REPOSITORY, timeout=5.0)
                    ),
                    timeout=10.0,
                ),
            ),
            (
                "connector.packages",
                McpActionConnector(
                    packages_server(PackagesConfig(index, timeout=5.0)), timeout=10.0
                ),
            ),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool(),
        )


async def test_b_10_04_names_a_shipped_copyleft_dependency_and_one_without_a_licence(
    outside: Outside, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tmp_path / "PACKAGES_TOKEN"
    token.write_text("any-value", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_PACKAGES_TOKEN_FILE", str(token))
    index = package_index_service.make_server("127.0.0.1", 0)
    threading.Thread(target=index.serve_forever, args=(0.05,), daemon=True).start()
    try:
        advance_main(outside, {"package-lock.json": LOCK})
        url = f"http://127.0.0.1:{index.server_address[1]}"
        w = await LicencesWorld(outside, url).ready()
        version = await w.registered("B-10.04-dependency-licences.yaml")
        await w.corridor(
            "licences.conflicts",
            version.process_id,
            step="conflicts",
            select="count",
            bounds="fixed",
            direction="above",
            yellow=0.25,
            red=0.5,
        )
        run = await w.start(version)
        assert run.state is RunState.FINISHED, failed(run)
        conflicts = await w.result(run, "conflicts")
        assert [p["name"] for p in conflicts["items"]] == ["copyleft-lib"]
        unknown = await w.result(run, "unknown")
        assert [p["name"] for p in unknown["items"]] == ["unheard-of"]
        looked = await w.signals.watch.look(TENANT)
        assert len(looked.incidents) == 1
    finally:
        index.shutdown()
        index.server_close()
