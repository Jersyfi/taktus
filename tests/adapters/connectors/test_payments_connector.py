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
from taktus_connectors.stripe.operations import Config
from taktus_connectors.stripe.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, CaseScope, idempotency_key
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


def replace(url: str, records: list[dict[str, Any]], kind: str = "subscriptions") -> None:
    httpx.post(f"{url}/_fake/{kind}", content=json.dumps(records), timeout=5.0)


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
        "started_at": 1780000001,
        "ended_at": None,
        "items": [
            {
                "price": "price_monthly",
                "product": "prod_plan",
                "quantity": 1,
                "unit_amount": 999,
                "currency": "EUR",
                "interval": "month",
                "interval_count": 1,
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


# --- failed payments, invoices, undelivered events, a customer's contact (ADR-0214) ---------


async def test_a_failed_payment_is_an_open_invoice_attempted_with_its_page_to_pay(
    provider: str,
) -> None:
    result = await payments(provider).call("payments.failures.list", context(), {})
    [failure] = result.output["failures"]
    assert failure["id"] == "in_fake9" and failure["customer"] == "cus_fake3"
    assert (failure["amount"], failure["currency"], failure["attempts"]) == (999, "EUR", 2)
    assert failure["reason"] == "insufficient_funds"
    assert failure["days_failing"] == 3
    assert failure["update_url"] == "https://invoice.stripe.example/i/9"
    assert result.output["complete"] is True and isinstance(result.output["as_of"], int)
    assert "@customer.example" not in json.dumps(result.output)


async def test_one_customers_failures_and_contact_only_under_their_scope(provider: str) -> None:
    connector = payments(provider)
    own = await connector.call(
        "payments.customers.failures", context("cus_fake3"), {"customer": "cus_fake3"}
    )
    assert [f["id"] for f in own.output["failures"]] == ["in_fake9"]
    none = await connector.call(
        "payments.customers.failures", context("cus_fake1"), {"customer": "cus_fake1"}
    )
    assert none.output["failures"] == []
    reached = await connector.call(
        "payments.customers.contact", context("cus_fake3"), {"customer": "cus_fake3"}
    )
    assert reached.output == {"customer": "cus_fake3", "email": "person3@customer.example"}
    for scope in (None, "cus_fake1"):
        with pytest.raises(CallFailed) as failed:
            await connector.call(
                "payments.customers.contact", context(scope), {"customer": "cus_fake3"}
            )
        assert failed.value.error.cause.value == "out_of_scope"


async def test_the_invoices_of_a_month_are_read_in_minor_units(provider: str) -> None:
    connector = payments(provider)
    result = await connector.call("payments.invoices.list", context(), {"status": "paid"})
    assert result.output["month"]
    assert all(i["status"] == "paid" for i in result.output["invoices"])
    records = [
        payment_service.invoice(1, "cus_fake1", created=1793491200),  # 2026-11-01 00:00 UTC
        payment_service.invoice(2, "cus_fake2", created=1793491199),  # the month before
    ]
    replace(provider, records, "invoices")
    november = await connector.call("payments.invoices.list", context(), {"month": "2026-11"})
    assert november.output["month"] == "2026-11"
    [only] = november.output["invoices"]
    assert only == {
        "id": "in_fake1",
        "number": "FAKE-0001",
        "customer": "cus_fake1",
        "subscription": "sub_fake1",
        "status": "paid",
        "currency": "EUR",
        "total": 999,
        "tax": 19,
        "paid": 999,
        "remaining": 0,
        "issued_at": 1793491200,
        "due_at": None,
        "paid_at": 1793491260,
    }
    assert "@customer.example" not in json.dumps(november.output)


async def test_the_undelivered_events_name_their_object_and_nothing_of_it(provider: str) -> None:
    result = await payments(provider).call("payments.events.undelivered", context(), {})
    [event] = result.output["events"]
    assert event["id"] == "evt_fake2" and event["type"] == "invoice.payment_failed"
    assert event["pending_webhooks"] == 1
    assert (event["object"], event["subject"]) == ("invoice", "in_fake2")
    assert "@customer.example" not in json.dumps(result.output)


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("payments.invoices.list", {"month": "2026-13"}),
        ("payments.invoices.list", {"status": "refunded"}),
        ("payments.failures.list", {"limit": 0}),
    ],
)
async def test_a_month_or_status_it_cannot_ask_is_invalid(
    provider: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await payments(provider).call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"
