"""Which state a ledger entry leads to is published once, beside the state machine (ADR-0055 §4).

The table is held against the engine's own source: every kind of a run or a step the engine
records is either in the table or named here as one that changes no state. A kind added to the
engine without a decision about it fails here, so that it cannot silently miss every stream.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from taktus.components.decision.domain.model import RECORDED_KINDS as DECISION_KINDS
from taktus.components.decision.domain.model import status_after
from taktus.components.run.domain.model import (
    RECORDED_KINDS,
    STEP_TRANSITIONS,
    Led,
    RunState,
    StepState,
    led_to,
)
from taktus.shared.v1 import DecisionStatus

ENGINE = (
    Path(__file__).resolve().parents[3]
    / "src/taktus/components/run/application/service/execute_run.py"
)
NO_STATE = frozenset(
    {
        "budget.set",  # the budget a person set
        "run.triggered",  # which trigger started the run
        "step.assigned",  # the assignment handed to the worker; the step was running already
        "step.reserved",  # what admission reserved; the step was admitted already
    }
)
"""Kinds of the engine that change no state: they are never sent as a change."""


NOT_LEDGER = frozenset(
    {"run.id", "run.state", "run.cause", "run.submit", "run.execute"}
    | {"step.id", "step.method", "step.state"}
)
"""Names in the engine's source that are a span or its attributes, or a job's kind: no entry."""


def recorded_by_the_engine() -> set[str]:
    source = ENGINE.read_text(encoding="utf-8")
    literal = set(re.findall(r'"((?:run|step)\.[a-z_]+)"', source)) - NOT_LEDGER
    # `_end` records `run.<state>` for every state a run ends a pass in.
    ended = {
        f"run.{state}"
        for state in (
            RunState.HALTED,
            RunState.ESCALATED,
            RunState.FINISHED,
            RunState.WAITING_HUMAN,
        )
    }
    return literal | ended


def test_every_kind_the_engine_records_is_decided() -> None:
    undecided = recorded_by_the_engine() - RECORDED_KINDS - NO_STATE
    assert not undecided, f"decide whether these change a state: {sorted(undecided)}"
    assert NO_STATE.isdisjoint(RECORDED_KINDS)


@pytest.mark.parametrize(
    ("kind", "outcome", "led"),
    [
        # What UC-6.10 names: a step started, completed, failed or halted, a decision awaited.
        ("step.started", None, Led(step=StepState.RUNNING)),
        ("step.finished", "succeeded", Led(step=StepState.SUCCEEDED)),
        ("step.finished", "rehearsed", Led(step=StepState.SUCCEEDED)),
        ("step.finished", "failed", Led(step=StepState.FAILED)),
        ("step.finished", "at_capacity", Led(step=StepState.FAILED)),
        ("step.finished", "stopped", Led(step=StepState.STOPPED)),
        ("step.failed", "not_raised", Led(step=StepState.FAILED)),
        ("run.halted", "limit", Led(run=RunState.HALTED)),
        ("step.anchored", "legal", Led(step=StepState.WAITING_HUMAN)),
        ("step.awaiting", "confirmation", Led(step=StepState.WAITING_HUMAN)),
        ("run.waiting_human", "person", Led(run=RunState.WAITING_HUMAN)),
        ("step.decided", "proceed", Led(step=StepState.PLANNED)),
        ("step.decided", "decline", Led(step=StepState.REJECTED)),
        ("run.recovered", None, Led(run=RunState.RUNNING, step=StepState.STOPPED)),
        ("budget.set", None, None),
    ],
)
def test_a_kind_and_its_outcome_lead_to_one_state(
    kind: str, outcome: str | None, led: Led | None
) -> None:
    assert led_to(kind, outcome) == led


def test_every_step_state_a_kind_leads_to_is_one_the_state_machine_reaches() -> None:
    reachable = {after for _, after in STEP_TRANSITIONS}
    for kind in RECORDED_KINDS:
        for outcome in (None, "succeeded", "stopped", "failed", "proceed", "decline"):
            led = led_to(kind, outcome)
            assert led is not None
            assert led.step is None or led.step in reachable


@pytest.mark.parametrize(
    ("kind", "outcome", "status"),
    [
        ("decision.raised", "legal", DecisionStatus.OPEN),
        ("decision.answered", "interpreted", DecisionStatus.INTERPRETED),
        ("decision.answered", "unread", DecisionStatus.ANSWERED),
        ("decision.reread", "rejected", DecisionStatus.OPEN),
        ("decision.confirmed", "option_a", DecisionStatus.CONFIRMED),
        ("decision.applied", "option_a", DecisionStatus.APPLIED),
        ("step.started", None, None),
    ],
)
def test_a_decision_request_s_kind_leads_to_one_status(
    kind: str, outcome: str | None, status: DecisionStatus | None
) -> None:
    assert status_after(kind, outcome) == status
    assert (kind in DECISION_KINDS) == (status is not None)
