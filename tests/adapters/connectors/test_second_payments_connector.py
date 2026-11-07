"""The second payment provider connector answers `payments.subscriptions` and
`payments.customers` in the shape of the first, from a provider whose subscriptions name a plan
and whose access needs a token exchanged first (ADR-0150, ADR-0206).

Against the fake under `tests/fakes/billing_plans_service.py`, in a thread of this process. The
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
from fakes import billing_plans_service as provider_fake
from fakes.ports import free_port
from taktus_connectors.paypal.operations import Config
from taktus_connectors.paypal.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, CaseScope, idempotency_key
from taktus.ports.worker import CredentialReference

PAIR = f"client-{secrets.token_hex(6)}:secret-{secrets.token_hex(12)}"
CREDENTIAL = "PAYMENTS_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "payments"
    path.write_text(PAIR, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def provider() -> Iterator[str]:
    server = provider_fake.make_server("127.0.0.1", 0, {PAIR})
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


def payments(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def replace(url: str, records: list[dict[str, Any]]) -> None:
    httpx.post(f"{url}/_fake/subscriptions", content=json.dumps(records), timeout=5.0)


async def test_the_active_subscriptions_are_listed_in_the_shared_shape_without_personal_data(
    provider: str,
) -> None:
    result = await payments(provider).call("payments.subscriptions.list", context(), {})
    assert result.effect.kind.value == "read"
    listed = result.output["subscriptions"]
    assert [s["id"] for s in listed] == [f"I-FAKE{n}" for n in range(1, 5)]
    assert listed[0] == {
        "id": "I-FAKE1",
        "customer": "PAYERFAKE1",
        "status": "active",
        "current_period_end": 1796119200,  # 2026-12-01T10:00:00Z
        "cancel_at_period_end": False,
        "items": [
            {
                "price": provider_fake.PLAN,
                "product": provider_fake.PRODUCT,
                "quantity": 1,
                "unit_amount": 999,
                "currency": "EUR",
                "interval": "month",
            }
        ],
        "metadata": {"custom_id": "acct-1"},
    }
    assert result.output["complete"] is True
    text = json.dumps(result.output)
    assert "@customer.example" not in text and "Customer" not in text


async def test_the_plan_is_read_once_per_call_and_the_token_exchanged_once(provider: str) -> None:
    result = await payments(provider).call("payments.subscriptions.list", context(), {})
    # One token, one page of four, one plan.
    assert result.consumption.quota_units == 3


async def test_statuses_map_to_the_shared_vocabulary(provider: str) -> None:
    connector = payments(provider)
    canceled = await connector.call(
        "payments.subscriptions.list", context(), {"status": "canceled"}
    )
    assert [(s["id"], s["status"]) for s in canceled.output["subscriptions"]] == [
        ("I-FAKE5", "canceled")
    ]
    every = await connector.call("payments.subscriptions.list", context(), {"status": "all"})
    assert len(every.output["subscriptions"]) == 5


async def test_pages_of_twenty_are_followed_and_the_limit_bounds_the_answer(provider: str) -> None:
    replace(provider, [provider_fake.subscription(n) for n in range(1, 46)])
    connector = payments(provider)
    result = await connector.call("payments.subscriptions.list", context(), {})
    assert len({s["id"] for s in result.output["subscriptions"]}) == 45
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 1 + 3 + 1, "token, three pages, one plan"
    bounded = await connector.call("payments.subscriptions.list", context(), {"limit": 30})
    assert len(bounded.output["subscriptions"]) == 30
    assert bounded.output["complete"] is False


async def test_one_customers_subscriptions_and_another_customer_refused_under_a_scope(
    provider: str,
) -> None:
    connector = payments(provider)
    own = await connector.call(
        "payments.customers.subscriptions", context("PAYERFAKE2"), {"customer": "PAYERFAKE2"}
    )
    assert [s["id"] for s in own.output["subscriptions"]] == ["I-FAKE2"]
    assert own.output["complete"] is True
    with pytest.raises(CallFailed) as failed:
        await connector.call(
            "payments.customers.subscriptions", context("PAYERFAKE2"), {"customer": "PAYERFAKE3"}
        )
    assert failed.value.error.cause.value == "out_of_scope"


async def test_a_quantity_that_is_no_whole_number_and_an_overridden_plan_are_not_guessed(
    provider: str,
) -> None:
    odd = provider_fake.subscription(1, quantity="1.5")
    odd["plan_overridden"] = True
    replace(provider, [odd])
    result = await payments(provider).call(
        "payments.subscriptions.read", context(), {"id": "I-FAKE1"}
    )
    [item] = result.output["items"]
    assert item["quantity"] is None and item["unit_amount"] is None


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("payments.subscriptions.read", {"id": "I-UNKNOWN"}),
        ("payments.subscriptions.read", {"id": "../plans"}),
        ("payments.subscriptions.list", {"status": "trialing"}),
        ("payments.subscriptions.list", {"limit": 0}),
        ("payments.customers.subscriptions", {"customer": "not one"}),
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    provider: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await payments(provider).call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"
    assert "refused by the fake" not in (failed.value.error.detail or "")


@pytest.mark.parametrize("value", ["client:not-the-secret", "no-colon"])
async def test_a_pair_the_provider_does_not_admit_is_unauthenticated(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text(value, encoding="utf-8")
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
