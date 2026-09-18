"""Reading a step's work, and the references inside it."""

from __future__ import annotations

import pytest

from taktus.components.run.domain.model import (
    CheckRule,
    ConnectorRule,
    ConstantRule,
    LlmWork,
    TemplateRule,
    UnsupportedWork,
    VerifyArtifactRule,
    WaitWork,
    WorkerWork,
    artifact_references,
    parse_work,
    references,
    resolve,
    resolve_inputs,
    select,
)
from taktus.shared.v1 import ExactnessClass, Fallback, Method, Step


def step(method: Method, **extra: object) -> Step:
    exactness = None if method in (Method.WAIT, Method.HUMAN) else ExactnessClass.TOLERANT
    fallback = (
        Fallback(when="x", to=Method.HUMAN) if method in (Method.LLM, Method.WORKER) else None
    )
    model = "m@1" if method in (Method.ML, Method.NEURAL) else None
    return Step(
        id="s",
        method=method,
        reason="r",
        rejected=(),
        exactness=exactness,
        fallback=fallback,
        model=model,
        **extra,
    )


def test_rule_work() -> None:
    assert isinstance(
        parse_work(step(Method.RULE), {"rule": "constant", "value": [1]}), ConstantRule
    )
    verify = parse_work(
        step(Method.RULE), {"rule": "verify_artifact", "step": "a", "artifact": "x"}
    )
    assert isinstance(verify, VerifyArtifactRule) and verify.pattern is None
    check = parse_work(
        step(Method.RULE),
        {"rule": "check", "conditions": [{"value": {"$from": "a"}, "equals": "open"}]},
    )
    assert isinstance(check, CheckRule)
    template = parse_work(
        step(Method.RULE), {"rule": "template", "text": "Closes #${n}", "values": {"n": 1}}
    )
    assert isinstance(template, TemplateRule)
    call = parse_work(
        step(Method.RULE),
        {
            "rule": "connector",
            "operation": "repository.issues.read",
            "input": {"number": {"$input": "issue"}},
            "credentials": [{"name": "REPOSITORY_TOKEN", "injected_as": "env"}],
        },
        {"issue": 42},
    )
    assert isinstance(call, ConnectorRule)
    assert call.capability == "repository.issues"
    assert call.input == {"number": 42}


def test_wait_work_defaults_to_no_wait() -> None:
    assert parse_work(step(Method.WAIT), None) == WaitWork(seconds=0)
    assert parse_work(step(Method.WAIT), {"seconds": 2.5}).seconds == 2.5  # type: ignore[union-attr]
    until = parse_work(
        step(Method.WAIT),
        {
            "until": {
                "operation": "repository.pipelines.status",
                "input": {"ref": "main"},
                "select": "state",
                "expect": ["success", "failure"],
            }
        },
    )
    assert isinstance(until, WaitWork) and until.until is not None
    assert until.until.capability == "repository.pipelines"
    assert until.until.poll_seconds == 30


def test_worker_work() -> None:
    work = parse_work(
        step(Method.WORKER, requires=("shell.script",)),
        {"task": {"goal": "g", "acceptance": ["a"]}},
    )
    assert isinstance(work, WorkerWork)
    assert work.max_steps == 100 and work.workspace.kind == "none"
    assert work.credentials == ()


def test_inputs_resolve_in_typed_places_too() -> None:
    work = parse_work(
        step(Method.WORKER, requires=("code.edit",)),
        {
            "task": {"goal": "g", "acceptance": ["a"], "inputs": {"n": {"$input": "issue"}}},
            "allowed_hosts": [{"$input": "host"}],
            "workspace": {"kind": "git", "location": {"$input": "url"}},
        },
        {"issue": 7, "host": "repo.example", "url": "https://repo.example/a/b.git"},
    )
    assert isinstance(work, WorkerWork)
    assert work.allowed_hosts == ("repo.example",)
    assert work.workspace.location == "https://repo.example/a/b.git"
    assert work.task.inputs == {"n": 7}


def test_llm_work() -> None:
    work = parse_work(
        step(Method.LLM),
        {"purpose": "reasoning", "prompt": "Write ${what}", "values": {"what": "criteria"}},
    )
    assert isinstance(work, LlmWork)
    assert work.max_output_tokens == 2048 and work.pattern is None


@pytest.mark.parametrize(
    ("method", "work", "fragment"),
    [
        (Method.RULE, None, "names its rule"),
        (Method.RULE, {"rule": "unknown"}, "does not match any of the expected tags"),
        (Method.RULE, {"rule": "constant"}, "work.constant.value"),
        (
            Method.RULE,
            {"rule": "connector", "operation": "issues.read"},
            "work.connector.operation",
        ),
        (Method.WAIT, {"seconds": -1}, "work.seconds"),
        (Method.WORKER, None, "carries its task"),
        (Method.WORKER, {"task": {"goal": "g"}}, "work.task.acceptance"),
        (Method.LLM, None, "carries its prompt"),
        (Method.LLM, {"prompt": "x"}, "work.purpose"),
        (Method.ML, {}, "no executor for method ml"),
        (Method.NEURAL, {}, "no executor for method neural"),
        (Method.STATISTICS, {}, "no executor for method statistics"),
        (Method.HUMAN, {}, "no executor for method human"),
        (Method.RULE, {"rule": "constant", "value": {"$input": "nope"}}, "no input 'nope'"),
    ],
)
def test_unsupported_or_malformed_work(
    method: Method, work: dict[str, object] | None, fragment: str
) -> None:
    requires = ("shell.script",) if method is Method.WORKER else None
    with pytest.raises(UnsupportedWork, match=fragment):
        parse_work(step(method, requires=requires), work)


def test_a_worker_step_names_its_capabilities() -> None:
    with pytest.raises(UnsupportedWork, match="capabilities it requires"):
        parse_work(step(Method.WORKER), {"task": {"goal": "g", "acceptance": ["a"]}})


def test_references_are_found_at_any_depth() -> None:
    value = {
        "a": {"$from": "one"},
        "b": [1, {"c": {"$from": "two", "$select": "x.0"}}],
        "d": {"$from": 3},
        "e": {"$from": "three", "$artifact": "patch"},
        "f": {"$input": "issue"},
    }
    assert references(value) == {"one", "two", "three"}
    assert artifact_references(value) == {("three", "patch")}


def test_resolve_replaces_references() -> None:
    value = {
        "commands": {"$from": "prep"},
        "n": [{"$from": "count"}],
        "keep": {"$from": 1, "other": 2},
        "title": {"$from": "issue", "$select": "output.title"},
        "first": {"$from": "issue", "$select": "output.tags.0"},
        "patch": {"$from": "work", "$artifact": "change-1"},
    }
    results = {
        "prep": ["ls"],
        "count": 2,
        "issue": {"output": {"title": "t", "tags": ["a", "b"]}},
    }
    resolved = resolve(value, results, {"work/change-1": "diff --git"})
    assert resolved == {
        "commands": ["ls"],
        "n": [2],
        "keep": {"$from": 1, "other": 2},
        "title": "t",
        "first": "a",
        "patch": "diff --git",
    }
    assert resolve_inputs({"x": {"$input": "a", "$select": "b"}}, {"a": {"b": 5}}) == {"x": 5}


def test_select_names_what_is_missing() -> None:
    assert select({"a": [10, 20]}, "a.1") == 20
    assert select("whole", None) == "whole"
    with pytest.raises(KeyError):
        select({"a": [10]}, "a.5")
    with pytest.raises(KeyError):
        select({"a": 1}, "b")
