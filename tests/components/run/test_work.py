"""Reading a step's work, and `$from` references."""

from __future__ import annotations

import pytest

from taktus.components.run.domain.model import (
    ConstantRule,
    UnsupportedWork,
    VerifyArtifactRule,
    WaitWork,
    WorkerWork,
    parse_work,
    references,
    resolve,
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


def test_wait_work_defaults_to_no_wait() -> None:
    assert parse_work(step(Method.WAIT), None) == WaitWork(seconds=0)
    assert parse_work(step(Method.WAIT), {"seconds": 2.5}).seconds == 2.5  # type: ignore[union-attr]


def test_worker_work() -> None:
    work = parse_work(
        step(Method.WORKER, requires=("shell.script",)),
        {"task": {"goal": "g", "acceptance": ["a"]}},
    )
    assert isinstance(work, WorkerWork)
    assert work.max_steps == 100 and work.workspace.kind == "none"


@pytest.mark.parametrize(
    ("method", "work", "fragment"),
    [
        (Method.RULE, None, "names its rule"),
        (Method.RULE, {"rule": "unknown"}, "does not match any of the expected tags"),
        (Method.RULE, {"rule": "constant"}, "work.constant.value"),
        (Method.WAIT, {"seconds": -1}, "work.seconds"),
        (Method.WORKER, None, "carries its task"),
        (Method.WORKER, {"task": {"goal": "g"}}, "work.task.acceptance"),
        (Method.LLM, {"prompt": "x"}, "no executor for method llm"),
        (Method.ML, {}, "no executor for method ml"),
        (Method.NEURAL, {}, "no executor for method neural"),
        (Method.STATISTICS, {}, "no executor for method statistics"),
        (Method.HUMAN, {}, "no executor for method human"),
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
    value = {"a": {"$from": "one"}, "b": [1, {"c": {"$from": "two"}}], "d": {"$from": 3}}
    assert references(value) == {"one", "two"}


def test_resolve_replaces_references() -> None:
    value = {"commands": {"$from": "prep"}, "n": [{"$from": "count"}], "keep": {"$from": 1}}
    resolved = resolve(value, {"prep": ["ls"], "count": 2})
    assert resolved == {"commands": ["ls"], "n": [2], "keep": {"$from": 1}}
