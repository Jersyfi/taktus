"""A currency budget holds an `llm` step's money after the step finished (#235, ADR-0005 third
amendment, points 2 and 3).

Admission reserves an `llm` step's money at the price table. Once the step ends it records
tokens per model and no money; the run's money is derived from those tokens at the run's table
at every boundary, never stored on the step. The figures below are computed by hand from the
test table: input 3.0, output 15.0 and cache write 3.75 usd per million tokens; the fake model
reads 11 tokens of the prompt and answers in 8.
"""

from __future__ import annotations

from typing import Any

import pytest

from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.service import budget as budgeting
from taktus.ports.model import price
from taktus.ports.worker import Limits

from .test_estimates import ISSUE, TABLE, priced
from .test_llm_steps import WORK, ModelHarness, llm

STEP = WORK | {"max_output_tokens": 300}
ESTIMATE = round((11 * 3.75 + 300 * 15.0) / 1_000_000, 9)
"""Each step's estimate: its input at the dearest input price, its output at its limit."""
USED = (11 * 3.0 + 8 * 15.0) / 1_000_000
"""What the first step used, at the table: the money it leaves held once it ended."""


def two_steps() -> ModelHarness:
    return priced(
        ModelHarness(ISSUE, llm("one", STEP, after=("issue",)), llm("two", STEP, after=("one",)))
    )


async def test_the_estimate_is_the_one_computed_by_hand() -> None:
    h = two_steps()
    run = await h.start(Limits(currency={"usd": 1.0}))
    assert run.state is RunState.FINISHED
    for step in ("one", "two"):
        estimate = run.step_run(step).estimate
        assert estimate is not None and estimate.currency == {"usd": ESTIMATE}


async def test_the_second_step_is_admitted_against_the_budget_less_the_first_steps_money() -> None:
    """A budget that fits one step's estimate and not that estimate beside the money the first
    step used halts the run with cause `limit` before the second call. Before #235 the second
    step was admitted against the whole budget."""
    h = two_steps()
    budget = ESTIMATE + USED / 2
    run = await h.start(Limits(currency={"usd": budget}))
    assert run.margin == 0.0, "the line is the budget itself"
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert run.step_run("one").state is StepState.SUCCEEDED
    assert run.step_run("two").state is StepState.REJECTED
    assert len(h.model.prompts) == 1, "the second call was never made"


async def test_a_budget_that_fits_both_admits_both() -> None:
    h = two_steps()
    run = await h.start(Limits(currency={"usd": ESTIMATE + USED * 1.5}))
    assert run.state is RunState.FINISHED
    assert len(h.model.prompts) == 2


async def test_the_money_is_derived_from_the_recorded_tokens_never_stored_on_the_step() -> None:
    h = two_steps()
    run = await h.start(Limits(currency={"usd": 1.0}))
    for step in ("one", "two"):
        used = run.step_run(step).consumption
        assert used is not None and used.currency is None, "the step stores no money"
    tokens, unattributed = run.tokens_without_money()
    assert unattributed == ()
    assert tokens is not None and tokens["fake-model@1"].input == 22
    assert tokens["fake-model@1"].output == 16


async def test_the_cost_report_and_admission_give_the_same_figure() -> None:
    h = two_steps()
    run = await h.start(Limits(currency={"usd": 1.0}))
    tokens, _ = run.tokens_without_money()
    held, missing = budgeting.with_token_money(run.consumed(), tokens, TABLE)
    assert missing == ()
    assert held.currency is not None
    assert held.currency["usd"] == pytest.approx(2 * USED)
    assert tokens is not None
    assert held.currency["usd"] == price(tokens, TABLE).amount, "what `taktusctl cost` prices"


async def test_money_a_step_reported_itself_is_not_priced_a_second_time() -> None:
    h = two_steps()
    run = await h.start(Limits(currency={"usd": 1.0}))
    one = run.step_run("one")
    assert one.consumption is not None
    reported: Any = one.consumption.model_copy(update={"currency": {"usd": 0.5}})
    steps = tuple(
        s.model_copy(update={"consumption": reported}) if s.step_id == "one" else s
        for s in run.step_runs
    )
    run = run.model_copy(update={"step_runs": steps})
    tokens, _ = run.tokens_without_money()
    assert tokens is not None and tokens["fake-model@1"].input == 11, "only step two's tokens"
    held, _ = budgeting_held(run)
    assert held == pytest.approx(0.5 + USED)


def budgeting_held(run: Run) -> tuple[float, tuple[str, ...]]:
    tokens, _ = run.tokens_without_money()
    held, missing = budgeting.with_token_money(run.consumed(), tokens, TABLE)
    return (held.currency or {}).get("usd", 0.0), missing
