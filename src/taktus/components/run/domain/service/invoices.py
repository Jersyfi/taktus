"""The `invoice` rule: an incoming invoice's amounts computed again and matched against what was
ordered (ADR-0169, UC-04). Pure: two readings in, a verdict out, in decimal arithmetic.

The invoice is a reading of its business terms as the European standard for electronic invoices,
EN 16931, names them (`BT-…`): the documents connector gives it, whichever syntax the document
came in. The order is a reading of what was ordered or contracted, as the accounting system
holds it: a purchase order, or a standing contract such as a subscription.

**The amounts are recomputed** by the standard's calculation rules, each from the parts the
document states, and compared with the totals it states:

- *line*: each line's net amount (BT-131) is its quantity (BT-129) times its price (BT-146),
  rounded to the cent, where the line states a price;
- *BR-CO-10*: the sum of the lines' net amounts is the lines' total (BT-106);
- *BR-CO-13*: the total without tax (BT-109) is that sum, less the allowances (BT-107), plus
  the charges (BT-108);
- *tax base*: the tax bases of the categories (BT-116) sum to the total without tax;
- *tax amount*: each category's tax (BT-117) is its base times its rate (BT-119), rounded half
  up to the cent;
- *BR-CO-14*: the tax total (BT-110) is the sum of the categories' taxes;
- *BR-CO-15*: the total with tax (BT-112) is the total without tax plus the tax total;
- *BR-CO-16*: the amount due (BT-115) is the total with tax, less what was paid (BT-113), plus
  the rounding (BT-114).

**The invoice is matched** against the order: the same currency, the same seller by its tax
identifier, the account to be paid where both name one, each line's price, a quantity no greater
than what was received less what was invoiced before, and a total without tax no greater than
what remains open. A credit note is not paid.

Every difference is named. Any difference fails the step: no amount leaves it, and the run goes
to a person, who sees each difference. Nothing here estimates, rounds before the end, or reads
words: the same readings always give the same verdict, which is what admits it for `exact`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from taktus.components.run.domain.model.errors import RuleFailed

CENT = Decimal("0.01")


def _decimal(value: Any, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise RuleFailed(f"{what} is not an amount given as decimal text: {value!r}")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise RuleFailed(f"{what} is not an amount: {value!r}") from error
    if not number.is_finite():
        raise RuleFailed(f"{what} is not a finite amount: {value!r}")
    return number


def _optional(value: Any, what: str) -> Decimal:
    return Decimal(0) if value is None else _decimal(value, what)


def _text(number: Decimal) -> str:
    return format(number, "f")


def _cent(number: Decimal) -> Decimal:
    return number.quantize(CENT, rounding=ROUND_HALF_UP)


def _mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuleFailed(f"{what} is not an object")
    return value


def _list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise RuleFailed(f"{what} is not a non-empty list")
    return value


def _same(differences: list[str], rule: str, stated: Decimal, computed: Decimal) -> None:
    if stated != computed:
        differences.append(
            f"{rule}: the invoice states {_text(stated)}, computed {_text(computed)}"
        )


def recomputed(invoice: Mapping[str, Any]) -> tuple[dict[str, Decimal], list[str]]:
    """The invoice's totals as it states them, and every calculation rule that does not hold."""
    differences: list[str] = []
    totals = _mapping(invoice.get("totals"), "the invoice's totals")
    lines = _list(invoice.get("lines"), "the invoice's lines")
    net_sum = Decimal(0)
    for index, given in enumerate(lines):
        line = _mapping(given, f"line {index + 1}")
        name = str(line.get("id") or index + 1)
        net = _decimal(line.get("net_amount"), f"the net amount of line {name}")
        net_sum += net
        if line.get("price") is not None:
            quantity = _decimal(line.get("quantity"), f"the quantity of line {name}")
            price = _decimal(line.get("price"), f"the price of line {name}")
            _same(differences, f"line {name}", net, _cent(quantity * price))
    stated = {
        key: _optional(totals.get(key), f"the total {key}")
        for key in ("lines", "allowances", "charges", "without_tax", "tax", "with_tax")
    }
    stated["prepaid"] = _optional(totals.get("prepaid"), "the amount paid")
    stated["rounding"] = _optional(totals.get("rounding"), "the rounding amount")
    stated["payable"] = _decimal(totals.get("payable"), "the amount due")
    _same(differences, "BR-CO-10", stated["lines"], net_sum)
    _same(
        differences,
        "BR-CO-13",
        stated["without_tax"],
        stated["lines"] - stated["allowances"] + stated["charges"],
    )
    base_sum = Decimal(0)
    tax_sum = Decimal(0)
    for index, given in enumerate(_list(invoice.get("tax"), "the invoice's tax breakdown")):
        category = _mapping(given, f"tax category {index + 1}")
        name = f"{category.get('category', '?')} {category.get('rate', '?')}%"
        base = _decimal(category.get("base"), f"the tax base of {name}")
        rate = _decimal(category.get("rate"), f"the tax rate of {name}")
        amount = _decimal(category.get("amount"), f"the tax amount of {name}")
        base_sum += base
        tax_sum += amount
        _same(differences, f"tax amount of {name}", amount, _cent(base * rate / 100))
    _same(differences, "tax base", stated["without_tax"], base_sum)
    _same(differences, "BR-CO-14", stated["tax"], tax_sum)
    _same(differences, "BR-CO-15", stated["with_tax"], stated["without_tax"] + stated["tax"])
    _same(
        differences,
        "BR-CO-16",
        stated["payable"],
        stated["with_tax"] - stated["prepaid"] + stated["rounding"],
    )
    return stated, differences


