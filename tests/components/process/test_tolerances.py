"""A variable step declares its tolerance before its process has any case, and the declaration
is held once a scorer scores the step (UC-8.4 §2, ADR-0300 §1)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fakes.takeover import instructions

from taktus.components.process.application.service.register_version import read_bundle
from taktus.components.process.domain.model import InvalidProcess
from taktus.components.process.domain.service.bundle import bundle_of

BUNDLE: dict[str, Any] = {
    "id": "replies",
    "version": "1",
    "name": "Draft a reply",
    "autonomy": {"level": 2, "reason": "a person sends it", "toward_next": "a quality record"},
    "author": "the tests",
    "reason": "a reply is drafted, and a person sends it",
    "limits": {"quota": {"units": 5}},
    "inputs": {"message": {"description": "the message", "example": "It broke."}},
    "steps": [
        {
            "id": "draft",
            "method": "llm",
            "reason": "words for a person",
            "rejected": [{"method": "rule", "why": "no rule writes a reply"}],
            "exactness": "free",
            "fallback": {"when": "the model fails", "to": "human"},
            "work": {"purpose": "drafting", "prompt": "Answer: {message}", "values": {}},
        },
        {
            "id": "file",
            "method": "rule",
            "reason": "a constant",
            "rejected": [{"method": "llm", "why": "nothing to judge"}],
            "exactness": "exact",
            "checks": [{"kind": "bounds", "pattern": "^\\\\{"}],
            "fallback": {"when": "never", "to": "human"},
            "depends_on": ["draft"],
            "work": {"rule": "constant", "value": {"filed": True}},
        },
    ],
}


def bundle(**more: Any) -> dict[str, Any]:
    given = {**copy.deepcopy(BUNDLE), **more}
    return {**given, "takeover": instructions(given)}


def test_a_variable_step_without_a_tolerance_is_refused_and_declares_it_beside_the_steps() -> None:
    undeclared, refused = read_bundle(bundle())
    assert undeclared.undeclared_tolerances() == ("draft",), "only the variable step"
    (finding,) = refused
    assert "'draft' varies and declares no tolerance" in finding, "registration refuses it"
    version, refused = read_bundle(bundle(tolerances={"draft": 0.3}))
    assert refused == []
    assert version.undeclared_tolerances() == ()
    exported = bundle_of(version, as_version="2", author="the tests", reason="r")
    assert exported["tolerances"] == {"draft": 0.3}, "the export carries it"


def test_a_tolerance_beside_the_steps_is_held_within_its_class_and_to_a_variable_step() -> None:
    sourced = copy.deepcopy(BUNDLE)
    sourced["steps"][0]["exactness"] = "sourced"
    sourced["steps"][0]["checks"] = [{"kind": "bounds", "pattern": "^."}]
    with pytest.raises(InvalidProcess, match=r"from 0 to 0\.05"):
        read_bundle(bundle(steps=sourced["steps"], tolerances={"draft": 0.3}))
    with pytest.raises(InvalidProcess, match="no step of this process that produces"):
        read_bundle(bundle(tolerances={"draft": 0.3, "nothing": 0.0}))


def test_the_declaration_is_held_once_a_scorer_scores_the_step() -> None:
    evaluation = {
        "cases": [{"id": "late", "inputs": {"message": "Late."}, "targets": {"draft": "Sorry."}}],
        "scorers": [
            {
                "step": "draft",
                "method": "rule",
                "reason": "words a rule can count",
                "exactness": "exact",
                "rule": {"kind": "overlap"},
            }
        ],
    }
    version, refused = read_bundle(bundle(tolerances={"draft": 0.3}, evaluation=evaluation))
    assert refused == [], "the tolerance declared before the cases counts for the scorer"
    assert version.tolerance_bounds()[0] == {"draft": 0.3}
    twice = {**evaluation, "tolerances": {"draft": 0.2}}
    with pytest.raises(InvalidProcess, match="declare it once"):
        read_bundle(bundle(tolerances={"draft": 0.3}, evaluation=twice))
