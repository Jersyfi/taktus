"""Money is computable from the ledger (ADR-0005 third amendment, ADR-0010): the tokens every
step recorded, per model and price kind, at the price table the run's budget statement names —
the same figure whatever the configuration says later, and nothing priced at zero that has no
price."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from taktus.adapters.driving.cli.cost_command import render
from taktus.components.accounting.application.service import CostOfRun, CostOfRunHandler
from taktus.components.accounting.domain.service import meter
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.model import PriceTable
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit

from ..run.test_engine import Harness, worker
from ..run.test_estimates import ISSUE, TABLE, margined, priced
from ..run.test_llm_steps import WORK, ModelHarness, llm


async def test_a_run_costs_what_its_tokens_cost_at_the_table_it_was_held_to() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    run = await h.start(Limits(currency={"usd": 1.0}))
    assert run.state is RunState.FINISHED
    handler = CostOfRunHandler(h.ledger, h.objects, h.persistence)
    cost = await handler.execute(CostOfRun(run.id, "t"))
    used = run.step_run("refine").consumption
    assert used is not None
    expected = (used.tokens_in or 0) * 3.0 / 1e6 + (used.tokens_out or 0) * 15.0 / 1e6
    assert cost.priced is not None and cost.priced.amount == pytest.approx(expected)
    assert cost.priced.table == "test-1" and cost.table_digest is not None
    assert cost.unpriced == ()
    assert cost.meter.steps == {"rule": 1, "llm": 1}


async def test_another_table_compares_and_a_missing_price_is_named_not_zero() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    run = await h.start(Limits(currency={"usd": 1.0}))
    other = PriceTable(
        version="other",
        valid_from=datetime(2026, 10, 1, tzinfo=UTC),
        currency="eur",
        unit_tokens=1000,
        source="a test",
        prices={"fake-model@1": {"input": 0.01}},
    )
    handler = CostOfRunHandler(h.ledger, h.objects, h.persistence)
    cost = await handler.execute(CostOfRun(run.id, "t", table=other))
    assert cost.priced is not None and cost.priced.currency == "eur"
    assert "no price for fake-model@1 output" in cost.unpriced


async def test_a_run_held_without_a_table_says_its_money_is_unknown() -> None:
    h = ModelHarness(ISSUE, llm("refine", WORK, after=("issue",)))
    run = await h.start(Limits(quota=QuotaLimit(units=10)))
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    assert cost.priced is None
    assert cost.unpriced == ("the run was held without a price table",)
    assert cost.meter.tokens, "the tokens are recorded all the same"


def test_the_meter_counts_what_was_used_never_what_was_reserved() -> None:
    assert meter([]).tokens == {} and meter([]).quota_units == 0.0
    assert TABLE.version == "test-1"


@pytest.mark.parametrize(
    ("uncalibrated_margin", "below"), [(0.0, True), (0.05, True), (0.1, False)]
)
async def test_the_cost_of_a_run_held_below_the_floor_says_so_beside_its_money(
    uncalibrated_margin: float, below: bool
) -> None:
    """`taktusctl cost` relies on the budget statement, so it says what the statement says: the
    run was held with an uncalibrated margin an operator set below the floor (DEC-0047)."""
    h = margined(Harness(worker("do")), uncalibrated_margin)
    run = await h.start()
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    shown = render(cost)
    if below:
        assert cost.below_floor is not None
        assert f"set to {uncalibrated_margin:g}, below the floor of 0.1" in cost.below_floor
        assert f"margin   {cost.below_floor}" in shown.splitlines()
        assert cost.document()["below_floor"] == cost.below_floor, "and in --json"
    else:
        assert cost.below_floor is None
        assert "margin" not in shown


# --- compute seconds are priced at the same table (#230) ------------------------------------

COMPUTE = TABLE.model_copy(update={"version": "test-compute", "compute": {"cpu.small": 0.002}})
"""The test table, and a price for a second of `cpu.small`: what the fake worker runs on."""

BOTH = Limits(currency={"usd": 1.0}, compute=ComputeLimit(seconds=10, resource_class="cpu.small"))

SECONDS = Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small"))
"""A budget in compute seconds alone: a currency budget refuses compute its table does not price
(ADR-0005, fourth amendment), so a run that used unpriced compute was held to none."""


def with_a_worker(table: PriceTable | None) -> ModelHarness:
    """A run that refines with a model and then does the work on a worker: tokens and compute."""
    return priced(
        ModelHarness(ISSUE, llm("refine", WORK, after=("issue",)), worker("do", after=("refine",))),
        table,
    )


def tokens_of(run: Run) -> float:
    """The refine step's tokens at the test table, computed by hand."""
    used = run.step_run("refine").consumption
    assert used is not None
    return (used.tokens_in or 0) * 3.0 / 1e6 + (used.tokens_out or 0) * 15.0 / 1e6


