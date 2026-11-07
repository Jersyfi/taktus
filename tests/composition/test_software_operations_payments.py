# ruff: noqa: F811 — every test requests the imported fixture `outside` by its name
"""The payment processes of the blueprint `software-operations` run unchanged on every payment
provider connector of this repository, and B-5.06 prepares a renewal (UC-03 B-6.01, B-3.04,
B-5.06; ADR-0199, ADR-0206).

The world of `test_software_operations.py`, with the connector behind `payments.subscriptions`
and `payments.customers` swapped: the first payment provider, a second whose subscriptions name
a plan and whose customers are payers, and an in-app subscription service whose customers are
the app's own user identifiers. The product's entitlements are served by the vendor connector
under the blueprint's manifest, as the product's own server would be. What is faked: each
provider's API and the product's server.

The bundles are the shipped ones; only the entitlements the fake product holds are set to the
identifiers each provider gives its customers and products, as a tenant's product keeps them.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeIdentifiers, FakeWorker
from fakes import app_subscriptions_service as in_app
from fakes import billing_plans_service as plans
from fakes import entitlement_server as entitlements
from fakes.maturity import VERIFIED
from fakes.owner_channel import TENANT
from taktus_connectors.paypal.operations import Config as SecondConfig
from taktus_connectors.paypal.server import build_server as second_server
from taktus_connectors.revenuecat.operations import Config as InAppConfig
from taktus_connectors.revenuecat.server import build_server as in_app_server
from taktus_connectors.stripe.operations import Config as FirstConfig
from taktus_connectors.stripe.server import build_server as first_server
from taktus_connectors.vendor.manifest import load as load_manifest
from taktus_connectors.vendor.server import build_server as vendor_server
from taktus_connectors.vendor.upstream import Upstream
from taktus_connectors.vendor.wrapping import Wrapper, with_manifest

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.reporting.domain.model import Level
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState

from .test_software_operations import (
    MANIFESTS,
    TOKEN,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
    states,
)

PAIR = f"client-{secrets.token_hex(6)}:secret-{secrets.token_hex(12)}"
"""The second provider's credential: an application's client identifier and secret."""


@dataclass(frozen=True)
class Provider:
    """One payment provider as a process sees it: the identifiers it gives the customers whose
    subscriptions the fake holds (four active, the fifth ended), and its product."""

    name: str
    url: str
    customers: tuple[str, ...]
    product: str
    ends: tuple[int, ...]
    """The end of each active customer's paid period, in seconds since the epoch."""

    def connector(self) -> McpActionConnector:
        if self.name == "second":
            server = second_server(SecondConfig(self.url, timeout=5.0))
        elif self.name == "in-app":
            server = in_app_server(InAppConfig(self.url, in_app.PROJECT, timeout=5.0))
        else:
            server = first_server(FirstConfig(self.url, timeout=5.0))
        return McpActionConnector(server, timeout=10.0)


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture(params=["first", "second", "in-app"])
def provider(
    request: pytest.FixtureRequest,
    outside: Outside,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Provider]:
    name = request.param
    if name == "first":
        yield Provider(
            name,
            outside.payments,
            tuple(f"cus_fake{n}" for n in range(1, 6)),
            "prod_plan",
            tuple(1790000000 + n for n in range(1, 5)),
        )
        return
    if name == "second":
        path = tmp_path / "PAYMENTS_TOKEN_PAIR"
        path.write_text(PAIR, encoding="utf-8")
        monkeypatch.setenv("TAKTUS_CREDENTIAL_PAYMENTS_TOKEN_FILE", str(path))
        server = plans.make_server("127.0.0.1", 0, {PAIR})
        given = Provider(
            name,
            _serving(server),
            tuple(f"PAYERFAKE{n}" for n in range(1, 6)),
            plans.PRODUCT,
            (1796119200, 1796205600, 1796292000, 1796378400),  # 2026-12-01 to -04, 10:00 UTC
        )
    else:
        server = in_app.make_server("127.0.0.1", 0, {TOKEN})
        given = Provider(
            name,
            _serving(server),
            tuple(f"cus_fake{n}" for n in range(1, 6)),
            "prod_plan",
            tuple(1790000000 + n for n in range(1, 5)),
        )
    yield given
    server.shutdown()
    server.server_close()


def entitled(outside: Outside, provider: Provider) -> None:
    """The product grants the first three active customers one seat each, and a customer
    nobody pays for: the fake product's default, in the provider's identifiers."""
    held = {
        f"ent_{n}": {
            "id": f"ent_{n}",
            "customer": provider.customers[n - 1],
            "product": provider.product,
            "quantity": 1,
        }
        for n in (1, 2, 3)
    }
    held["ent_9"] = {
        "id": "ent_9",
        "customer": "UNPAID9",
        "product": provider.product,
        "quantity": 1,
    }
    with outside.product.lock:
        outside.product.entitlements.clear()
        outside.product.entitlements.update(held)


