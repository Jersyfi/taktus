"""Partner interfaces under a data contract (UC-15.3, ADR-0273): registration's rule.

What is proven: a version that reads a partner's data without a data contract does not
register, and the finding names the step; the invoice bundles of the blueprint register with
theirs; the contract is part of the version; an import step whose check does not hold every
required field, an export step that sends a document nobody checked, a contract with neither an
open standard nor the reason for a proprietary format, and a frequency nobody expects are each
refused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess

ROOT = Path(__file__).resolve().parents[3]
INCOMING = ROOT / "blueprints/invoice-to-payment/processes/B-10.03-incoming-invoice.yaml"
UNREFERENCED = ROOT / "blueprints/invoice-to-payment/processes/B-10.03-unreferenced-invoice.yaml"


def incoming() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(INCOMING.read_text(encoding="utf-8"))
    return document


def refused(document: dict[str, Any]) -> str:
    with pytest.raises(InvalidProcess) as raised:
        parse_bundle(document)
    return "; ".join(raised.value.findings)


def step(document: dict[str, Any], step_id: str) -> dict[str, Any]:
    (found,) = [s for s in document["steps"] if s["id"] == step_id]
    return found


def test_the_invoice_bundles_register_with_their_data_contract() -> None:
    for path in (INCOMING, UNREFERENCED):
        version = parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8")))
        (contract,) = version.contracts.values()
        assert contract.direction == "import" and contract.standard is not None
        assert {"number", "issue_date", "currency", "seller", "totals"} <= set(contract.required)
        assert contract.responsible.ours == "owner"


def test_a_version_that_reads_a_partners_data_without_a_contract_does_not_register() -> None:
    document = incoming()
    del document["contracts"]
    said = refused(document)
    assert "the step 'read-invoice' exchanges data with a partner through " in said
    assert "documents.invoices.read" in said and "no data contract" in said


def test_the_contract_is_part_of_the_version() -> None:
    first = parse_bundle(incoming())
    document = incoming()
    document["contracts"]["supplier-invoices"]["frequency"] = "7d"
    second = parse_bundle(document)
    assert first.contracts != second.contracts
    assert first.model_dump(exclude={"contracts"}) == second.model_dump(exclude={"contracts"})


def test_an_import_whose_check_does_not_hold_every_required_field_is_refused() -> None:
    document = incoming()
    step(document, "read-invoice")["checks"] = [
        {"kind": "source_shape", "columns": ["digest", "number"]}
    ]
    said = refused(document)
    assert "imports under the data contract 'supplier-invoices'" in said
    assert "currency, issue_date, number, order_reference, seller, totals" in said


def test_an_export_of_a_document_nobody_checked_is_refused() -> None:
    """`read-order` stands in for a sending step: it depends on `read-invoice`, whose check
    holds the order reference and no `reference`."""
    document = incoming()
    contract = document["contracts"]["supplier-invoices"]
    contract["direction"] = "export"
    contract["steps"] = ["read-order"]
    contract["fields"] = [{"name": "reference", "required": True}]
    said = refused(document)
    assert "the step 'read-order' exports under the data contract 'supplier-invoices'" in said
    contract["fields"] = [{"name": "order_reference", "required": True}]
    assert "exports under" not in refused_or_none(document)


def refused_or_none(document: dict[str, Any]) -> str:
    try:
        parse_bundle(document)
    except InvalidProcess as error:
        return "; ".join(error.findings)
    return ""


def test_a_contract_names_an_open_standard_or_why_a_proprietary_format() -> None:
    document = incoming()
    del document["contracts"]["supplier-invoices"]["standard"]
    assert "proprietary" in refused(document)
    document["contracts"]["supplier-invoices"]["proprietary"] = "the partner offers no other"
    parse_bundle(document)


def test_a_frequency_nobody_expects_is_refused() -> None:
    document = incoming()
    document["triggers"] = []
    document.pop("expect", None)
    assert "expects no run" in refused(document)