async def test_a_run_costs_its_tokens_plus_its_compute_seconds_at_the_table_it_was_held_to() -> (
    None
):
    h = with_a_worker(COMPUTE)
    run = await h.start(BOTH)
    assert run.state is RunState.FINISHED
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    do = run.step_run("do").consumption
    assert do is not None and do.compute_seconds
    tokens, compute = tokens_of(run), do.compute_seconds * 0.002
    assert cost.tokens_amount == pytest.approx(tokens)
    assert cost.compute_amount == pytest.approx(compute)
    assert cost.priced is not None and cost.priced.amount == pytest.approx(tokens + compute)
    assert cost.priced.table == "test-compute", "the table the budget statement names"
    assert cost.unpriced == ()
    assert f"compute {compute:.6f}" in render(cost)


async def test_compute_in_a_class_the_table_does_not_price_is_named_never_free() -> None:
    h = with_a_worker(TABLE.model_copy(update={"version": "gpu", "compute": {"gpu.large": 1.0}}))
    run = await h.start(SECONDS)
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    assert cost.compute_amount == 0.0
    assert cost.priced is not None and cost.priced.amount == pytest.approx(tokens_of(run))
    assert cost.unpriced == ("no price for compute cpu.small",)
    assert "compute cpu.small" in cost.priced.unpriced
    assert "unpriced no price for compute cpu.small" in render(cost).splitlines()


async def test_a_table_without_compute_gives_todays_amount_and_says_compute_was_not_priced() -> (
    None
):
    h = with_a_worker(TABLE)
    run = await h.start(SECONDS)
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    assert cost.priced is not None and cost.priced.amount == pytest.approx(tokens_of(run))
    assert cost.compute_amount == 0.0
    assert cost.unpriced == (
        "compute seconds were not priced: price table test-1 prices no compute (cpu.small)",
    )


async def test_compute_is_priced_at_the_statements_table_and_another_table_only_compares() -> None:
    """The run was held to a table without compute; a table given to compare prices its
    compute, and the run's own figure does not change (ADR-0010)."""
    h = with_a_worker(TABLE)
    run = await h.start(SECONDS)
    handler = CostOfRunHandler(h.ledger, h.objects, h.persistence)
    compared = await handler.execute(CostOfRun(run.id, "t", table=COMPUTE))
    own = await handler.execute(CostOfRun(run.id, "t"))
    assert compared.compute_amount and compared.unpriced == ()
    assert compared.table_digest is None, "a table to compare is not the run's"
    assert own.priced is not None and own.priced.table == "test-1"
    assert own.compute_amount == 0.0 and own.table_digest is not None


async def test_a_run_of_compute_alone_held_without_a_table_says_its_money_is_unknown() -> None:
    h = Harness(worker("do"))
    run = await h.start()
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    assert cost.meter.compute_seconds and cost.priced is None
    assert cost.unpriced == ("the run was held without a price table",)
