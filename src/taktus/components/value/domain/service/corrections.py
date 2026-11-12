"""The measured correction rate of a process version, counted from the ledger (UC-6.9 §3,
ADR-0226).

A result **counts** when its step finished as succeeded outside a rehearsal: the checks the
step declares ran before its value counted (ADR-0152), so a counted result of a checked step is
one whose checks passed. It is **corrected** when a person recorded `step.corrected` for it
afterwards. Each result is corrected once at most, however often a person corrected it.

The figure is folded entry by entry into a projection (ADR-0105): per process version and
step, how many results counted and which were corrected. It is counted per process and step,
never per person: the projection keeps no actor (principle 14).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from taktus.shared.v1 import LedgerEntry

FINISHED = "step.finished"
CORRECTED = "step.corrected"


@dataclass
class Counted:
    """Per `<process>@<version>` and step: how many results counted, and the runs whose result
    of the step a person corrected."""

    counted: dict[str, dict[str, int]] = field(default_factory=dict)
    corrected: dict[str, dict[str, list[str]]] = field(default_factory=dict)


@dataclass(frozen=True)
class Measured:
    """The rate of one process version over the steps that declare a check."""

    process_version: str
    corrected: int
    counted: int

    @property
    def per_hundred(self) -> float | None:
        """None while no result of a checked step has counted."""
        return None if self.counted == 0 else 100 * self.corrected / self.counted


def fold(state: Counted, entry: LedgerEntry) -> Counted:
    refs = entry.refs
    if entry.rehearsal or refs.process_version is None or refs.step_id is None:
        return state
    if entry.kind == FINISHED and entry.outcome == "succeeded":
        steps = state.counted.setdefault(refs.process_version, {})
        steps[refs.step_id] = steps.get(refs.step_id, 0) + 1
    elif entry.kind == CORRECTED and refs.run_id is not None:
        runs = state.corrected.setdefault(refs.process_version, {}).setdefault(refs.step_id, [])
        if refs.run_id not in runs:
            runs.append(refs.run_id)
    return state


def measured(state: Counted, process_version: str, checked: Iterable[str]) -> Measured:
    """The rate of a version over `checked`, the steps that declare at least one check. A
    correction of a result that never counted is not counted either."""
    steps = set(checked)
    counted = state.counted.get(process_version, {})
    corrected = state.corrected.get(process_version, {})
    return Measured(
        process_version=process_version,
        counted=sum(n for s, n in counted.items() if s in steps),
        corrected=sum(
            min(len(runs), counted.get(s, 0)) for s, runs in corrected.items() if s in steps
        ),
    )


class CorrectionsProjection:
    name = "value.corrections.v1"
    kinds: frozenset[str] | None = frozenset({FINISHED, CORRECTED})

    def empty(self) -> Counted:
        return Counted()

    def fold(self, state: Counted, entry: LedgerEntry) -> Counted:
        return fold(state, entry)

    def dump(self, state: Counted) -> dict[str, Any]:
        return {"counted": state.counted, "corrected": state.corrected}

    def load(self, document: Mapping[str, Any]) -> Counted:
        return Counted(
            counted={k: dict(v) for k, v in document["counted"].items()},
            corrected={
                k: {s: list(r) for s, r in v.items()} for k, v in document["corrected"].items()
            },
        )


CORRECTIONS = CorrectionsProjection()
