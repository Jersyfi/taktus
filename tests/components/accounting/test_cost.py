"""Money is computable from the ledger (ADR-0005 third amendment, ADR-0010): the tokens every
step recorded, per model and price kind, at the price table the run's budget statement names —
the same figure whatever the configuration says later, and nothing priced at zero that has no
price."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from taktus.components.accounting.application.service import CostOfRun, CostOfRunHandler
from taktus.components.accounting.domain.service import meter
from taktus.components.run.domain.model import RunState
from taktus.ports.model import PriceTable
from taktus.ports.worker import Limits, QuotaLimit

from ..run.test_estimates import ISSUE, TABLE, priced
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
