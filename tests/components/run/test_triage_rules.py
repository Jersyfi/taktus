"""The rules of a contribution's triage (UC-1.9, ADR-0088): `spam` by fixed patterns, and
`classification`, which holds a judgement to the classes and versions that may be answered;
and the two keys of a step's work that are not what it does, `when` and `ask`."""

from __future__ import annotations

from typing import Any

import pytest

from taktus.components.run.domain.model import (
    ClassificationRule,
    RuleFailed,
    SpamRule,
    UnsupportedWork,
    control_of,
    parse_work,
)
from taktus.components.run.domain.service import rules
from taktus.shared.v1 import ExactnessClass, Method, Step

VERSIONS = ["0.3.0", "0.4.0"]
SCREENED = {"spam": False, "matched": []}


def spam(*patterns: str) -> SpamRule:
    return SpamRule(rule="spam", text=None, patterns=patterns)


def classify(answer: Any, screened: Any = SCREENED) -> dict[str, Any]:
    rule = ClassificationRule(rule="classification", answer=None, screened=None, versions=None)
    return rules.classification(rule, answer, screened, VERSIONS)


def test_spam_is_what_a_pattern_finds_case_blind_and_nothing_else() -> None:
    rule = spam(r"\bcasino\b", r"(https?://\S+[\s\S]*){3,}")
    assert rules.spam(rule, ["Best CASINO", "bonus"]) == {"spam": True, "matched": [r"\bcasino\b"]}
    assert rules.spam(rule, "a report on the export")["spam"] is False
    links = "see http://a http://b http://c"
    assert rules.spam(rule, links)["matched"] == [r"(https?://\S+[\s\S]*){3,}"]
    with pytest.raises(RuleFailed):
        rules.spam(rule, {"title": 1})


def test_a_pattern_that_does_not_compile_is_refused_before_the_run() -> None:
    with pytest.raises(ValueError, match="does not compile"):
        SpamRule(rule="spam", text="x", patterns=("(",))


def test_the_screen_wins_over_any_answer() -> None:
    screened = {"spam": True, "matched": ["casino"]}
    assert classify({"skipped": True}, screened)["class"] == "spam"


def test_a_defect_or_a_feature_names_a_planned_version_and_a_summary() -> None:
    answer = {"text": "Class: Feature\nversion: `0.4.0`\nsummary: CSV export.", "model": "m"}
    assert classify(answer) == {"class": "feature", "version": "0.4.0", "summary": "CSV export."}
    assert classify("class: spam")["class"] == "spam"
    for wrong in (
        "class: question\nversion: 0.4.0\nsummary: s",
        "class: defect\nversion: 9.9.9\nsummary: s",
        "class: defect\nversion: 0.4.0",
        "class: defect\nclass: feature\nversion: 0.4.0\nsummary: s",
        "nothing at all",
    ):
        with pytest.raises(RuleFailed):
            classify(wrong)


def step(method: Method = Method.RULE) -> Step:
    return Step(id="s", method=method, reason="r", rejected=(), exactness=ExactnessClass.SOURCED)


def test_when_and_ask_are_read_beside_the_work_and_never_as_part_of_it() -> None:
    work = {
        "rule": "constant",
        "value": 1,
        "when": [{"value": {"$from": "a"}, "equals": "x"}],
        "ask": {"question": "Q ${n}?", "values": {"n": {"$input": "n"}}, "on_decline": "continue"},
    }
    assert parse_work(step(), work, {"n": 3}).model_dump() == {"rule": "constant", "value": 1}
    control = control_of(step(), work, {"n": 3})
    assert control.ask is not None and control.ask.role == "owner"
    assert control.ask.values == {"n": 3} and control.ask.on_decline == "continue"
    assert len(control.when) == 1
    assert control_of(step(), {"rule": "constant", "value": 1}).ask is None


def test_an_ask_without_a_question_is_refused() -> None:
    with pytest.raises(UnsupportedWork, match="ask"):
        control_of(step(), {"rule": "constant", "value": 1, "ask": {"role": "owner"}})
