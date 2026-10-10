"""The Python binding of the events contract matches `Event.json` (`contracts/events/v1`).

The catalogue and the conditions are read from the schema and compared with the process
component's; every event example passes through `Event` and back, every must-fail one is refused;
every event-trigger example registers or is refused, with what the schema refuses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from taktus.components.process.domain.model import KINDS, Condition, Event, Kind, Trigger

from .test_shared_kernel_binding import example_cases, load

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ROOT / "contracts" / "events" / "v1"
SCHEMA: dict[str, Any] = json.loads((EVENTS / "Event.json").read_text(encoding="utf-8"))


def required_by_schema() -> dict[str, set[str]]:
    """For each kind, the context fields the schema's `allOf` requires."""
    found: dict[str, set[str]] = {}
    for rule in SCHEMA["allOf"]:
        test = rule["if"]["properties"]["kind"]
        kinds = test["enum"] if "enum" in test else [test["const"]]
        context = rule["then"]["properties"]["context"]
        parts = context.get("allOf", [context])
        fields: set[str] = set()
        for part in parts:
            if "$ref" in part:
                name = part["$ref"].rsplit("/", 1)[-1]
                fields |= set(SCHEMA["$defs"][name]["required"])
            else:
                fields |= set(part["required"])
        for kind in kinds:
            found[kind] = fields
    return found


def test_the_catalogue_is_the_schemas() -> None:
    assert [k.value for k in Kind] == SCHEMA["$defs"]["Kind"]["enum"]
    assert {k.value: set(f.required) for k, f in KINDS.items()} == required_by_schema()


def test_the_conditions_are_the_schemas() -> None:
    assert [c.value for c in Condition] == SCHEMA["$defs"]["Condition"]["enum"]


@pytest.mark.parametrize(
    ("path", "valid"),
    [c for c in example_cases(EVENTS / "examples") if c[0].parent.parent.name == "event"],
    ids=lambda p: p.relative_to(EVENTS / "examples").as_posix() if isinstance(p, Path) else "",
)
def test_event_examples_through_the_binding(path: Path, valid: bool) -> None:
    data = load(path)
    if valid:
        event = Event.model_validate(data)
        assert event.missing() == []
        assert event.document() == data
    else:
        try:
            event = Event.model_validate(data)
        except ValidationError:
            return
        assert event.missing(), f"{path.name} must be refused"


@pytest.mark.parametrize(
    ("path", "valid"),
    [c for c in example_cases(EVENTS / "examples") if c[0].parent.parent.name == "event-trigger"],
    ids=lambda p: p.relative_to(EVENTS / "examples").as_posix() if isinstance(p, Path) else "",
)
def test_event_trigger_examples_through_the_binding(path: Path, valid: bool) -> None:
    data = load(path)
    if valid:
        assert Trigger.model_validate(data).findings() == []
    else:
        try:
            trigger = Trigger.model_validate(data)
        except ValidationError:
            return
        assert trigger.findings(), f"{path.name} must be refused at registration"
