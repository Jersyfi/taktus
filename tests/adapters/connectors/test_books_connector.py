"""The books connector exports outgoing invoices as drafts once, never twice across runs, and
never posts one, against the fake API (`accounting.invoices`, ADR-0314).

The fake under `tests/fakes/books_service.py` runs in a thread of this process; the connector
is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import books_service
from fakes.ports import free_port
from taktus_connectors.erpnext.operations import Config, major
from taktus_connectors.erpnext.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

KEY = f"key-{secrets.token_hex(6)}:sig-{secrets.token_hex(12)}"
OCTOBER = 1790899200  # 2026-10-02 00:00 UTC


def invoice(number: str, total: Any = 1190, tax: Any = 190, **more: Any) -> dict[str, Any]:
    return {
        "number": number,
        "currency": "EUR",
        "status": "paid",
        "total": total,
        "tax": tax,
        "issued_at": OCTOBER,
        "due_at": OCTOBER + 14 * 86_400,
        **more,
    }


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    port = free_port()
    server = books_service.make_server("127.0.0.1", port, {KEY})
    path = tmp_path / "BOOKS_TOKEN"
    path.write_text(KEY, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_BOOKS_TOKEN_FILE", str(path))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def context(run: str, step: str = "export") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_books",
        run_id=run,
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key(run, step, 1),
        credentials=(CredentialReference(name="BOOKS_TOKEN", injected_as="env"),),
    )


def connector(url: str, *, income: str = "Sales - EX") -> McpActionConnector:
    config = Config(url, "Online customers", income, "VAT - EX", timeout=5.0)
    return McpActionConnector(build_server(config))


def held(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()["invoices"]
    return {k: v for k, v in found.items() if k != books_service.SEEDED}


def test_minor_units_become_the_major_unit_by_the_currency_s_exponent() -> None:
    assert major(1190, "EUR") == Decimal("11.90")
    assert major(1190, "JPY") == Decimal("1190")
    assert major(1190, "KWD") == Decimal("1.190")


async def test_an_invoice_is_exported_as_a_draft_with_its_net_line_and_its_tax(api: str) -> None:
    result = await connector(api).call(
        "accounting.invoices.export", context("run_1"), {"invoices": [invoice("INV-1")]}
    )
    assert result.effect.replayed is False
    assert result.output["created"] == 1
    [(name, draft)] = held(api).items()
    assert draft["docstatus"] == 0, "a draft: a person submits it"
    assert draft["customer"] == "Online customers" and draft["currency"] == "EUR"
    assert draft["posting_date"] == "2026-10-02" and draft["due_date"] == "2026-10-16"
    assert draft["items"][0]["rate"] == 10.0 and draft["items"][0]["income_account"] == "Sales - EX"
    assert draft["taxes"] == [
        {
            "charge_type": "Actual",
            "account_head": "VAT - EX",
            "description": "Tax of the payment provider's invoice",
            "tax_amount": 1.9,
        }
    ]
    assert draft["grand_total"] == 11.9
    read = await connector(api).call("accounting.invoices.read", context("r"), {"name": name})
    assert read.output["status"] == "draft" and read.output["mark"].startswith("taktus:INV-1:")
    assert KEY not in str(result.output) + str(read.output)


async def test_a_repeat_replays_and_another_run_exports_nothing_twice(api: str) -> None:
    batch = {"invoices": [invoice("INV-1"), invoice("INV-2", total=999, tax=0)]}
    first = await connector(api).call("accounting.invoices.export", context("run_1"), batch)
    again = await connector(api).call("accounting.invoices.export", context("run_1"), batch)
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert again.output["replayed"] == 2
    later = await connector(api).call(
        "accounting.invoices.export",
        context("run_2"),
        {"invoices": [*batch["invoices"], invoice("INV-3")]},
    )
    assert [e["export"] for e in later.output["exported"]] == ["before", "before", "created"]
    assert len(held(api)) == 3, "each invoice once in the books"
    no_tax = next(d for d in held(api).values() if d["remarks"].startswith("taktus:INV-2:"))
    assert no_tax["taxes"] == []


@pytest.mark.parametrize(
    "bad",
    [
        invoice("INV-1", total=100, tax=190),
        invoice("INV-1", total="11.90"),
        invoice("INV-1", currency="eur"),
        invoice("", total=1),
        {k: v for k, v in invoice("INV-1").items() if k != "issued_at"},
    ],
)
async def test_one_malformed_invoice_refuses_the_batch_before_any_request(
    api: str, bad: dict[str, Any]
) -> None:
    with pytest.raises(CallFailed) as refused:
        await connector(api).call(
            "accounting.invoices.export",
            context("run_1"),
            {"invoices": [invoice("INV-0"), bad]},
        )
    assert refused.value.error.cause.value == "invalid"
    assert held(api) == {}


async def test_an_account_the_books_do_not_hold_is_refused_and_a_stranger_is_not_admitted(
    api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CallFailed) as refused:
        await connector(api, income="Nowhere").call(
            "accounting.invoices.export", context("run_1"), {"invoices": [invoice("INV-1")]}
        )
    assert refused.value.error.cause.value == "invalid"
    stranger = tmp_path / "STRANGER"
    stranger.write_text("key-x:sig-y", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_BOOKS_TOKEN_FILE", str(stranger))
    with pytest.raises(CallFailed) as unknown:
        await connector(api).call(
            "accounting.invoices.read", context("r"), {"name": books_service.SEEDED}
        )
    assert unknown.value.error.cause.value == "unauthenticated"
    assert held(api) == {}