class PaymentsWorld(World):
    """The world, with the payment provider the test names behind the payment capabilities."""

    def __init__(self, outside: Outside, provider: Provider) -> None:
        super().__init__(outside)
        entitled(outside, provider)
        connectors = [
            ("connector.payments", provider.connector()),
            (
                "connector.entitlements",
                McpActionConnector(
                    vendor_server(
                        Wrapper(
                            Upstream(entitlements.create_server(outside.product), timeout=5.0),
                            with_manifest(*load_manifest(MANIFESTS / "entitlements.manifest.json")),
                        )
                    ),
                    timeout=10.0,
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

    async def ready(self) -> PaymentsWorld:
        await super().ready()
        return self


async def test_b_6_01_names_what_is_paid_and_not_granted_on_every_provider(
    outside: Outside, provider: Provider
) -> None:
    w = await PaymentsWorld(outside, provider).ready()
    version = await w.registered("B-6.01-payment-against-entitlement.yaml")
    await w.corridor(
        "payments.entitlement_mismatches",
        version.process_id,
        step="match",
        select="mismatches",
        bounds="fixed",
        direction="above",
        yellow=0.25,
        red=0.5,
    )
    run = await w.start(version)
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    matched = await w.result(run, "match")
    assert matched["matched"] == 3
    assert [e["customer"] for e in matched["left_only"]] == [provider.customers[3]]
    assert [e["customer"] for e in matched["right_only"]] == ["UNPAID9"]
    looked = await w.signals.watch.look(TENANT)
    (judged,) = looked.judged
    assert judged.level is Level.RED and len(looked.incidents) == 1
    assert outside.product.document()["calls"] == {"list_entitlements": 1}, "it only read"


async def test_b_3_04_grants_what_was_paid_for_on_every_provider(
    outside: Outside, provider: Provider
) -> None:
    w = await PaymentsWorld(outside, provider).ready()
    version = await w.registered("B-3.04-paid-not-unlocked.yaml")
    unlocked = provider.customers[3]
    run = await w.start(version, customer=unlocked)
    assert run.state is RunState.WAITING_HUMAN, "at level 2 nothing starts before a person"
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "match"))["first"]["kind"] == "left_only"
    granted = [e for e in outside.product.document()["entitlements"] if e["customer"] == unlocked]
    assert [(e["product"], e["quantity"]) for e in granted] == [(provider.product, 1)]
    assert states(run)["repair"] is StepState.SUCCEEDED
    again = await w.confirmed(await w.start(version, customer=unlocked))
    assert (await w.result(again, "match"))["mismatches"] == 0


async def test_b_5_06_checks_the_seats_on_every_provider(
    outside: Outside, provider: Provider
) -> None:
    w = await PaymentsWorld(outside, provider).ready()
    version = await w.registered("B-5.06-business-seats.yaml")
    customer = provider.customers[0]
    run = await w.start(version, customer=customer)
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "match"))["mismatches"] == 0
    assert (await w.result(run, "renewals"))["count"] == 0, "no moment given, none prepared"
    with outside.product.lock:
        outside.product.entitlements["ent_1"]["quantity"] = 3
    changed = await w.start(version, customer=customer)
    [differing] = (await w.result(changed, "match"))["differing"]
    assert differing["fields"][0]["right_value"] == 3


async def test_b_5_06_prepares_the_renewal_of_a_period_that_ends_by_the_moment_given(
    outside: Outside, provider: Provider
) -> None:
    w = await PaymentsWorld(outside, provider).ready()
    version = await w.registered("B-5.06-business-seats.yaml")
    await w.corridor(
        "payments.renewals_due",
        version.process_id,
        step="renewals",
        select="count",
        bounds="fixed",
        direction="above",
        yellow=0.25,
        red=0.5,
    )
    customer, end = provider.customers[0], provider.ends[0]
    before = await w.start(version, customer=customer, renew_before=end - 1)
    assert before.state is RunState.FINISHED, [(s.step_id, s.reason) for s in before.step_runs]
    assert (await w.result(before, "renewals"))["count"] == 0
    due = await w.start(version, customer=customer, renew_before=end)
    renewals = await w.result(due, "renewals")
    assert renewals["count"] == 1
    assert renewals["first"]["customer"] == customer
    assert renewals["first"]["current_period_end"] == end
    looked = await w.signals.watch.look(TENANT)
    assert any(j.level is Level.RED and j.run_id == due.id for j in looked.judged)
    assert "grant_entitlement" not in outside.product.document()["calls"], "it only read"
