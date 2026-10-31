"""The `invoice` rule: an invoice's amounts computed again by EN 16931's calculation rules and
matched against its order (ADR-0169, UC-04).

Pure: readings in the shapes the documents and the accounting connectors give, a verdict out.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from taktus.components.run.domain.model import InvoiceRule, RuleFailed
from taktus.components.run.domain.service.invoices import invoice

INVOICE: dict[str, Any] = {
    "syntax": "ubl",
    "type": "invoice",
    "number": "INV-2026-0042",
    "issue_date": "2026-10-20",
    "due_date": "2026-11-19",
    "currency": "EUR",
    "order_reference": "PO-7",
    "seller": {"name": "Hosting Example GmbH", "vat_id": "DE123456789"},
    "payment": {"account": "DE02120300000000202051"},
    "lines": [
        {"id": "1", "quantity": "3", "price": "33.33", "net_amount": "99.99", "order_line": "1"},
        {"id": "2", "quantity": "1", "price": "0.01", "net_amount": "0.01", "order_line": "2"},
    ],
    "tax": [{"category": "S", "rate": "19", "base": "100.00", "amount": "19.00"}],
    "totals": {
        "lines": "100.00",
        "without_tax": "100.00",
        "tax": "19.00",
        "with_tax": "119.00",
        "payable": "119.00",
    },
}
ORDER: dict[str, Any] = {
    "reference": "PO-7",
    "currency": "EUR",
    "supplier": {"vat_id": "DE123456789", "account": "DE02120300000000202051"},
    "lines": [
        {"id": "1", "price": "33.33", "received": "3"},
        {"id": "2", "price": "0.01", "received": "5", "invoiced": "1"},
    ],
    "net_total": "200.00",
    "net_invoiced": "100.00",
    "account": "4930",
    "cost_centre": "hosting",
}


def changed(document: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(document)
    *parents, last = path.split(".")
    here: Any = out
    for part in parents:
        here = here[int(part)] if part.isdigit() else here[part]
    here[int(last) if last.isdigit() else last] = value
    return out


def test_an_invoice_that_holds_gives_its_amounts_exactly_as_decimal_text() -> None:
    verdict = invoice(INVOICE, ORDER)
    assert verdict["matched"] is True
    assert (verdict["net"], verdict["tax"], verdict["gross"], verdict["payable"]) == (
        "100.00",
        "19.00",
        "119.00",
        "119.00",
    )
    assert verdict["account"] == "4930" and verdict["order"] == "PO-7"
    assert verdict["taxes"] == [
        {"category": "S", "rate": "19", "base": "100.00", "amount": "19.00"}
    ]
    assert invoice(INVOICE, ORDER) == verdict, "the same readings give the same verdict"


def test_the_tax_is_rounded_half_up_to_the_cent() -> None:
    odd = changed(INVOICE, "lines.1.net_amount", "0.05")
    odd = changed(odd, "lines.1.price", "0.05")
    odd = changed(odd, "tax.0.base", "100.04")
    odd = changed(odd, "tax.0.amount", "19.01")  # 100.04 x 19 % = 19.0076
    odd["totals"] = {
        "lines": "100.04",
        "without_tax": "100.04",
        "tax": "19.01",
        "with_tax": "119.05",
        "payable": "119.05",
    }
    order = changed(changed(ORDER, "lines.1.price", "0.05"), "net_invoiced", "0.00")
    assert invoice(odd, order)["payable"] == "119.05"


@pytest.mark.parametrize(
    ("path", "value", "named"),
    [
        ("lines.0.net_amount", "100.00", "line 1: the invoice states 100.00, computed 99.99"),
        ("totals.lines", "100.01", "BR-CO-10"),
        ("totals.without_tax", "99.00", "BR-CO-13"),
        ("tax.0.amount", "19.10", "tax amount of S 19%"),
        ("totals.tax", "19.10", "BR-CO-14"),
        ("totals.with_tax", "120.00", "BR-CO-15"),
        ("totals.payable", "118.00", "BR-CO-16"),
        ("tax.0.base", "90.00", "tax base"),
    ],
)
def test_a_total_the_parts_do_not_give_fails_and_names_its_rule(
    path: str, value: str, named: str
) -> None:
    with pytest.raises(RuleFailed, match="does not hold") as failed:
        invoice(changed(INVOICE, path, value), ORDER)
    assert named in str(failed.value)


@pytest.mark.parametrize(
    ("document", "order", "named"),
    [
        (changed(INVOICE, "currency", "USD"), ORDER, "currency"),
        (changed(INVOICE, "seller.vat_id", "DE999999999"), ORDER, "seller"),
        (
            changed(INVOICE, "payment.account", "DE89370400440532013000"),
            ORDER,
            "account to be paid",
        ),
        (INVOICE, changed(ORDER, "lines.0.price", "30.00"), "line 1: the price"),
        (INVOICE, changed(ORDER, "lines.0.received", "2"), "line 1: 3 invoiced, 2 received"),
        (INVOICE, changed(ORDER, "lines.1.id", "9"), "the order has no line '2'"),
        (INVOICE, changed(ORDER, "net_invoiced", "150.00"), "50.00 open on the order"),
        (changed(INVOICE, "type", "credit_note"), ORDER, "a credit note is not paid"),
    ],
)
def test_an_invoice_that_does_not_match_its_order_fails_and_names_the_difference(
    document: dict[str, Any], order: dict[str, Any], named: str
) -> None:
    with pytest.raises(RuleFailed) as failed:
        invoice(document, order)
    assert named in str(failed.value)


def test_an_amount_that_is_not_decimal_text_is_refused() -> None:
    with pytest.raises(RuleFailed, match="decimal text"):
        invoice(changed(INVOICE, "totals.payable", 119.0), ORDER)


def test_the_rule_parses_as_rule_work() -> None:
    work = InvoiceRule.model_validate({"rule": "invoice", "invoice": {}, "order": {}})
    assert work.rule == "invoice"
