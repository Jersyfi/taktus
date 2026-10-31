"""The documents connector reads an inbox's invoices as EN 16931 business terms, and the
accounting connector reads orders and proposes into the accounting system, each write once per
key (ADR-0169, UC-15.8).

Against the fakes under `tests/fakes/document_inbox_service.py` and
`tests/fakes/accounting_service.py`, each in a thread of this process. The connectors are served
in-process over MCP, as an instance reaches them.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import accounting_service, document_inbox_service
from taktus_connectors.accounting import operations as accounting_operations
from taktus_connectors.accounting.server import build_server as accounting_server
from taktus_connectors.einvoice import standard
from taktus_connectors.einvoice.operations import Config as InboxConfig
from taktus_connectors.einvoice.server import build_server as inbox_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
DOCUMENTS = Path(document_inbox_service.__file__).parent / "documents"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DOCUMENTS_TOKEN", "ACCOUNTING_TOKEN"):
        path = tmp_path / name
        path.write_text(TOKEN, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))


def _serve(make: object) -> Iterator[str]:
    server = make("127.0.0.1", 0, {TOKEN})  # type: ignore[operator]
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def inbox() -> Iterator[str]:
    yield from _serve(document_inbox_service.make_server)


@pytest.fixture
def books() -> Iterator[str]:
    yield from _serve(accounting_service.make_server)


def context(name: str, attempt: int = 1, step: str = "read") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_finance",
        run_id="run_invoice",
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key("run_invoice", step, attempt),
        credentials=(CredentialReference(name=name, injected_as="env"),),
    )


async def state_of(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        answer: dict[str, Any] = (await client.get(f"{url}/_fake/state")).json()
    return answer


def documents(url: str) -> McpActionConnector:
    return McpActionConnector(inbox_server(InboxConfig(url, timeout=5.0)))


def accounting(url: str) -> McpActionConnector:
    return McpActionConnector(accounting_server(accounting_operations.Config(url, timeout=5.0)))


# --- the documents connector ---------------------------------------------------------------------


async def test_the_inbox_is_listed_by_document_name(inbox: str) -> None:
    result = await documents(inbox).call("documents.invoices.list", context("DOCUMENTS_TOKEN"), {})
    assert result.effect.kind.value == "read"
    names = [d["document"] for d in result.output["documents"]]
    assert set(names) == {"invoice-cii.xml", "invoice-ubl.xml", "not-an-invoice.xml"}
    assert all(d["size"] > 0 and d["etag"] for d in result.output["documents"])
    assert result.output["complete"] is True


async def test_a_ubl_invoice_is_read_as_its_business_terms_amounts_as_given(inbox: str) -> None:
    result = await documents(inbox).call(
        "documents.invoices.read", context("DOCUMENTS_TOKEN"), {"document": "invoice-ubl.xml"}
    )
    read = result.output
    assert (read["syntax"], read["type"], read["number"]) == ("ubl", "invoice", "INV-2026-0042")
    assert (read["issue_date"], read["due_date"], read["currency"]) == (
        "2026-10-20",
        "2026-11-19",
        "EUR",
    )
    assert read["order_reference"] == "PO-7"
    assert read["seller"] == {"name": "Hosting Example GmbH", "vat_id": "DE123456789"}
    assert read["payment"] == {"account": "DE02120300000000202051"}
    assert [
        (line["id"], line["quantity"], line["price"], line["net_amount"]) for line in read["lines"]
    ] == [
        ("1", "3", "33.33", "99.99"),
        ("2", "1", "0.01", "0.01"),
    ]
    assert read["tax"] == [{"category": "S", "rate": "19", "base": "100.00", "amount": "19.00"}]
    assert read["totals"]["payable"] == "119.00" and read["totals"]["tax"] == "19.00"
    content = (DOCUMENTS / "invoice-ubl.xml").read_bytes()
    assert read["digest"].startswith("sha256:") and len(content) > 0


async def test_a_cii_invoice_is_read_in_the_same_shape(inbox: str) -> None:
    result = await documents(inbox).call(
        "documents.invoices.read", context("DOCUMENTS_TOKEN"), {"document": "invoice-cii.xml"}
    )
    read = result.output
    assert (read["syntax"], read["number"], read["issue_date"], read["due_date"]) == (
        "cii",
        "INV-2026-0043",
        "2026-10-21",
        "2026-11-20",
    )
    assert read["seller"]["vat_id"] == "DE987654321" and read["order_reference"] == "PO-8"
    assert read["lines"][0]["price"] == "10.00" and read["lines"][0]["quantity"] == "12"
    assert read["totals"]["payable"] == "142.80"
    assert set(read) == set(standard.parse((DOCUMENTS / "invoice-ubl.xml").read_bytes())) | {
        "document",
        "digest",
    }


async def test_a_document_that_is_no_invoice_or_outside_the_folder_is_invalid(inbox: str) -> None:
    connector = documents(inbox)
    for name in ("not-an-invoice.xml", "missing.xml", "../etc/passwd", ".hidden"):
        with pytest.raises(CallFailed) as failed:
            await connector.call(
                "documents.invoices.read", context("DOCUMENTS_TOKEN"), {"document": name}
            )
        assert failed.value.error.cause.value == "invalid", name


async def test_a_document_that_declares_an_entity_is_refused_unparsed(inbox: str) -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
        b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">&lol;</Invoice>'
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        await client.post(f"{inbox}/_fake/documents?name=bomb.xml", content=bomb)
    with pytest.raises(CallFailed, match="document type or an entity"):
        await documents(inbox).call(
            "documents.invoices.read", context("DOCUMENTS_TOKEN"), {"document": "bomb.xml"}
        )
    with pytest.raises(standard.NotAnInvoice, match="larger than"):
        standard.parse(b" " * (standard.MAX_BYTES + 1))


# --- the accounting connector --------------------------------------------------------------------


BOOKING = {
    "document": "INV-2026-0042",
    "supplier": "DE123456789",
    "currency": "EUR",
    "issue_date": "2026-10-20",
    "due_date": "2026-11-19",
    "account": "4930",
    "net": "100.00",
    "tax": "19.00",
    "gross": "119.00",
    "taxes": [{"category": "S", "rate": "19", "base": "100.00", "amount": "19.00"}],
}


async def test_an_order_is_read_with_what_was_received(books: str) -> None:
    result = await accounting(books).call(
        "accounting.orders.read", context("ACCOUNTING_TOKEN"), {"reference": "PO-7"}
    )
    assert result.output["reference"] == "PO-7"
    assert result.output["supplier"]["vat_id"] == "DE123456789"
    assert [line["received"] for line in result.output["lines"]] == ["3", "1"]
    with pytest.raises(CallFailed) as failed:
        await accounting(books).call(
            "accounting.orders.read", context("ACCOUNTING_TOKEN"), {"reference": "PO-0"}
        )
    assert failed.value.error.cause.value == "invalid"


async def test_a_booking_is_proposed_once_per_key_and_a_repeat_finds_it(books: str) -> None:
    connector = accounting(books)
    first = await connector.call(
        "accounting.bookings.propose", context("ACCOUNTING_TOKEN", step="book"), BOOKING
    )
    again = await connector.call(
        "accounting.bookings.propose", context("ACCOUNTING_TOKEN", step="book"), BOOKING
    )
    assert first.effect.replayed is False and again.effect.replayed is True
    assert first.output["id"] == again.output["id"]
    state = await state_of(books)
    assert len(state["bookings"]) == 1
    assert state["bookings"][0]["mark"] == accounting_operations.mark_of(
        idempotency_key("run_invoice", "book", 1)
    )
    assert idempotency_key("run_invoice", "book", 1) not in str(state), "the key never leaves"


async def test_a_malformed_amount_never_reaches_the_books(books: str) -> None:
    connector = accounting(books)
    for change in ({"net": 100.0}, {"gross": "119.001"}, {"currency": "eur"}):
        with pytest.raises(CallFailed) as failed:
            await connector.call(
                "accounting.bookings.propose",
                context("ACCOUNTING_TOKEN", step="book"),
                {**BOOKING, **change},
            )
        assert failed.value.error.cause.value == "invalid"
    with pytest.raises(CallFailed, match="above zero"):
        await connector.call(
            "payment.release.submit",
            context("ACCOUNTING_TOKEN", step="pay"),
            {
                "document": "INV-1",
                "supplier": "DE123456789",
                "currency": "EUR",
                "amount": "0.00",
                "due_date": "2026-11-19",
            },
        )
    assert (await state_of(books))["bookings"] == []
