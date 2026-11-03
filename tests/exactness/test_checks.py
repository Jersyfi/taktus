"""UC-4.13 §2 and #223 (ADR-0152): the checks of the catalogue run, and an `exact` result counts
only when its checks pass.

Three levels. The rules: every kind has a fixture that passes and one that fails, and a wrong
value that slips through each, which is exactly the case the exactness statement names as that
step's residual risk. The engine: a failed check fails its step, no step after it reads the
value, and the run escalates with the check, its parameters and what it compared; an approval
holds a value above its threshold for its role, and a sample puts a chosen result to its role
after the fact. The method: the module that judges reaches no model.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fakes.connector import READ
from governance.test_anchors import TENANT, World

from taktus.components.process.domain.service import exactness
from taktus.components.run.application.query import (
    ProvenanceOfRun,
    ProvenanceQuery,
    SampleRates,
)
from taktus.components.run.domain.model import RunState, StepState, control_of
from taktus.components.run.domain.service import checking
from taktus.shared.v1 import Check, CheckKind, ExactnessClass, InputKind, Method, Step

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "fake.records"
CONTROLLER = "idn_controller"


def check(kind: str, **given: Any) -> Check:
    return Check.model_validate({"kind": kind, **given})


BOUNDS = check("bounds", subject="the booked amount", minimum=0, maximum=1000)
PATTERN = check("bounds", subject="the tax code", pattern="^DE[0-9]{2}$")
RECONCILED = check(
    "reconciliation", subject="the line amounts", total="the invoice total", source=SOURCE
)
AGREED = check("agreement", subject="the headcount", source=SOURCE, reference="source")
APPROVAL = check("approval", subject="the payment", threshold=500, role="controller")
SAMPLING = check("sampling", subject="the booking", share=1, role="controller")
RECOMPUTED = check("recomputation", subject="the sum")


# --- every check of the catalogue: a fixture that passes, and one that fails ---------------------


@pytest.mark.parametrize(
    ("given", "value", "passes"),
    [
        (BOUNDS, 120, True),
        (BOUNDS, "999.99", True),
        (BOUNDS, 1000.01, False),
        (BOUNDS, -1, False),
        (BOUNDS, "twelve", False),
        (BOUNDS, True, False),
        (PATTERN, "DE19", True),
        (PATTERN, "AT19", False),
    ],
)
def test_bounds_pass_inside_and_fail_outside(given: Check, value: Any, passes: bool) -> None:
    assert checking.bounds(1, given, value).passed is passes


@pytest.mark.parametrize(
    ("parts", "total", "passes"),
    [
        ([100, 20], "120.00", True),
        ({"a": 0.1, "b": 0.2}, 0.3, True),  # decimal, not binary floating point
        (120, 120, True),
        ([100, 21], "120.00", False),
        ([100, "x"], 120, False),
        ([100, 20], "unknown", False),
    ],
)
def test_reconciliation_sums_the_parts_against_the_total_read(
    parts: Any, total: Any, passes: bool
) -> None:
    assert checking.reconciliation(1, RECONCILED, parts, total).passed is passes


@pytest.mark.parametrize(
    ("value", "other", "passes"),
    [(42, 42, True), (42, "42.0", True), ("a", "a", True), (42, 43, False), ("a", "b", False)],
)
def test_agreement_holds_the_value_to_the_second_system(
    value: Any, other: Any, passes: bool
) -> None:
    assert checking.agreement(1, AGREED, value, other).passed is passes


def test_recomputation_passes_the_same_digest_and_fails_another() -> None:
    assert checking.recomputation(1, RECOMPUTED, "sha256:" + "a" * 64, "sha256:" + "a" * 64).passed
    assert not checking.recomputation(
        1, RECOMPUTED, "sha256:" + "a" * 64, "sha256:" + "b" * 64
    ).passed


@pytest.mark.parametrize(("value", "held"), [(500.01, True), (500, False), (12, False)])
def test_an_approval_holds_a_value_above_its_threshold_only(value: Any, held: bool) -> None:
    assert checking.above_threshold(APPROVAL, value) is held


def test_sampling_chooses_the_same_results_for_the_same_runs_and_about_its_share() -> None:
    half = check("sampling", share=0.25, role="controller")
    chosen = [checking.sampled(half, f"run_{n}", "book") for n in range(2000)]
    assert chosen == [checking.sampled(half, f"run_{n}", "book") for n in range(2000)]
    assert 0.2 < sum(chosen) / len(chosen) < 0.3
    assert all(checking.sampled(SAMPLING, f"run_{n}", "book") for n in range(50))


def test_numbers_are_compared_in_decimal_from_their_text() -> None:
    assert checking.decimal("0.10") == Decimal("0.1")
    assert checking.decimal(float("nan")) is None
    assert checking.decimal(False) is None


# --- what a check does not cover: a wrong value slips through, and the statement names it --------


def _step(*checks: Check) -> Step:
    return Step(
        id="book",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        checks=checks,
    )


def _residual(given: Check) -> str:
    stated = exactness.statement("p@1", "P", [_step(given)])
    (line,) = [line for line in stated.residual if line.startswith("`book`")]
    return line


def test_a_wrong_value_inside_the_bounds_passes_and_the_statement_names_that_case() -> None:
    wrong = 999  # the right amount was 99: a digit too many, still inside the bounds
    assert checking.bounds(1, BOUNDS, wrong).passed
    assert "a wrong value that lies between 0 and 1000" in _residual(BOUNDS)


def test_offsetting_errors_reconcile_and_the_statement_names_that_case() -> None:
    wrong = [110, 10]  # each line wrong by 10, in opposite directions
    assert checking.reconciliation(1, RECONCILED, wrong, 120).passed
    assert "an error another part offsets" in _residual(RECONCILED)


def test_a_total_itself_wrong_reconciles_and_the_statement_names_that_case() -> None:
    assert checking.reconciliation(1, RECONCILED, [100, 25], 125).passed  # the total was 120
    assert "the invoice total itself wrong" in _residual(RECONCILED)


def test_both_systems_wrong_alike_agree_and_the_statement_names_that_case() -> None:
    assert checking.agreement(1, AGREED, 41, 41).passed  # both hold 41; the truth is 42
    assert "a value wrong in both systems alike" in _residual(AGREED)


def test_a_wrong_value_at_the_threshold_counts_unconfirmed_and_the_statement_names_it() -> None:
    assert checking.above_threshold(APPROVAL, 500) is False  # wrong, and not above 500
    assert "a wrong value at or below 500" in _residual(APPROVAL)


def test_a_wrong_value_outside_the_sample_counts_and_the_statement_names_that_case() -> None:
    tenth = check("sampling", subject="the booking", share=0.1, role="controller")
    unsampled = next(n for n in range(100) if not checking.sampled(tenth, f"run_{n}", "book"))
    assert not checking.sampled(tenth, f"run_{unsampled}", "book")
    assert "a wrong value outside the sample" in _residual(tenth)


def test_wrong_inputs_recompute_alike_and_the_statement_names_that_case() -> None:
    same = "sha256:" + "c" * 64  # computed twice over the same wrong input
    assert checking.recomputation(1, RECOMPUTED, same, same).passed
    assert "wrong inputs" in _residual(RECOMPUTED)


# --- the method: rules, never a model ------------------------------------------------------------


def test_no_model_chooses_or_evaluates_a_check() -> None:
    module = ROOT / "src" / "taktus" / "components" / "run" / "domain" / "service" / "checking.py"
    imported: set[str] = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("model" in name or "llm" in name for name in imported), imported


# --- the engine: a result counts only when its checks pass ---------------------------------------


def booking(*checks: Check, value: Any, **checking_work: Any) -> tuple[Step, dict[str, Any]]:
    work: dict[str, Any] = {"rule": "constant", "value": value}
    if checking_work:
        work["checking"] = checking_work
    return _step(*checks), work


def after(step_id: str = "post", on: str = "book") -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=step_id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=(on,),
        checks=(RECOMPUTED,),
    )
    return step, {"rule": "constant", "value": {"$from": on}}


TOTAL_READ = {SOURCE: {"operation": READ, "input": {"id": "invoice"}, "select": "total"}}


async def world(*definitions: tuple[Step, dict[str, Any]]) -> World:
    w = await World(*definitions).setup()
    await w.people.directory.add(TENANT, CONTROLLER, (TENANT,), roles=("controller",))
    w.connector.reads["invoice"] = {"id": "invoice", "total": "120.00"}
    return w


async def test_a_result_whose_checks_pass_counts_and_the_total_read_is_in_its_provenance() -> None:
    w = await world(booking(RECONCILED, value=[100, 20], reads=TOTAL_READ), after())
    run = await w.start()
    assert run.state is RunState.FINISHED
    records = await ProvenanceQuery(w.engine._provenance, w.runs, w.ledger, w.persistence).of_run(
        ProvenanceOfRun(run_id=run.id, tenant="t")
    )
    (book,) = [r for r in records if r.step_id == "book"]
    (read,) = [i for i in book.inputs if i.kind is InputKind.SOURCE]
    assert read.capability == SOURCE
    assert read.ref is not None and READ in read.ref
    assert read.observed_at is not None


async def test_a_failed_check_reaches_no_dependent_step_and_the_run_escalates_with_it() -> None:
    w = await world(booking(RECONCILED, value=[100, 21], reads=TOTAL_READ), after())
    run = await w.start()
    assert run.state is RunState.ESCALATED
    book = run.step_run("book")
    assert book.state is StepState.FAILED
    assert book.checkpoint is None  # the step did not finish with the result
    assert run.step_run("post").state is StepState.PLANNED
    reason = book.reason or ""
    assert "reconciliation" in reason
    assert "the invoice total" in reason and SOURCE in reason
    assert "121" in reason and "120.00" in reason
    assert "step.finished:book:check_failed" in await w.kinds(run)


async def test_a_check_without_a_read_for_its_source_fails_rather_than_passes() -> None:
    w = await world(booking(RECONCILED, value=[100, 20]))
    run = await w.start()
    assert run.step_run("book").state is StepState.FAILED
    assert "checking.reads" in (run.step_run("book").reason or "")


async def test_a_value_above_the_threshold_waits_for_its_role_and_counts_once_confirmed() -> None:
    w = await world(booking(APPROVAL, value=750), after())
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN
    book = run.step_run("book")
    assert book.state is StepState.WAITING_HUMAN
    assert run.step_run("post").state is StepState.PLANNED
    assert book.anchoring is not None
    (request_id,) = book.anchoring.requests
    request = await w.request(request_id)
    assert request.request.class_ == "domain"
    assert "750" in request.request.question
    await w.answer(request_id, option="A", by=CONTROLLER)
    run = await w.confirm(request_id, by=CONTROLLER)
    assert run.state is RunState.FINISHED
    assert run.step_run("book").state is StepState.SUCCEEDED
    assert run.step_run("post").state is StepState.SUCCEEDED


async def test_a_value_the_decider_does_not_confirm_does_not_count() -> None:
    w = await world(booking(APPROVAL, value=750), after())
    run = await w.start()
    (request_id,) = run.step_run("book").anchoring.requests  # type: ignore[union-attr]
    await w.answer(request_id, option="B", by=CONTROLLER)
    run = await w.confirm(request_id, by=CONTROLLER)
    assert run.state is RunState.HALTED
    assert run.step_run("book").checkpoint is None
    assert run.step_run("post").state is StepState.PLANNED


async def test_a_value_at_or_below_the_threshold_counts_without_a_request() -> None:
    w = await world(booking(APPROVAL, value=500), after())
    run = await w.start()
    assert run.state is RunState.FINISHED
    assert run.step_run("book").anchoring is None


async def test_a_sample_goes_to_its_role_after_the_fact_and_its_verdict_is_read() -> None:
    w = await world(booking(SAMPLING, value=120), after())
    run = await w.start()
    assert run.state is RunState.FINISHED  # nothing waits for the sample
    (sampled,) = [e for e in await w.entries(run) if e.kind == "check.sampled"]
    assert sampled.refs.step_id == "book" and sampled.outcome == "check_1"
    request_id = sampled.refs.decision_request_id
    assert request_id is not None
    request = await w.request(request_id)
    assert request.request.blocking == ()
    rates = SampleRates(w.ledger, w.persistence, w.decisions.requests)
    (before,) = await rates.of("t")
    assert (before.sampled, before.judged, before.wrong, before.rate) == (1, 0, 0, None)
    await w.answer(request_id, option="B", by=CONTROLLER)
    await w.decisions.confirm.execute(_confirmation(request_id))
    (after_verdict,) = await rates.of("t")
    assert (after_verdict.judged, after_verdict.wrong, after_verdict.rate) == (1, 1, 1.0)


def _confirmation(request_id: str) -> Any:
    from taktus.components.decision.application.service import ConfirmRequest

    return ConfirmRequest(tenant="t", request_id=request_id, identity=CONTROLLER, confirmed=True)


async def test_a_recomputation_runs_the_rule_again_and_the_same_value_counts() -> None:
    w = await world(booking(RECOMPUTED, value=7))
    run = await w.start()
    assert run.state is RunState.FINISHED


def test_the_part_a_check_judges_and_its_reads_are_work_of_the_step() -> None:
    step, work = booking(RECONCILED, value={"lines": [1, 2]}, select="lines", reads=TOTAL_READ)
    control = control_of(step, work)
    assert control.checking is not None
    assert control.checking.select == "lines"
    assert control.checking.reads[SOURCE].operation == READ
    assert {kind for kind in CheckKind} >= {RECONCILED.kind}


async def test_a_recomputation_of_a_call_holds_the_value_to_its_answer_and_calls_once() -> None:
    step = Step(
        id="book",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        checks=(RECOMPUTED,),
    )
    w = await world((step, {"rule": "connector", "operation": READ, "input": {"id": "invoice"}}))
    run = await w.start()
    assert run.step_run("book").state is StepState.SUCCEEDED
    assert len(w.connector.calls) == 1
