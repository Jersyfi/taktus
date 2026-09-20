"""The Python binding of the connector contract matches `Connector.json`.

The same three readings `test_shared_kernel_binding.py` applies to the worker contract: the
shape of every object definition the port binds, the enumerations, and the contract's own
examples — every valid example parses and writes back byte-for-byte, every must-fail example is
refused. A definition that exists only for the conformance suite (the scenario) is not bound
by the port and is listed as such.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

import taktus.ports.connector as connector

from .test_shared_kernel_binding import assert_same_shape, example_cases, load

ROOT = Path(__file__).resolve().parents[2]
CONNECTOR = ROOT / "contracts" / "connector" / "v1"
SCHEMA = json.loads((CONNECTOR / "Connector.json").read_text(encoding="utf-8"))

DEFINITIONS: dict[str, Any] = {
    "arguments": connector.Arguments,
    "call-context": connector.CallContext,
    "capabilities": connector.Capabilities,
    "effect-report": connector.EffectReport,
    "error": connector.Error,
    "intake": connector.Intake,
    "intake-arguments": connector.Delivery,
    "intake-declaration": connector.IntakeDeclaration,
    "intake-result": connector.IntakeResult,
    "operation": connector.Operation,
    "refusal": connector.Refusal,
    "result": connector.Result,
}
"""Example directory → the port type. `IntakeArguments` is bound as `Delivery`, the name the
core uses for an event before anything is believed about it."""

NOT_BOUND = {"Scenario", "ScenarioCall", "ScenarioPayload", "IntakeArguments"}
"""The scenario is the suite's input, not a wire object of the core; IntakeArguments is bound
under another name (see DEFINITIONS)."""


@pytest.mark.parametrize(
    ("path", "valid"),
    [c for c in example_cases(CONNECTOR / "examples") if c[0].parent.parent.name != "scenario"],
    ids=lambda p: p.relative_to(CONNECTOR / "examples").as_posix() if isinstance(p, Path) else "",
)
def test_connector_examples_through_the_port_types(path: Path, valid: bool) -> None:
    adapter: TypeAdapter[Any] = TypeAdapter(DEFINITIONS[path.parent.parent.name])
    data = load(path)
    if valid:
        instance = adapter.validate_python(data)
        assert instance.document() == data
    else:
        with pytest.raises(ValidationError):
            adapter.validate_python(data)


@pytest.mark.parametrize(
    "definition",
    sorted(
        name
        for name, body in SCHEMA["$defs"].items()
        if body.get("type") == "object" and "oneOf" not in body and name not in NOT_BOUND
    ),
)
def test_connector_definitions_have_the_same_shape(definition: str) -> None:
    body = SCHEMA["$defs"][definition]
    assert_same_shape(
        body, getattr(connector, definition), SCHEMA["$defs"], CONNECTOR, where=definition
    )


def test_delivery_has_the_shape_of_intake_arguments() -> None:
    body = SCHEMA["$defs"]["IntakeArguments"]
    assert_same_shape(body, connector.Delivery, SCHEMA["$defs"], CONNECTOR, where="Delivery")


def test_every_connector_object_definition_is_bound_or_listed() -> None:
    unbound = sorted(
        name
        for name, body in SCHEMA["$defs"].items()
        if body.get("type") == "object"
        and "oneOf" not in body
        and not hasattr(connector, name)
        and name not in NOT_BOUND
    )
    assert unbound == []


def test_the_enumerations_match() -> None:
    defs = SCHEMA["$defs"]
    assert [m.value for m in connector.Effect] == defs["Effect"]["enum"]
    assert [m.value for m in connector.Idempotency] == defs["Idempotency"]["enum"]
    assert [m.value for m in connector.Cause] == defs["Cause"]["enum"]
    assert [m.value for m in connector.RefusalReason] == defs["RefusalReason"]["enum"]
    assert [m.value for m in connector.SenderKind] == defs["Sender"]["properties"]["kind"]["enum"]
    assert connector.IDEMPOTENCY_KEY_PATTERN == defs["IdempotencyKey"]["pattern"]
    assert connector.OPERATION_PATTERN == defs["OperationName"]["pattern"]
    assert connector.CREDENTIAL_NAME_PATTERN == defs["CredentialName"]["pattern"]


def test_the_idempotency_key_of_an_attempt_is_derived_and_valid() -> None:
    key = connector.idempotency_key("run_0123456789abcdef0123", "open-pr", 1)
    assert key == "taktus:run_0123456789abcdef0123:open-pr:1"
    assert len(connector.idempotency_key("run_1", "a", 1)) >= 16
    TypeAdapter(connector.CallContext).validate_python(
        {
            "tenant": "default",
            "identity": "idn_1",
            "run_id": "run_0123456789abcdef0123",
            "step_id": "open-pr",
            "attempt": 1,
            "idempotency_key": key,
            "credentials": [],
        }
    )
