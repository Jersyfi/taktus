"""The graph rules of the process domain, as tables. No mocks: values in, findings out."""

from __future__ import annotations

from datetime import timedelta

import pytest

from taktus.components.process.domain.model import (
    Edge,
    InvalidProcess,
    ProcessVersion,
    Slo,
    Trigger,
)
from taktus.components.process.domain.service import validation
from taktus.shared.v1 import ExactnessClass, Fallback, Method, Step


def step(
    id: str,
    method: Method = Method.RULE,
    *,
    exactness: ExactnessClass | None = ExactnessClass.EXACT,
    depends_on: tuple[str, ...] = (),
    fallback: bool = False,
) -> Step:
    if method in (Method.WAIT, Method.HUMAN):
        exactness = None
    if method in (Method.LLM, Method.WORKER) and exactness is ExactnessClass.EXACT:
        exactness = ExactnessClass.TOLERANT
    return Step(
        id=id,
        method=method,
        reason="table test",
        rejected=(),
        exactness=exactness,
        fallback=Fallback(when="always", to=Method.HUMAN) if fallback else None,
        depends_on=depends_on or None,
    )


def version(*steps: Step, **extra: object) -> ProcessVersion:
    return ProcessVersion(
        process_id="p", version="1", name="P", autonomy_level=2, steps=steps, **extra
    )


GRAPH_CASES: list[tuple[str, tuple[Step, ...], str | None]] = [
    ("single step", (step("a"),), None),
    ("chain", (step("a"), step("b", depends_on=("a",))), None),
    (
        "diamond",
        (
            step("a"),
            step("b", depends_on=("a",)),
            step("c", depends_on=("a",)),
            step("d", depends_on=("b", "c")),
        ),
        None,
    ),
    ("duplicate id", (step("a"), step("a")), "defined twice"),
    ("unknown dependency", (step("a", depends_on=("zz",)),), "not a step of this process"),
    ("self cycle", (step("a", depends_on=("a",)),), "cycle"),
    ("two-step cycle", (step("a", depends_on=("b",)), step("b", depends_on=("a",))), "cycle"),
    (
        "cycle behind a valid prefix",
        (
            step("a"),
            step("b", depends_on=("a", "d")),
            step("c", depends_on=("b",)),
            step("d", depends_on=("c",)),
        ),
        "cycle through 'b', 'c', 'd'",
    ),
    ("island", (step("a"), step("b", depends_on=("a",)), step("c")), "'c' cannot be reached"),
    (
        "two islands",
        (step("a"), step("b", depends_on=("a",)), step("c"), step("d", depends_on=("c",))),
        "'c', 'd' cannot be reached",
    ),
]


@pytest.mark.parametrize(("name", "steps", "finding"), GRAPH_CASES, ids=[c[0] for c in GRAPH_CASES])
def test_graph_rules(name: str, steps: tuple[Step, ...], finding: str | None) -> None:
    findings = validation.validate_graph(steps)
    if finding is None:
        assert findings == []
        version(*steps)  # and the constructor agrees
    else:
        assert any(finding in f for f in findings), findings
        with pytest.raises(InvalidProcess) as raised:
            version(*steps)
        assert any(finding in f for f in raised.value.findings)


def test_every_finding_is_reported_at_once() -> None:
    steps = (step("a"), step("a"), step("b", depends_on=("zz",)))
    with pytest.raises(InvalidProcess) as raised:
        version(*steps)
    assert len(raised.value.findings) == 1, "duplicates are reported before edges are judged"
    findings = validation.validate_graph(
        (step("b", depends_on=("zz",)), step("c", depends_on=("yy",)))
    )
    assert len(findings) == 2


ORDER_CASES = [
    ((step("a"), step("b", depends_on=("a",))), ["a", "b"]),
    ((step("b", depends_on=("a",)), step("a")), ["a", "b"]),
    (
        (
            step("d", depends_on=("b", "c")),
            step("c", depends_on=("a",)),
            step("b", depends_on=("a",)),
            step("a"),
        ),
        ["a", "c", "b", "d"],
    ),
    ((step("x"), step("y"), step("z", depends_on=("x", "y"))), ["x", "y", "z"]),
]


@pytest.mark.parametrize(("steps", "expected"), ORDER_CASES)
def test_topological_order_respects_edges_and_keeps_declared_order_for_ties(
    steps: tuple[Step, ...], expected: list[str]
) -> None:
    assert [s.id for s in version(*steps).ordered()] == expected


