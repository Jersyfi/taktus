"""Where a figure a query computed may go (UC-5.6 §2, ADR-0262 §4): a query a model wrote feeds
only a step of class tolerant or free, and an exact step is fed only by a query fixed in the
version. Refused when the version is registered."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess
from taktus.components.process.domain.service import queries
from taktus.shared.v1 import Check, CheckKind, ExactnessClass, Fallback, Method, Step

ROOT = Path(__file__).resolve().parents[3]
FIXED = "SELECT step, users FROM signups_funnel"


def step(id: str, method: Method, exactness: ExactnessClass | None) -> Step:
    checks = (
        (Check(kind=CheckKind.BOUNDS, subject="it", pattern="."),)
        if exactness in (ExactnessClass.EXACT, ExactnessClass.SOURCED)
        else None
    )
    fallback = (
        None if method in (Method.RULE, Method.STATISTICS) else Fallback(when="w", to=Method.HUMAN)
    )
    return Step(
        id=id,
        method=method,
        reason="r",
        rejected=(),
        exactness=exactness,
        checks=checks,
        fallback=fallback,
    )


def reading(query: Any) -> dict[str, Any]:
    return {"rule": "connector", "operation": "warehouse.queries.run", "input": {"query": query}}


def template(*sources: str) -> dict[str, Any]:
    return {"rule": "template", "text": "x", "values": {s: {"$from": s} for s in sources}}


WRITER = step("write", Method.LLM, ExactnessClass.FREE)
WRITER_WORK = {"purpose": "analysis", "prompt": "q"}


def test_a_query_fixed_in_the_version_may_feed_an_exact_step() -> None:
    steps = [step("rows", Method.RULE, ExactnessClass.SOURCED),
             step("total", Method.RULE, ExactnessClass.EXACT)]  # fmt: skip
    assert queries.findings(steps, {"rows": reading(FIXED), "total": template("rows")}) == []


@pytest.mark.parametrize("fed", [ExactnessClass.EXACT, ExactnessClass.SOURCED])
def test_a_query_a_model_wrote_feeds_no_exact_or_sourced_step(fed: ExactnessClass) -> None:
    steps = [WRITER, step("rows", Method.RULE, ExactnessClass.TOLERANT),
             step("figure", Method.RULE, fed)]  # fmt: skip
    work = {
        "write": WRITER_WORK,
        "rows": reading({"$from": "write", "$select": "text"}),
        "figure": template("rows"),
    }
    [finding] = queries.findings(steps, work)
    assert "'figure'" in finding and "tolerant or free" in finding


def test_the_reading_of_a_query_a_model_wrote_is_itself_tolerant_or_free() -> None:
    steps = [WRITER, step("rows", Method.RULE, ExactnessClass.SOURCED)]
    [finding] = queries.findings(
        steps, {"write": WRITER_WORK, "rows": reading({"$from": "write", "$select": "text"})}
    )
    assert "'rows'" in finding


@pytest.mark.parametrize("fed", [ExactnessClass.TOLERANT, ExactnessClass.FREE])
def test_a_query_a_model_wrote_may_feed_a_tolerant_or_free_step(fed: ExactnessClass) -> None:
    steps = [
        WRITER,
        step("rows", Method.RULE, ExactnessClass.TOLERANT),
        step("reading", Method.LLM, ExactnessClass.FREE),
        step("post", Method.RULE, fed),
    ]
    work = {
        "write": WRITER_WORK,
        "rows": reading({"$from": "write"}),
        "reading": {"prompt": "p", "values": {"rows": {"$from": "rows"}}},
        "post": template("reading"),
    }
    assert queries.findings(steps, work) == []


def test_a_model_is_followed_through_the_steps_between_it_and_the_query() -> None:
    """A rule that puts a model's words into a query is no wall: the query is still the
    model's."""
    steps = [WRITER, step("shape", Method.RULE, ExactnessClass.FREE),
             step("rows", Method.RULE, ExactnessClass.TOLERANT),
             step("sum", Method.RULE, ExactnessClass.TOLERANT),
             step("figure", Method.STATISTICS, ExactnessClass.EXACT)]  # fmt: skip
    work = {
        "write": WRITER_WORK,
        "shape": template("write"),
        "rows": reading({"$from": "shape"}),
        "sum": template("rows"),
        "figure": template("sum"),
    }
    [finding] = queries.findings(steps, work)
    assert "'figure'" in finding


def test_a_query_given_as_an_input_may_feed_sourced_but_not_exact() -> None:
    steps = [step("rows", Method.RULE, ExactnessClass.SOURCED),
             step("figure", Method.RULE, ExactnessClass.EXACT)]  # fmt: skip
    work = {"rows": reading({"$input": "query"}), "figure": template("rows")}
    [finding] = queries.findings(steps, work)
    assert "'figure'" in finding and "not literal text in the version" in finding
    assert queries.findings(steps[:1], {"rows": work["rows"]}) == []


def test_a_parameter_a_model_chose_makes_the_reading_the_models() -> None:
    steps = [WRITER, step("rows", Method.RULE, ExactnessClass.SOURCED)]
    work = {
        "write": WRITER_WORK,
        "rows": {
            "rule": "connector",
            "operation": "warehouse.queries.run",
            "input": {"query": FIXED + " WHERE step = @s", "parameters": {"s": {"$from": "write"}}},
        },
    }
    assert len(queries.findings(steps, work)) == 1


def test_a_reading_of_another_capability_is_not_held_to_the_rule() -> None:
    steps = [WRITER, step("issue", Method.RULE, ExactnessClass.SOURCED)]
    work = {
        "write": WRITER_WORK,
        "issue": {"rule": "connector", "operation": "issues.records.read",
                  "input": {"id": {"$from": "write"}}},
    }  # fmt: skip
    assert queries.findings(steps, work) == []


def test_registration_refuses_a_version_whose_model_written_query_feeds_a_sourced_step() -> None:
    bundle = yaml.safe_load(
        (ROOT / "blueprints/software-operations/processes/B-9.02-figures.yaml").read_text("utf-8")
    )
    assert parse_bundle(bundle).ref.startswith("b-9-02@"), "as shipped, it registers"
    rows = next(s for s in bundle["steps"] if s["id"] == "rows")
    rows["exactness"] = "sourced"
    with pytest.raises(InvalidProcess) as refused:
        parse_bundle(bundle)
    assert any("'rows'" in f and "tolerant or free" in f for f in refused.value.findings)
