# ruff: noqa: F811 — every test requests the imported fixtures `outside` and `provider` by name
"""B-6.06 exports the month's outgoing invoices into the books as drafts, once, and never posts
one (UC-03 B-6.06, #402, ADR-0314).

The world of `test_software_operations_payments.py`, with the books connector behind
`accounting.invoices`, served in-process over MCP. What is faked: each payment provider's API
and the accounting system's REST API (`tests/fakes/books_service.py`). The bundle is the shipped
one.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import billing_plans_service as plans
from fakes import books_service, payment_service
from taktus_connectors.erpnext.operations import Config as BooksConfig
from taktus_connectors.erpnext.server import build_server as books_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.domain.model import RunState, StepState

from .test_software_operations import (
    Outside,
    outside,  # noqa: F401 — the fixture, requested by name
)
from .test_software_operations_payments import (
    PaymentsWorld,
    Provider,
    provider,  # noqa: F401 — the fixture
)
from .test_software_operations_payments_more import (
    CUSTOMERS,
    DAY,
    OCTOBER,
    failed,
    posted,
    until_export,
)

KEY = f"key-{secrets.token_hex(6)}:sig-{secrets.token_hex(12)}"


@pytest.fixture
def books(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = books_service.make_server("127.0.0.1", 0, {KEY})
    path = tmp_path / "BOOKS_TOKEN"
    path.write_text(KEY, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_BOOKS_TOKEN_FILE", str(path))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


class BooksWorld(PaymentsWorld):
    """The payments world, with the books behind `accounting.invoices`."""

    def __init__(self, outside: Outside, provider: Provider, books: str) -> None:
        super().__init__(outside, provider)
        served = McpActionConnector(
            books_server(
                BooksConfig(books, books_service.CUSTOMER, "Sales - EX", "VAT - EX", timeout=5.0)
            ),
            timeout=10.0,
        )
        pool = self.engine._connectors
        assert isinstance(pool, StaticConnectorPool)
        self.engine._connectors = StaticConnectorPool(
            [*pool._connectors, ("connector.books", served)]
        )


def drafts(books: str) -> list[dict[str, Any]]:
    held: dict[str, Any] = httpx.get(f"{books}/_fake/state", timeout=5).json()["invoices"]
    return [d for name, d in held.items() if name != books_service.SEEDED]


async def test_b_6_06_exports_the_months_issued_invoices_as_drafts_once(
    outside: Outside, provider: Provider, books: str
) -> None:
    if provider.name == "in-app":
        return  # the in-app service lists no invoices of a project (ADR-0214)
    if provider.name == "first":
        records = [
            payment_service.invoice(1, "cus_fake1", created=OCTOBER + DAY),
            payment_service.invoice(2, "cus_fake2", status="open", created=OCTOBER + 2 * DAY,
                                    failed=True),
            payment_service.invoice(3, "cus_fake3", status="void", created=OCTOBER + 3 * DAY),
        ]  # fmt: skip
    else:
        records = [
            plans.invoice(1, "2026-10-02"),
            plans.invoice(2, "2026-10-03", status="SENT"),
            plans.invoice(3, "2026-10-04", status="DRAFT"),
        ]
    posted(provider.url, "invoices", records)
    w = await BooksWorld(outside, provider, books).ready()
    version = await w.registered("B-6.06-outgoing-invoices.yaml")
    run = await until_export(w, await w.start(version, month="2026-10"))
    assert run.step_run("export").state is StepState.WAITING_HUMAN
    assert drafts(books) == [], "nothing reaches the books before a person confirmed it"
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, failed(run)
    exported = await w.result(run, "export")
    assert exported["output"]["created"] == 2
    held = drafts(books)
    assert len(held) == 2 and {d["docstatus"] for d in held} == {0}, "drafts, never posted"
    assert {d["grand_total"] for d in held} == {9.99}, "the provider's total, to the cent"
    assert {d["currency"] for d in held} == {"EUR"}

    again = await w.confirmed(await w.start(version, month="2026-10"))
    assert again.state is RunState.FINISHED, failed(again)
    second = await w.result(again, "export")
    assert (second["output"]["created"], second["output"]["before"]) == (0, 2)
    assert len(drafts(books)) == 2, "a month run again exports none of its invoices twice"


async def test_b_6_06_exports_nothing_for_a_month_without_issued_invoices(
    outside: Outside, books: str
) -> None:
    first = Provider("first", outside.payments, CUSTOMERS, "prod_plan", ())
    posted(outside.payments, "invoices", [])
    w = await BooksWorld(outside, first, books).ready()
    version = await w.registered("B-6.06-outgoing-invoices.yaml")
    run = await w.confirmed(await w.start(version, month="2026-10"))
    assert run.state is RunState.FINISHED, failed(run)
    assert (await w.result(run, "export"))["skipped"] is True
    assert drafts(books) == []
