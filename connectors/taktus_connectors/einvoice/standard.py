"""An electronic invoice read as the business terms of EN 16931, from either of its syntaxes.

EN 16931-1 is the European standard's semantic model of an invoice: each item of it is a
**business term**, `BT-1` the invoice number, `BT-115` the amount due. Two syntaxes carry it
(CEN/TS 16931-3): the OASIS Universal Business Language, UBL 2.1, as an `Invoice` or a
`CreditNote`, and the UN/CEFACT Cross Industry Invoice, CII D16B, as a `CrossIndustryInvoice`.
National profiles — XRechnung, the XML of ZUGFeRD and Factur-X, Peppol BIS Billing 3.0 — are
documents in one of the two, and are read as the syntax they are in.

What is read is what a check of the amounts and a match against an order need: the document's
number, type, dates, currency and references; the seller by name and tax identifier; the account
to be paid; each line; the tax breakdown; the totals. Every amount stays the decimal text the
document gave. Nothing is rounded, summed or computed here: recomputing is the rule's
(ADR-0169), and a reading that already did it could not be checked.

**Parsing is defused.** A document that declares a document type (`<!DOCTYPE`) or an entity
(`<!ENTITY`) is refused before it is parsed: neither syntax needs one, and one is how an
entity expansion or an external reference gets into a parser. A document above `MAX_BYTES` is
refused too. The parser is the standard library's, over the bytes that remain.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from decimal import Decimal, InvalidOperation
from typing import Any

type Json = dict[str, Any]

MAX_BYTES = 5 * 1024 * 1024
FORBIDDEN = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)

UBL_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
UBL_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CII = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "rsm": CII,
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
CREDIT_NOTE_CODES = frozenset({"381", "396", "532"})
"""Type codes (UNTDID 1001, BT-3) of a credit note; every other one is an invoice."""


class NotAnInvoice(ValueError):
    """The document is not an electronic invoice this module reads; the message says why."""


def parse(content: bytes) -> Json:
    """The business terms of one document, or NotAnInvoice."""
    if len(content) > MAX_BYTES:
        raise NotAnInvoice(f"the document is larger than {MAX_BYTES} bytes")
    if FORBIDDEN.search(content):
        raise NotAnInvoice("the document declares a document type or an entity; refused unparsed")
    try:
        # Defused: a document type or an entity was refused above, before parsing.
        root = ElementTree.fromstring(content)  # noqa: S314
    except ElementTree.ParseError as error:
        raise NotAnInvoice(f"the document is not well-formed XML: {error}") from error
    if root.tag == f"{{{UBL_INVOICE}}}Invoice":
        return _ubl(root, credit=False)
    if root.tag == f"{{{UBL_CREDIT_NOTE}}}CreditNote":
        return _ubl(root, credit=True)
    if root.tag == f"{{{CII}}}CrossIndustryInvoice":
        return _cii(root)
    raise NotAnInvoice(f"the document's root {root.tag!r} is neither a UBL invoice nor a CII one")


def _text(element: ElementTree.Element | None, path: str) -> str | None:
    if element is None:
        return None
    found = element.find(path, NS)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def _required(element: ElementTree.Element, path: str, term: str) -> str:
    value = _text(element, path)
    if value is None:
        raise NotAnInvoice(f"the document has no {term}")
    return value


def _price(amount: str | None, base: str | None) -> str | None:
    """The price of one unit (BT-146), over the base quantity (BT-149) where one is not 1."""
    if amount is None or base in (None, "1", "1.0", "1.00"):
        return amount
    try:
        return format(Decimal(amount) / Decimal(base or "1"), "f")
    except (InvalidOperation, ZeroDivisionError) as error:
        raise NotAnInvoice(f"a price's base quantity {base!r} cannot divide it") from error


def _ubl(root: ElementTree.Element, *, credit: bool) -> Json:
    line_tag, quantity_tag = (
        ("cac:CreditNoteLine", "cbc:CreditedQuantity")
        if credit
        else ("cac:InvoiceLine", "cbc:InvoicedQuantity")
    )
    code = _text(root, "cbc:CreditNoteTypeCode" if credit else "cbc:InvoiceTypeCode")
    party = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    lines: list[Json] = []
    for line in root.findall(line_tag, NS):
        quantity = line.find(quantity_tag, NS)
        tax = line.find("cac:Item/cac:ClassifiedTaxCategory", NS)
        lines.append(
            {
                "id": _text(line, "cbc:ID"),
                "quantity": None if quantity is None else (quantity.text or "").strip(),
                "unit": None if quantity is None else quantity.get("unitCode"),
                "net_amount": _text(line, "cbc:LineExtensionAmount"),
                "order_line": _text(line, "cac:OrderLineReference/cbc:LineID"),
                "item": _text(line, "cac:Item/cbc:Name"),
                "tax_category": _text(tax, "cbc:ID"),
                "tax_rate": _text(tax, "cbc:Percent"),
                "price": _price(
                    _text(line, "cac:Price/cbc:PriceAmount"),
                    _text(line, "cac:Price/cbc:BaseQuantity"),
                ),
            }
        )
    currency = _required(root, "cbc:DocumentCurrencyCode", "currency (BT-5)")
    tax_total = _tax_total_ubl(root, currency)
    totals = root.find("cac:LegalMonetaryTotal", NS)
    if totals is None:
        raise NotAnInvoice("the document has no totals (BG-22)")
    return {
        "syntax": "ubl",
        "type": "credit_note" if credit or code in CREDIT_NOTE_CODES else "invoice",
        "type_code": code,
        "number": _required(root, "cbc:ID", "number (BT-1)"),
        "issue_date": _required(root, "cbc:IssueDate", "issue date (BT-2)"),
        "due_date": _text(root, "cbc:DueDate")
        or _text(root, "cac:PaymentMeans/cbc:PaymentDueDate"),
        "currency": currency,
        "buyer_reference": _text(root, "cbc:BuyerReference"),
        "order_reference": _text(root, "cac:OrderReference/cbc:ID"),
        "contract_reference": _text(root, "cac:ContractDocumentReference/cbc:ID"),
        "seller": {
            "name": _text(party, "cac:PartyLegalEntity/cbc:RegistrationName")
            or _text(party, "cac:PartyName/cbc:Name"),
            "vat_id": _text(party, "cac:PartyTaxScheme/cbc:CompanyID"),
        },
        "payment": {"account": _text(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID")},
        "lines": lines,
        "tax": [
            {
                "category": _text(sub, "cac:TaxCategory/cbc:ID"),
                "rate": _text(sub, "cac:TaxCategory/cbc:Percent"),
                "base": _text(sub, "cbc:TaxableAmount"),
                "amount": _text(sub, "cbc:TaxAmount"),
            }
            for sub in ([] if tax_total is None else tax_total.findall("cac:TaxSubtotal", NS))
        ],
        "totals": {
            "lines": _text(totals, "cbc:LineExtensionAmount"),
            "allowances": _text(totals, "cbc:AllowanceTotalAmount"),
            "charges": _text(totals, "cbc:ChargeTotalAmount"),
            "without_tax": _text(totals, "cbc:TaxExclusiveAmount"),
            "tax": None if tax_total is None else _text(tax_total, "cbc:TaxAmount"),
            "with_tax": _text(totals, "cbc:TaxInclusiveAmount"),
            "prepaid": _text(totals, "cbc:PrepaidAmount"),
            "rounding": _text(totals, "cbc:PayableRoundingAmount"),
            "payable": _text(totals, "cbc:PayableAmount"),
        },
    }


def _tax_total_ubl(root: ElementTree.Element, currency: str) -> ElementTree.Element | None:
    """The tax total in the document's currency (BT-110): the one with a breakdown, or the one
    whose amount is in that currency."""
    for total in root.findall("cac:TaxTotal", NS):
        if total.find("cac:TaxSubtotal", NS) is not None:
            return total
    for total in root.findall("cac:TaxTotal", NS):
        amount = total.find("cbc:TaxAmount", NS)
        if amount is not None and amount.get("currencyID") in (None, currency):
            return total
    return None


def _date_102(element: ElementTree.Element | None, path: str) -> str | None:
    """A CII date of format 102, `YYYYMMDD`, as `YYYY-MM-DD`."""
    value = _text(element, path)
    if value is None:
        return None
    if re.fullmatch(r"\d{8}", value) is None:
        raise NotAnInvoice(f"the date {value!r} is not of the format 102, YYYYMMDD")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _cii(root: ElementTree.Element) -> Json:
    document = root.find("rsm:ExchangedDocument", NS)
    trade = root.find("rsm:SupplyChainTradeTransaction", NS)
    if document is None or trade is None:
        raise NotAnInvoice("the document has no exchanged document or no trade transaction")
    agreement = trade.find("ram:ApplicableHeaderTradeAgreement", NS)
    settlement = trade.find("ram:ApplicableHeaderTradeSettlement", NS)
    if settlement is None:
        raise NotAnInvoice("the document has no header trade settlement")
    seller = None if agreement is None else agreement.find("ram:SellerTradeParty", NS)
    vat_id = None
    for registration in (
        [] if seller is None else seller.findall("ram:SpecifiedTaxRegistration", NS)
    ):
        identifier = registration.find("ram:ID", NS)
        if identifier is not None and identifier.get("schemeID") == "VA":
            vat_id = (identifier.text or "").strip() or None
    code = _text(document, "ram:TypeCode")
    currency = _required(settlement, "ram:InvoiceCurrencyCode", "currency (BT-5)")
    summation = settlement.find("ram:SpecifiedTradeSettlementHeaderMonetarySummation", NS)
    if summation is None:
        raise NotAnInvoice("the document has no totals (BG-22)")
    tax_total = None
    for amount in summation.findall("ram:TaxTotalAmount", NS):
        if amount.get("currencyID") in (None, currency):
            tax_total = (amount.text or "").strip() or None
    lines: list[Json] = []
    for line in trade.findall("ram:IncludedSupplyChainTradeLineItem", NS):
        quantity = line.find("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NS)
        tax = line.find("ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax", NS)
        price = line.find("ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice", NS)
        lines.append(
            {
                "id": _text(line, "ram:AssociatedDocumentLineDocument/ram:LineID"),
                "quantity": None if quantity is None else (quantity.text or "").strip(),
                "unit": None if quantity is None else quantity.get("unitCode"),
                "net_amount": _text(
                    line,
                    "ram:SpecifiedLineTradeSettlement/"
                    "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
                ),
                "order_line": _text(
                    line,
                    "ram:SpecifiedLineTradeAgreement/ram:BuyerOrderReferencedDocument/ram:LineID",
                ),
                "item": _text(line, "ram:SpecifiedTradeProduct/ram:Name"),
                "tax_category": _text(tax, "ram:CategoryCode"),
                "tax_rate": _text(tax, "ram:RateApplicablePercent"),
                "price": _price(
                    _text(price, "ram:ChargeAmount"), _text(price, "ram:BasisQuantity")
                ),
            }
        )
    return {
        "syntax": "cii",
        "type": "credit_note" if code in CREDIT_NOTE_CODES else "invoice",
        "type_code": code,
        "number": _required(document, "ram:ID", "number (BT-1)"),
        "issue_date": _date_102(document, "ram:IssueDateTime/udt:DateTimeString"),
        "due_date": _date_102(
            settlement, "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString"
        ),
        "currency": currency,
        "buyer_reference": _text(agreement, "ram:BuyerReference"),
        "order_reference": _text(
            agreement, "ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID"
        ),
        "contract_reference": _text(
            agreement, "ram:ContractReferencedDocument/ram:IssuerAssignedID"
        ),
        "seller": {"name": _text(seller, "ram:Name"), "vat_id": vat_id},
        "payment": {
            "account": _text(
                settlement,
                "ram:SpecifiedTradeSettlementPaymentMeans/"
                "ram:PayeePartyCreditorFinancialAccount/ram:IBANID",
            )
        },
        "lines": lines,
        "tax": [
            {
                "category": _text(tax, "ram:CategoryCode"),
                "rate": _text(tax, "ram:RateApplicablePercent"),
                "base": _text(tax, "ram:BasisAmount"),
                "amount": _text(tax, "ram:CalculatedAmount"),
            }
            for tax in settlement.findall("ram:ApplicableTradeTax", NS)
        ],
        "totals": {
            "lines": _text(summation, "ram:LineTotalAmount"),
            "allowances": _text(summation, "ram:AllowanceTotalAmount"),
            "charges": _text(summation, "ram:ChargeTotalAmount"),
            "without_tax": _text(summation, "ram:TaxBasisTotalAmount"),
            "tax": tax_total,
            "with_tax": _text(summation, "ram:GrandTotalAmount"),
            "prepaid": _text(summation, "ram:TotalPrepaidAmount"),
            "rounding": _text(summation, "ram:RoundingAmount"),
            "payable": _text(summation, "ram:DuePayableAmount"),
        },
    }
