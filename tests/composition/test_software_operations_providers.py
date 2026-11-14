"""B-6.01 on three payment providers at once (ADR-0329): a card processor, a wallet and an in-app
subscription service, each the configured connector the run names, their subscriptions joined
before they are matched against the product's entitlements. Read one provider alone, the
entitlements the other two pay for are named granted and not paid; read together, only the
entitlement nobody pays for is.

Each provider is its connector of this repository over its fake under `tests/fakes/`; the
product is the entitlements manifest over the vendor connector. What is faked: every system
behind a connector. No live call is made (DEC-0225, DEC-0226).
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pytest
from fakes import FakeIdentifiers, FakeWorker, payment_service
from fakes import app_subscriptions_service as in_app
from fakes import billing_plans_service as plans
from fakes import entitlement_server as entitlements
from fakes.maturity import VERIFIED
from taktus_connectors.paypal.operations import Config as WalletConfig
from taktus_connectors.paypal.server import build_server as wallet_server
from taktus_connectors.revenuecat.operations import Config as InAppConfig
from taktus_connectors.revenuecat.server import build_server as in_app_server
from taktus_connectors.stripe.operations import Config as CardConfig
from taktus_connectors.stripe.server import build_server as card_server
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
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState

from .test_software_operations import MANIFESTS, Outside, World
from .test_software_operations import outside as outside

KEY = f"client-{secrets.token_hex(6)}:secret-{secrets.token_hex(12)}"
"""One value every provider's fake admits: the three connectors run in this one process and
read their key under the one parameter the bundle names (ADR-0311, where the promise ends)."""
APP_USERS = tuple(f"app_user{n}" for n in range(1, 6))


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def providers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    path = tmp_path / "PAYMENTS_TOKEN"
    path.write_text(KEY, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_PAYMENTS_TOKEN_FILE", str(path))
    servers = {
        "card": payment_service.make_server("127.0.0.1", 0, {KEY}),
        "wallet": plans.make_server("127.0.0.1", 0, {KEY}),
        "in_app": in_app.make_server("127.0.0.1", 0, {KEY}),
    }
    urls = {name: _serving(server) for name, server in servers.items()}
    # The in-app service knows its customers by the app's own user identifiers.
    records = [
        in_app.subscription(n, "expired" if n == 5 else "active", APP_USERS[n - 1])
        for n in range(1, 6)
    ]
    request = Request(  # noqa: S310 - the fake's own address
        f"{urls['in_app']}/_fake/subscriptions", data=json.dumps(records).encode(), method="POST"
    )
    with urlopen(request) as answer:  # noqa: S310 - the fake's own address
        assert answer.status == 200
    yield urls
    for server in servers.values():
        server.shutdown()
        server.server_close()


def granted(outside: Outside) -> None:
    """The product grants the first active customer of each provider one seat, each in its
    provider's identifiers, and one customer nobody pays for."""
    held = {
        "ent_card": ("cus_fake1", "prod_plan"),
        "ent_wallet": ("PAYERFAKE1", plans.PRODUCT),
        "ent_in_app": ("app_user1", "prod_plan"),
        "ent_unpaid": ("UNPAID9", "prod_plan"),
    }
    with outside.product.lock:
        outside.product.entitlements.clear()
        outside.product.entitlements.update(
            {
                key: {"id": key, "customer": customer, "product": product, "quantity": 1}
                for key, (customer, product) in held.items()
            }
        )


class ProvidersWorld(World):
    """The world, with three payment providers under identifiers of their own."""

    def __init__(self, outside: Outside, urls: dict[str, str]) -> None:
        super().__init__(outside)
        granted(outside)

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        product = Wrapper(
            Upstream(entitlements.create_server(outside.product), timeout=5.0),
            with_manifest(*load_manifest(MANIFESTS / "entitlements.manifest.json")),
        )
        connectors = [
            ("connector.card", served(card_server(CardConfig(urls["card"], timeout=5.0)))),
            ("connector.wallet", served(wallet_server(WalletConfig(urls["wallet"], timeout=5.0)))),
            (
                "connector.in_app",
                served(in_app_server(InAppConfig(urls["in_app"], in_app.PROJECT, timeout=5.0))),
            ),
            ("connector.entitlements", served(vendor_server(product))),
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

    async def ready(self) -> ProvidersWorld:
        await super().ready()
        return self


async def test_b_6_01_matches_every_provider_s_payments_in_one_run(
    outside: Outside, providers: dict[str, str]
) -> None:
    w = await ProvidersWorld(outside, providers).ready()
    version = await w.registered("B-6.01-payment-against-entitlement.yaml")

    alone = await w.start(version, provider="connector.card")
    assert alone.state is RunState.FINISHED, [(s.step_id, s.reason) for s in alone.step_runs]
    one = await w.result(alone, "match")
    assert sorted(e["customer"] for e in one["right_only"]) == [
        "PAYERFAKE1",
        "UNPAID9",
        "app_user1",
    ], "read alone, what the other two providers are paid for looks granted and not paid"
    for step in ("payments-second", "payments-third"):
        assert (await w.result(alone, step))["skipped"] is True

    run = await w.start(
        version, provider="connector.card", second="connector.wallet", third="connector.in_app"
    )
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    matched = await w.result(run, "match")
    assert matched["matched"] == 3, "each provider's first customer pays its entitlement"
    assert [e["customer"] for e in matched["right_only"]] == ["UNPAID9"]
    assert sorted(e["customer"] for e in matched["left_only"]) == sorted(
        [
            *(f"cus_fake{n}" for n in (2, 3, 4)),
            *(f"PAYERFAKE{n}" for n in (2, 3, 4)),
            *(f"app_user{n}" for n in (2, 3, 4)),
        ]
    ), "every provider's active subscription without an entitlement is named"
    assert matched["duplicates"] == [] and matched["unkeyed"] == []
    assert outside.product.document()["calls"] == {"list_entitlements": 2}, "it only read"