def test_edges_are_derived_from_depends_on() -> None:
    v = version(step("a"), step("b", depends_on=("a",)), step("c", depends_on=("a", "b")))
    assert v.edges == (
        Edge(from_step="a", to_step="b"),
        Edge(from_step="a", to_step="c"),
        Edge(from_step="b", to_step="c"),
    )


def test_process_exactness_is_the_strictest_result() -> None:
    assert version(step("a", exactness=ExactnessClass.FREE)).exactness is ExactnessClass.FREE
    assert (
        version(
            step("a", exactness=ExactnessClass.FREE),
            step("b", exactness=ExactnessClass.SOURCED, depends_on=("a",)),
        ).exactness
        is ExactnessClass.SOURCED
    )
    assert version(step("w", Method.WAIT)).exactness is None


def test_work_must_name_a_step() -> None:
    with pytest.raises(InvalidProcess, match="work is given for 'zz'"):
        version(step("a"), work={"zz": {"rule": "constant", "value": 1}})


def test_ref_names_process_and_version() -> None:
    v = version(
        step("a"), triggers=(Trigger(schedule="daily"),), slo=Slo(freshness=timedelta(hours=24))
    )
    assert v.ref == "p@1"
    assert v.id == v.ref
    assert v.triggers[0].schedule == "daily"


def test_trigger_names_a_schedule_or_an_event_not_both() -> None:
    with pytest.raises(ValueError):
        Trigger(schedule="daily", event="issue.opened")
    with pytest.raises(ValueError):
        Trigger()
    assert Trigger(event="issue.opened", filter="label:ready").event == "issue.opened"


STEP_RULE_CASES = [
    ("exact on rule", Method.RULE, ExactnessClass.EXACT, True, None, []),
    ("exact on statistics", Method.STATISTICS, ExactnessClass.EXACT, True, None, []),
    ("exact on llm", Method.LLM, ExactnessClass.EXACT, True, None, ["classed exact"]),
    ("exact on worker", Method.WORKER, ExactnessClass.EXACT, True, None, ["classed exact"]),
    ("exact on ml", Method.ML, ExactnessClass.EXACT, True, "m@1", ["classed exact"]),
    ("exact on neural", Method.NEURAL, ExactnessClass.EXACT, True, "m@1", ["classed exact"]),
    ("rule without class", Method.RULE, None, True, None, ["carries no exactness class"]),
    (
        "wait with class",
        Method.WAIT,
        ExactnessClass.FREE,
        True,
        None,
        ["carries an exactness class"],
    ),
    (
        "wait classed exact",
        Method.WAIT,
        ExactnessClass.EXACT,
        True,
        None,
        ["classed exact", "carries an exactness class"],
    ),
    (
        "human with class",
        Method.HUMAN,
        ExactnessClass.FREE,
        True,
        None,
        ["carries an exactness class"],
    ),
    ("llm without fallback", Method.LLM, ExactnessClass.FREE, False, None, ["names no fallback"]),
    (
        "worker without fallback",
        Method.WORKER,
        ExactnessClass.FREE,
        False,
        None,
        ["names no fallback"],
    ),
    ("ml without model", Method.ML, ExactnessClass.SOURCED, True, None, ["pins no model"]),
    ("neural with model", Method.NEURAL, ExactnessClass.SOURCED, True, "m@1", []),
]


@pytest.mark.parametrize(
    ("name", "method", "exactness", "fallback", "model", "expected"),
    STEP_RULE_CASES,
    ids=[c[0] for c in STEP_RULE_CASES],
)
def test_step_rules_of_the_domain_on_unvalidated_steps(
    name: str,
    method: Method,
    exactness: ExactnessClass | None,
    fallback: bool,
    model: str | None,
    expected: list[str],
) -> None:
    """The domain's own reading of ADR-0004/0014/0018, on a step built without the kernel's
    constructor checks — the road a deserialised or planner-built step would take."""
    unvalidated = Step.model_construct(
        id="s",
        method=method,
        reason="r",
        rejected=(),
        exactness=exactness,
        fallback=Fallback(when="always", to=Method.HUMAN) if fallback else None,
        model=model,
    )
    findings = validation.validate_step(unvalidated)
    assert len(findings) == len(expected), findings
    for fragment, finding in zip(expected, findings, strict=True):
        assert fragment in finding
