"""A deprecation names its removal where the gate can read it (ADR-0220 §3).

`make gate-contracts` fails a deprecated schema, property or operation under `contracts/` that
names no product major as its removal, and an operation without the date it was deprecated. The
compatibility lane counts a deprecation as compatible.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import contract_compat  # noqa: E402 — a script under tools/, found through the line above
import validate_contracts  # noqa: E402

SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://taktus.eu/contracts/shared/v1/Step.json",
    "type": "object",
    "properties": {"id": {"type": "string"}, "old": {"type": "string"}},
}


def with_old(**marks: Any) -> dict[str, Any]:
    schema = json.loads(json.dumps(SCHEMA))
    schema["properties"]["old"].update(marks)
    return schema


def test_a_deprecated_property_without_its_removal_fails_and_with_it_passes() -> None:
    assert validate_contracts.deprecations(with_old(deprecated=True)) == [
        ("/properties/old", "deprecated without `x-taktus-removal: N.0.0`")
    ]
    assert validate_contracts.deprecations(
        with_old(deprecated=True, **{"x-taktus-removal": "2.1.0"})
    )
    assert (
        validate_contracts.deprecations(with_old(deprecated=True, **{"x-taktus-removal": "2.0.0"}))
        == []
    )
    assert validate_contracts.deprecations(SCHEMA) == []


def test_a_deprecated_operation_names_its_date_as_well() -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/old": {"get": {"deprecated": True, "x-taktus-removal": "2.0.0"}},
            "/kept": {
                "post": {
                    "deprecated": True,
                    "x-taktus-removal": "2.0.0",
                    "x-taktus-deprecated": "2026-11-07",
                }
            },
        },
    }
    assert validate_contracts.deprecations(document) == [
        ("/paths//old/get", "a deprecated operation without `x-taktus-deprecated`")
    ]


def test_the_repository_s_contracts_carry_only_well_formed_deprecations() -> None:
    report = validate_contracts.Report()
    validate_contracts.check_deprecations(report)
    assert report.failures == []


def test_a_deprecation_is_a_compatible_change() -> None:
    old = with_old()
    new = with_old(deprecated=True, **{"x-taktus-removal": "2.0.0"})
    changes = list(contract_compat.compare(old, new))
    assert changes and all(kind == contract_compat.COMPATIBLE for _, kind, _ in changes)
