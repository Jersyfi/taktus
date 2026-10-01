"""No step is admitted without an estimate, and a budget is a budget (ADR-0005): every kind of
step is estimated before it is admitted, a step that cannot be is refused, the estimate is
reserved as calibration scales it, the run says what its budget can promise when it is set,
and a worker that halts before its ceiling halts the run with cause `limit`."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fakes import FakeConnector, FakeModel, FakeWorker, InnerStep

from taktus.adapters.driven.models import StaticModelPool
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.ports.model import Calculability, PriceTable
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit, TokenLimit

from .test_connector_steps import READ, ConnectorHarness, call
from .test_engine import BUDGET, Harness, rule, worker
from .test_llm_steps import WORK, ModelHarness, llm

TABLE = PriceTable(
    version="test-1",
    valid_from=datetime(2026, 9, 30, tzinfo=UTC),
    currency="usd",
    unit_tokens=1_000_000,
    source="a test",
    prices={"fake-model@1": {"input": 3.0, "output": 15.0, "cache_write": 3.75}},
)
ISSUE = rule("issue", {"rule": "constant", "value": {"number": 11, "title": "Report git"}})


def priced(h: ModelHarness, table: PriceTable | None = TABLE) -> ModelHarness:
    """The harness's engine, with a price table."""
    h.engine = RunEngine(
        runs=h.runs,
        work=h.persistence,
        objects=h.objects,
        ledger=h.ledger,
        provenance=h.provenance,
        workers=h.engine._workers,
        clock=h.clock,
        ids=h.ids,
        telemetry=h.engine._telemetry,
        models=StaticModelPool([("model.fake", ["reasoning"], h.model, "fake-model@1")]),
        options=EngineOptions(prices=table),
    )
    return h


async def statement(h: Harness, run: Run) -> dict[str, object]:
    entries = [e for e in await h.entries(run) if e.kind == "budget.set"]
    assert len(entries) == 1 and entries[0].content_digest is not None
    content = await h.objects.get(entries[0].content_digest)
    assert content is not None
    result: dict[str, object] = json.loads(content)
    return result


# --- every kind of step is estimated -------------------------------------------------------------


async def test_an_llm_step_is_estimated_before_it_is_admitted() -> None:
    h = ModelHarness(ISSUE, llm("refine", WORK | {"max_output_tokens": 300}, after=("issue",)))
    run = await h.start(Limits(tokens=TokenLimit.of(10_000, 1_000)))
    assert run.state is RunState.FINISHED
    refine = run.step_run("refine")
    assert refine.estimate is not None
    assert refine.estimate.tokens_out == 300, "the output is bounded by the limit the step sets"
    assert refine.estimate.tokens_in is not None and refine.estimate.tokens_in > 0
    admitted = next(
        e for e in await h.entries(run) if e.kind == "step.admitted" and e.refs.step_id == "refine"
    )
    assert admitted.consumption is not None and admitted.consumption.tokens_out == 300
    assert refine.consumption is not None and refine.consumption.tokens_by_model is not None
    assert "fake-model@1" in refine.consumption.tokens_by_model


async def test_a_model_that_cannot_count_is_refused_and_never_called() -> None:
    model = FakeModel(
        declaration=Calculability(
            input_count="none",
            output_cap="hard",
            usage_kinds=("input", "output"),
            billing="per_token",
        )
    )
    h = ModelHarness(ISSUE, llm("refine", WORK, after=("issue",)), model=model)
    run = await h.start(Limits(quota=QuotaLimit(units=10)))
    assert run.state is RunState.HALTED and run.cause is Cause.NO_ESTIMATE
    refine = run.step_run("refine")
    assert refine.state is StepState.REJECTED and refine.estimate is None
    assert "cannot count" in (refine.reason or "")
    assert model.prompts == [], "the model was never asked"
    kinds = await h.kinds(run)
    assert "step.rejected:refine:no_estimate" in kinds and "step.started:refine" not in kinds


async def test_a_currency_budget_needs_a_price_to_estimate_an_llm_step() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))), table=None)
    run = await h.start(Limits(currency={"usd": 1.0}))
    assert run.cause is Cause.NO_ESTIMATE
    assert "price table has no price" in (run.step_run("refine").reason or "")


async def test_a_priced_llm_step_reserves_money_at_the_dearest_input_price() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    run = await h.start(Limits(currency={"usd": 1.0}))
    assert run.state is RunState.FINISHED
    estimate = run.step_run("refine").estimate
    assert estimate is not None and estimate.currency is not None
    tokens_in, tokens_out = estimate.tokens_in or 0, estimate.tokens_out or 0
    expected = (tokens_in * 3.75 + tokens_out * 15.0) / 1_000_000
    assert estimate.currency["usd"] == round(expected, 9), "a cache write, the worst case"


async def test_a_priced_llm_step_that_does_not_fit_is_rejected_before_the_call() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    run = await h.start(Limits(currency={"usd": 0.001}))
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert h.model.prompts == []


