"""A process declares its deadlines beside its steps (UC-4.17 §2, ADR-0133 §1). A deadline
without an action does not register, and every action names a role or a process."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess

from .test_bundle_parsing import bundle

DEADLINE: dict[str, Any] = {
    "from": "run",
    "limit": "1d",
    "lead": "4h",
    "counts": "working",
    "until": {"step": "a"},
    "at_lead": {"remind": "support"},
    "at_limit": {"escalate": "support-lead"},
}


def with_deadline(**fields: Any) -> dict[str, Any]:
    given = {**DEADLINE, **fields}
    return bundle(
        deadlines={"first_answer": {k: v for k, v in given.items() if v is not None}},
        inputs={"expires": {"description": "when", "example": "2026-12-01", "required": False}},
    )


def findings(document: dict[str, Any]) -> str:
    with pytest.raises(InvalidProcess) as raised:
        parse_bundle(document)
    return "; ".join(raised.value.findings)


def test_a_deadline_is_declared_with_its_start_limit_lead_count_and_actions() -> None:
    (declared,) = parse_bundle(with_deadline()).deadlines.values()
    assert declared.start == "run" and declared.until == "a"
    assert declared.limit == timedelta(days=1) and declared.lead == timedelta(hours=4)
    assert declared.working
    assert declared.at_lead is not None and declared.at_lead.role == "support"
    assert declared.at_limit.kind == "escalate" and declared.at_limit.role == "support-lead"
    after = parse_bundle(with_deadline(**{"from": {"after": "a"}, "until": {"step": "b"}}))
    assert after.deadlines["first_answer"].after == "a"
    dated = parse_bundle(with_deadline(**{"from": {"date": "expires"}, "limit": "0d"}))
    assert dated.deadlines["first_answer"].date_input == "expires"
    started = parse_bundle(
        with_deadline(at_limit={"start": {"process": "renew", "inputs": {"n": 1}}})
    )
    assert started.deadlines["first_answer"].at_limit.process == "renew"


def test_a_deadline_without_an_action_does_not_register() -> None:
    assert "without an action does not register" in findings(with_deadline(at_limit=None))
    assert "without `at_lead`" in findings(with_deadline(at_lead=None))
    assert "no `lead`" in findings(with_deadline(lead=None))


def test_a_deadline_names_steps_and_inputs_the_process_has() -> None:
    assert "'nowhere', which is not a step" in findings(with_deadline(until={"step": "nowhere"}))
    assert "starts after 'x'" in findings(with_deadline(**{"from": {"after": "x"}}))
    assert "the input 'due'" in findings(with_deadline(**{"from": {"date": "due"}}))
    assert ".from` is `run`" in findings(with_deadline(**{"from": "yesterday"}))
    assert "`calendar` or `working`" in findings(with_deadline(counts="office"))
    assert "names no `limit`" in findings(with_deadline(limit=None))
    assert "which a deadline has not" in findings(with_deadline(owner="idn_ada"))


def test_an_action_is_a_reminder_an_escalation_or_a_start_never_a_person() -> None:
    assert "exactly one of" in findings(with_deadline(at_limit={"notify": "ada"}))
    assert "exactly one of" in findings(
        with_deadline(at_limit={"remind": "support", "escalate": "lead"})
    )
    assert "names a role, never a person" in findings(
        with_deadline(at_limit={"escalate": {"person": "idn_ada"}})
    )
    assert "at_limit" in findings(with_deadline(at_limit={"escalate": "Ada Lovelace"}))