def matched(invoice: Mapping[str, Any], order: Mapping[str, Any], net: Decimal) -> list[str]:
    """Every way the invoice differs from what was ordered."""
    differences: list[str] = []
    if invoice.get("type") == "credit_note":
        differences.append("the document is a credit note: a credit note is not paid")
    if invoice.get("currency") != order.get("currency"):
        differences.append(
            f"currency: the invoice is in {invoice.get('currency')!r}, the order in "
            f"{order.get('currency')!r}"
        )
    seller = _mapping(invoice.get("seller") or {}, "the seller")
    supplier = _mapping(order.get("supplier") or {}, "the order's supplier")
    if not seller.get("vat_id") or seller.get("vat_id") != supplier.get("vat_id"):
        differences.append(
            f"seller: the invoice names the tax identifier {seller.get('vat_id')!r}, the order "
            f"{supplier.get('vat_id')!r}"
        )
    payee = (invoice.get("payment") or {}).get("account")
    known = supplier.get("account")
    if payee is not None and payee != known:
        differences.append(
            "account to be paid: the invoice names another account than the one the "
            "accounting system holds for the supplier"
        )
    ordered = {
        str(line.get("id")): line
        for line in _list(order.get("lines"), "the order's lines")
        if isinstance(line, Mapping)
    }
    for index, given in enumerate(invoice.get("lines") or []):
        line = _mapping(given, f"line {index + 1}")
        name = str(line.get("id") or index + 1)
        reference = str(line.get("order_line") or line.get("id") or "")
        against = ordered.get(reference)
        if against is None:
            differences.append(f"line {name}: the order has no line {reference!r}")
            continue
        if line.get("price") is not None and _decimal(
            line["price"], f"the price of line {name}"
        ) != _decimal(against.get("price"), f"the ordered price of line {reference}"):
            differences.append(
                f"line {name}: the price is {line['price']}, ordered at {against.get('price')}"
            )
        quantity = _decimal(line.get("quantity"), f"the quantity of line {name}")
        open_quantity = _decimal(
            against.get("received"), f"the quantity received of line {reference}"
        ) - _optional(against.get("invoiced"), f"the quantity invoiced of line {reference}")
        if quantity > open_quantity:
            differences.append(
                f"line {name}: {_text(quantity)} invoiced, {_text(open_quantity)} received "
                "and not yet invoiced"
            )
    remaining = _decimal(order.get("net_total"), "the order's net total") - _optional(
        order.get("net_invoiced"), "what was invoiced against the order"
    )
    if net > remaining:
        differences.append(
            f"total without tax: {_text(net)} invoiced, {_text(remaining)} open on the order"
        )
    return differences


def invoice(invoice: Any, order: Any) -> dict[str, Any]:
    """The verdict on one invoice: its amounts recomputed and matched against the order. Any
    difference fails the step, naming each."""
    read = _mapping(invoice, "the invoice")
    against = _mapping(order, "the order")
    stated, differences = recomputed(read)
    differences += matched(read, against, stated["without_tax"])
    if differences:
        raise RuleFailed(
            f"the invoice {read.get('number')!r} does not hold: " + "; ".join(differences)
        )
    if stated["payable"] <= 0:
        raise RuleFailed(f"the invoice {read.get('number')!r} leaves nothing to pay")
    return {
        "matched": True,
        "document": read.get("number"),
        "order": against.get("reference"),
        "supplier": (read.get("seller") or {}).get("vat_id"),
        "currency": read.get("currency"),
        "issue_date": read.get("issue_date"),
        "due_date": read.get("due_date"),
        "net": _text(stated["without_tax"]),
        "tax": _text(stated["tax"]),
        "gross": _text(stated["with_tax"]),
        "payable": _text(stated["payable"]),
        "amounts": {"net": _text(stated["without_tax"]), "tax": _text(stated["tax"])},
        "account": against.get("account"),
        "cost_centre": against.get("cost_centre"),
        "taxes": [
            {
                "category": c.get("category"),
                "rate": str(c.get("rate")),
                "base": str(c.get("base")),
                "amount": str(c.get("amount")),
            }
            for c in read.get("tax") or []
            if isinstance(c, Mapping)
        ],
    }
