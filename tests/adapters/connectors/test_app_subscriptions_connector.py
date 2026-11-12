"""The in-app subscription connector answers `payments.subscriptions` and `payments.customers`
in the shape of the first payment provider connector, from a service that lists customers and
each customer's subscriptions, but no project's subscriptions at once (ADR-0150, ADR-0206).

Against the fake under `tests/fakes/app_subscriptions_service.py`, in a thread of this process.
The connector is served in-process over MCP, as an instance reaches it.
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
from fakes import app_subscriptions_service as service
from fakes.ports import free_port
from taktus_connectors.revenuecat.operations import Config
from taktus_connectors.revenuecat.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, CaseScope, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "sk_" + secrets.token_hex(12)
CREDENTIAL = "PAYMENTS_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "payments"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def provider() -> Iterator[str]:
    server = service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(scope: str | None = None) -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
        scope=CaseScope(subject=scope) if scope else None,
    )


def payments(url: str, project: str = service.PROJECT) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, project, timeout=5.0)))


def replace(url: str, records: list[dict[str, Any]]) -> None:
    httpx.post(f"{url}/_fake/subscriptions", content=json.dumps(records), timeout=5.0)


async def test_the_active_subscriptions_are_listed_in_the_shared_shape_without_personal_data(
    provider: str,
) -> None:
    result = await payments(provider).call("payments.subscriptions.list", context(), {})
    assert result.effect.kind.value == "read"
    listed = result.output["subscriptions"]
    assert [s["id"] for s in listed] == [f"sub_fake{n}" for n in range(1, 5)]
    assert listed[0] == {
        "id": "sub_fake1",
        "customer": "cus_fake1",
        "status": "active",
        "current_period_end": 1790000001,
        "cancel_at_period_end": False,
        "started_at": 1780000000,
        "ended_at": None,
        "items": [
            {
                "price": None,
                "product": "prod_plan",
                "quantity": 1,
                "unit_amount": None,
                "currency": None,
                "interval": None,
                "interval_count": None,
            }
        ],
        "metadata": {"store": "app_store", "environment": "production"},
    }
    assert listed[1]["cancel_at_period_end"] is True, "will_not_renew"
    assert result.output["complete"] is True
    # One page of customers, then one request per customer.
    assert result.consumption.quota_units == 1 + 5
    text = json.dumps(result.output)
    assert "management_url" not in text and "apps.apple.example" not in text and "DE" not in text


async def test_statuses_map_to_the_shared_vocabulary(provider: str) -> None:
    replace(
        provider,
        [
            service.subscription(1, "in_grace_period"),
            service.subscription(2, "in_billing_retry"),
            service.subscription(3, "expired"),
            service.subscription(4, "unknown"),
        ],
    )
    every = await payments(provider).call(
        "payments.subscriptions.list", context(), {"status": "all"}
    )
    assert [s["status"] for s in every.output["subscriptions"]] == [
        "past_due",
        "past_due",
        "canceled",
        None,
    ]


async def test_customers_are_paged_and_the_limit_bounds_the_answer(provider: str) -> None:
    replace(provider, [service.subscription(n) for n in range(1, 151)])
    connector = payments(provider)
    result = await connector.call("payments.subscriptions.list", context(), {})
    assert len({s["id"] for s in result.output["subscriptions"]}) == 150
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 2 + 150, "two pages of customers, one per customer"
    bounded = await connector.call("payments.subscriptions.list", context(), {"limit": 20})
    assert len(bounded.output["subscriptions"]) == 20
    assert bounded.output["complete"] is False


async def test_one_customers_subscriptions_and_another_customer_refused_under_a_scope(
    provider: str,
) -> None:
    connector = payments(provider)
    own = await connector.call(
        "payments.customers.subscriptions", context("cus_fake2"), {"customer": "cus_fake2"}
    )
    assert [s["id"] for s in own.output["subscriptions"]] == ["sub_fake2"]
    assert own.output["complete"] is True and own.consumption.quota_units == 1
    with pytest.raises(CallFailed) as failed:
        await connector.call(
            "payments.customers.subscriptions", context("cus_fake2"), {"customer": "cus_fake3"}
        )
    assert failed.value.error.cause.value == "out_of_scope"


async def test_an_app_user_identifier_with_reserved_characters_is_sent_encoded(
    provider: str,
) -> None:
    anonymous = "$RCAnonymousID:0a1b/2c"
    replace(provider, [service.subscription(1, customer=anonymous)])
    result = await payments(provider).call(
        "payments.customers.subscriptions", context(), {"customer": anonymous}
    )
    assert [s["customer"] for s in result.output["subscriptions"]] == [anonymous]


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("payments.subscriptions.read", {"id": "sub_unknown"}),
        ("payments.subscriptions.read", {"id": "../customers"}),
        ("payments.subscriptions.list", {"status": "unpaid"}),
        ("payments.subscriptions.list", {"limit": 0}),
        ("payments.customers.subscriptions", {"customer": "cus_nobody"}),
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    provider: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await payments(provider).call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"
    assert "refused by the fake" not in (failed.value.error.detail or "")


async def test_a_key_the_provider_does_not_admit_is_unauthenticated(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-key", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await payments(provider).call("payments.subscriptions.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await payments(f"http://127.0.0.1:{free_port()}").call(
            "payments.subscriptions.list", context(), {}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


async def test_a_renewal_the_store_retries_is_a_failure_with_the_stores_page(
    provider: str,
) -> None:
    records = [service.subscription(1), service.subscription(2, "in_billing_retry")]
    replace(provider, records)
    connector = payments(provider)
    result = await connector.call("payments.failures.list", context(), {})
    [failure] = result.output["failures"]
    assert failure["customer"] == "cus_fake2" and failure["reason"] == "in_billing_retry"
    assert failure["update_url"] == "https://apps.apple.example/account/subscriptions/2"
    assert failure["amount"] is None and failure["days_failing"] is None, "never guessed"
    own = await connector.call(
        "payments.customers.failures", context("cus_fake2"), {"customer": "cus_fake2"}
    )
    assert [f["id"] for f in own.output["failures"]] == ["sub_fake2"]
