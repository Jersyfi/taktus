"""The Python binding of the changes contract matches `Changes.json` (`contracts/changes/v1`).

The kinds sent and the states are read from the schema and compared with what the run and the
decision component publish; every example passes through the reporting component's values and
back, and every must-fail one is refused (ADR-0055 §4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from taktus.components.decision.domain.model import RECORDED_KINDS as DECISION_KINDS
from taktus.components.reporting.domain.model import Change, Snapshot
from taktus.components.run.domain.model import RECORDED_KINDS as RUN_KINDS
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.live import state_of
from taktus.shared.v1 import DecisionStatus

from .test_shared_kernel_binding import example_cases, load

ROOT = Path(__file__).resolve().parents[2]
CHANGES = ROOT / "contracts" / "changes" / "v1"
SCHEMA: dict[str, Any] = json.loads((CHANGES / "Changes.json").read_text(encoding="utf-8"))
DEFS = SCHEMA["$defs"]
BINDINGS: dict[str, type[Snapshot] | type[Change]] = {"snapshot": Snapshot, "change": Change}


def test_the_kinds_sent_are_the_ones_the_components_publish() -> None:
    assert set(DEFS["Kind"]["enum"]) == RUN_KINDS | DECISION_KINDS
    for kind in DEFS["Kind"]["enum"]:
        assert state_of(kind, None) is not None, f"{kind} leads to no state"


def test_the_states_are_the_state_machines() -> None:
    assert DEFS["RunState"]["enum"] == [s.value for s in RunState]
    assert DEFS["StepState"]["enum"] == [s.value for s in StepState]
    shared = json.loads(
        (ROOT / "contracts" / "shared" / "v1" / "DecisionRequest.json").read_text("utf-8")
    )
    assert shared["properties"]["status"]["enum"] == [s.value for s in DecisionStatus]


@pytest.mark.parametrize(
    ("path", "valid"),
    example_cases(CHANGES / "examples"),
    ids=lambda p: p.relative_to(CHANGES / "examples").as_posix() if isinstance(p, Path) else "",
)
def test_examples_through_the_binding(path: Path, valid: bool) -> None:
    binding = BINDINGS[path.parent.parent.name]
    data = load(path)
    if valid:
        assert binding.model_validate(data).document() == data
        return
    with pytest.raises(ValidationError):
        binding.model_validate(data)
