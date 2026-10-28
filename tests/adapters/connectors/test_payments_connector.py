"""The payment provider connector reads subscriptions with the fields a match against the
product's entitlements needs, and no personal data (ADR-0150, issue #447).

Against the fake under `tests/fakes/payment_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
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
from fakes import payment_service
from fakes.ports import free_port

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.stripe.operations import Config
from taktus.adapters.driven.connectors.stripe.server import build_server
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "PAYMENTS_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "payments"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def provider() -> Iterator[str]:
    server = payment_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


def payments(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def replace(url: str, records: list[dict[str, Any]]) -> None:
    httpx.post(f"{url}/_fake/subscriptions", content=json.dumps(records), timeout=5.0)


async def test_the_active_subscriptions_are_listed_without_personal_data(provider: str) -> None:
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
        "items": [
            {
                "price": "price_monthly",
                "product": "prod_plan",
                "quantity": 1,
                "unit_amount": 999,
                "currency": "EUR",
                "interval": "month",
            }
        ],
        "metadata": {"account": "acct-1"},
    }
    assert result.output["complete"] is True
    text = json.dumps(result.output)
    assert "@customer.example" not in text and "Customer 1" not in text and "pm_fake" not in text


async def test_a_status_filter_and_all(provider: str) -> None:
    connector = payments(provider)
    canceled = await connector.call(
        "payments.subscriptions.list", context(), {"status": "canceled"}
    )
    assert [s["id"] for s in canceled.output["subscriptions"]] == ["sub_fake5"]
    every = await connector.call("payments.subscriptions.list", context(), {"status": "all"})
    assert len(every.output["subscriptions"]) == 5


async def test_pages_are_followed_and_the_limit_bounds_the_answer(provider: str) -> None:
    replace(provider, [payment_service.subscription(n) for n in range(1, 251)])
    connector = payments(provider)
    result = await connector.call("payments.subscriptions.list", context(), {})
    assert len(result.output["subscriptions"]) == 250
    assert len({s["id"] for s in result.output["subscriptions"]}) == 250
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 3, "three pages of at most 100"
    bounded = await connector.call("payments.subscriptions.list", context(), {"limit": 150})
    assert len(bounded.output["subscriptions"]) == 150
    assert bounded.output["complete"] is False


async def test_one_subscription_is_read(provider: str) -> None:
    result = await payments(provider).call(
        "payments.subscriptions.read", context(), {"id": "sub_fake2"}
    )
    assert result.output["id"] == "sub_fake2"
    assert result.output["cancel_at_period_end"] is True


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("payments.subscriptions.read", {"id": "sub_unknown"}),
        ("payments.subscriptions.read", {"id": "../customers"}),
        ("payments.subscriptions.list", {"status": "lapsed"}),
        ("payments.subscriptions.list", {"limit": 0}),
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
