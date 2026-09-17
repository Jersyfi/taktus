"""The rules of the connector contract on known-good and known-bad documents.

The schema fixtures under contracts/connector/v1/examples say what a document may look like;
the rules in src/taktus/conformance/connector/rules.py say what it must say given what was
declared and asked. Both callers of the rules — the live suite and this table — must agree, so
the table pins them: every valid example breaks no rule, and one document per rule breaks exactly
the check the rule belongs to.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taktus.conformance.catalogue import catalogue_of
from taktus.conformance.connector import rules
from taktus.conformance.connector.rules import CATALOGUE, CHECKS

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "connector" / "v1" / "examples"

type Json = dict[str, Any]


def load(rel: str) -> Json:
    with (EXAMPLES / rel).open(encoding="utf-8") as handle:
        result: Json = json.load(handle)
        return result


CAPABILITIES = load("capabilities/valid/repository-connector.json")
TOOLS = [op["name"] for op in CAPABILITIES["operations"]] + ["intake"]
WRITE = load("result/valid/pull-request-opened.json")
REPLAYED = load("result/valid/pull-request-replayed.json")
READ = load("result/valid/issue-read.json")


def checks(violations: list[rules.Violation]) -> set[str]:
    return {v.check for v in violations}


def test_the_catalogue_is_complete_and_findable() -> None:
    assert list(CATALOGUE) == [f"C-{n:02d}" for n in range(1, 11)]
    assert CATALOGUE.runnable == [f"C-{n:02d}" for n in range(1, 10)]
    for check in CHECKS:
        assert catalogue_of(check) is CATALOGUE
        assert CATALOGUE.where(check).startswith("contracts/connector/v1/README.md §")


def test_a_conforming_declaration_breaks_no_rule() -> None:
    assert rules.declaration_violations(CAPABILITIES, TOOLS) == []


@pytest.mark.parametrize(
    ("tools", "message"),
    [
        (TOOLS[:-1], "declared operation 'intake' is not served"),
        (TOOLS[1:], "declared operation 'repository.issues.read' is not served"),
        ([*TOOLS, "repository.labels.add"], "served tool 'repository.labels.add' is not declared"),
    ],
)
def test_the_tool_list_must_agree_with_the_declaration(tools: list[str], message: str) -> None:
    violations = rules.declaration_violations(CAPABILITIES, tools)
    assert checks(violations) == {"C-01"}
    assert any(message in v.message for v in violations)


def test_an_operation_must_extend_a_declared_capability() -> None:
    stray = {
        **CAPABILITIES,
        "operations": [
            {**CAPABILITIES["operations"][0], "name": "repository.labels.read"},
            {**CAPABILITIES["operations"][0], "capability": "repository.labels"},
        ],
    }
    violations = rules.declaration_violations(
        stray, ["repository.labels.read", "repository.issues.read", "intake"]
    )
    assert checks(violations) == {"C-01"}
    assert len(violations) == 3


def test_a_conforming_result_breaks_no_rule() -> None:
    assert rules.result_violations(CAPABILITIES, "repository.pullrequests.open", WRITE) == []
    assert rules.result_violations(CAPABILITIES, "repository.issues.read", READ) == []


def test_the_effect_must_be_the_declared_one() -> None:
    lying = {**WRITE, "effect": {"kind": "read"}}
    assert checks(rules.result_violations(CAPABILITIES, "repository.pullrequests.open", lying)) == {
        "C-02"
    }


def test_consumption_must_be_reported_in_a_declared_kind() -> None:
    silent = {**READ, "consumption": {}}
    wrong_kind = {**READ, "consumption": {"tokens_in": 3}}
    assert checks(rules.result_violations(CAPABILITIES, "repository.issues.read", silent)) == {
        "C-09"
    }
    assert checks(rules.result_violations(CAPABILITIES, "repository.issues.read", wrong_kind)) == {
        "C-09"
    }


def test_a_recognised_repeat_breaks_no_rule() -> None:
    fresh = {
        **WRITE,
        "effect": {**WRITE["effect"], "records": [{"kind": "vcs.pullrequest", "id": "58"}]},
    }
    assert rules.repeat_violations("repository.pullrequests.open", WRITE, REPLAYED, fresh) == []


@pytest.mark.parametrize(
    ("repeat", "fresh", "message"),
    [
        (WRITE, None, "the repeat was not recognised"),
        (
            {
                **REPLAYED,
                "effect": {
                    **REPLAYED["effect"],
                    "records": [{"kind": "vcs.pullrequest", "id": "99"}],
                },
            },
            None,
            "the connector acted twice",
        ),
        (REPLAYED, WRITE, "the connector recognises the input, not the key"),
        (REPLAYED, REPLAYED, "a new key must act again"),
    ],
)
def test_a_repeat_must_be_recognised_by_key(repeat: Json, fresh: Json | None, message: str) -> None:
    violations = rules.repeat_violations("repository.pullrequests.open", WRITE, repeat, fresh)
    assert checks(violations) == {"C-05"}
    assert any(message in v.message for v in violations)


def test_an_error_must_carry_the_expected_cause_and_a_consistent_retryable() -> None:
    forbidden = load("error/valid/forbidden.json")
    assert rules.error_violations(forbidden, expected_cause="forbidden") == []
    assert checks(rules.error_violations(forbidden, expected_cause="not_found")) == {"C-06"}
    assert checks(rules.error_violations({**forbidden, "retryable": True})) == {"C-06"}
    assert checks(rules.error_violations("bare text")) == {"C-06"}


def test_intake_results_are_judged_against_what_was_expected() -> None:
    accepted = load("intake-result/valid/accepted.json")
    refused = load("intake-result/valid/refused.json")
    assert rules.intake_violations(CAPABILITIES, accepted, expect="accepted") == []
    assert rules.intake_violations(CAPABILITIES, refused, expect="refused", reason="unsigned") == []
    assert checks(rules.intake_violations(CAPABILITIES, refused, expect="accepted")) == {"C-07"}
    assert checks(
        rules.intake_violations(CAPABILITIES, accepted, expect="refused", reason="unsigned")
    ) == {"C-08"}
    assert checks(
        rules.intake_violations(CAPABILITIES, refused, expect="refused", reason="bad_signature")
    ) == {"C-08"}
    undeclared = {"accepted": {**accepted["accepted"], "event": "star.created"}}
    assert checks(rules.intake_violations(CAPABILITIES, undeclared, expect="accepted")) == {"C-07"}