async def test_a_connector_call_reserves_its_declared_demand() -> None:
    h = ConnectorHarness(call("read", READ, {"id": "issue-1"}))
    run = await h.start(Limits(quota=QuotaLimit(units=10)))
    assert run.state is RunState.FINISHED
    assert run.step_run("read").estimate is not None
    assert run.step_run("read").estimate.quota_units == 1  # type: ignore[union-attr]


async def test_a_connector_operation_without_a_declared_demand_is_refused() -> None:
    class Undeclared(FakeConnector):
        async def capabilities(self):  # type: ignore[no-untyped-def]
            declaration = await super().capabilities()
            operations = tuple(
                op.model_copy(update={"demand": None}) for op in declaration.operations
            )
            return declaration.model_copy(update={"operations": operations})

    h = ConnectorHarness(call("read", READ, {"id": "issue-1"}), connector=Undeclared())
    run = await h.start(Limits(quota=QuotaLimit(units=10)))
    assert run.cause is Cause.NO_ESTIMATE
    assert "declares no demand" in (run.step_run("read").reason or "")
    assert h.connector.calls == [], "nothing was called"


async def test_a_rule_demands_nothing_and_that_is_an_estimate() -> None:
    h = Harness(rule("one", {"rule": "constant", "value": 1}))
    run = await h.start()
    assert run.state is RunState.FINISHED
    estimate = run.step_run("one").estimate
    assert estimate is not None and estimate.quantities() == {}


# --- the line, the reservation, the statement ----------------------------------------------------


async def test_the_margin_is_held_back_from_the_first_step() -> None:
    fake = FakeWorker(estimate_seconds=10, script=(InnerStep("one", 1.0),))
    h = Harness(worker("do"), workers=[fake])
    run = await h.engine.start(
        StartRun(
            plan=h.plan(),
            work=h.work,
            budget=BUDGET,
            process_version="p@1",
            actor="idn_t",
            tenant="t",
            margin=0.2,
        )
    )
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert "8.000s left" in (run.step_run("do").reason or ""), "10 s less a margin of 20 %"


async def test_a_worker_that_underestimated_before_is_reserved_what_it_used() -> None:
    fake = FakeWorker(estimate_seconds=1.0, script=(InnerStep("one", 3.0),))
    budget = Limits(compute=ComputeLimit(seconds=100, resource_class="cpu.small"))
    h = Harness(worker("do"), workers=[fake])
    first = await h.start(budget)
    assert first.state is RunState.FINISHED
    second = await h.start(budget)
    reservation = second.step_run("do").reservation
    assert reservation is not None and reservation.compute_seconds == 3.0
    assert "step.reserved:do:calibrated" in await h.kinds(second)
    assert fake.assignments[-1].limits.compute is not None
    assert fake.assignments[-1].limits.compute.seconds == 3.0, "the ceiling is the reservation"


async def test_the_budget_says_what_it_can_promise_when_it_is_set() -> None:
    model = FakeModel(
        declaration=Calculability(
            input_count="none",
            output_cap="none",
            usage_kinds=("input", "output"),
            billing="per_window",
        )
    )
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",)), model=model))
    run = await h.start(Limits(currency={"usd": 5.0}))
    said = await statement(h, run)
    (promise,) = said["promises"]  # type: ignore[misc]
    assert promise["kind"] == "currency" and promise["how"] == "window_share"
    assert "cannot be enforced" in promise["reason"]
    assert said["price_table"]["version"] == "test-1"  # type: ignore[index]
    assert said["held"] == {"currency": {"usd": 5.0}}


# --- a worker halts before its ceiling -------------------------------------------------------


async def test_a_worker_that_halts_at_its_ceiling_halts_the_run_on_the_limit() -> None:
    fake = FakeWorker(
        halt_on_limit="compute", script=(InnerStep("one", 0.5), InnerStep("two", 0.5))
    )
    h = Harness(worker("do"), workers=[fake])
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    do = run.step_run("do")
    assert do.state is StepState.STOPPED and do.checkpoint is not None, "resumable"
    assert "compute ceiling" in (do.reason or "")


async def test_a_stopped_step_is_no_calibration_history() -> None:
    """A stopped attempt used part of its estimate; read as history it would flatter the worker
    and take away the margin it is owed while nothing has measured it (DEC-0034)."""
    budget = Limits(compute=ComputeLimit(seconds=100, resource_class="cpu.small"))
    stops = FakeWorker(
        halt_on_limit="compute", script=(InnerStep("one", 0.5), InnerStep("two", 0.5))
    )
    h = Harness(worker("do"), workers=[stops])
    h.engine._options = EngineOptions()  # the default: an uncalibrated worker reserves twice
    first = await h.start(budget)
    assert first.step_run("do").state is StepState.STOPPED
    second = await h.start(budget)
    reservation = second.step_run("do").reservation
    assert reservation is not None and reservation.compute_seconds == 4.0, (
        "the estimate of 2 s, twice: the stopped attempt counted as no history"
    )
