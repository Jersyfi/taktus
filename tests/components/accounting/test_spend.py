"""Where a process spends, per step, and two runs side by side (#449, DEC-0200 answer 3).

The ledger records, per step, plain input, cache writes, cache reads, output tokens, turns and,
where a compression ran, the input before and after it. From those records a run's spend is
shown per step at its own price table, a process's over a window, and two runs of the same task
side by side, figures and results.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from taktus.adapters.driving.cli.cost_command import render_comparison, render_spend
from taktus.components.accounting.application.service import (
    CompareRuns,
    SpendHandler,
    SpendOfProcess,
    SpendOfRun,
)
from taktus.components.accounting.domain.service.metering import meter_by_step
from taktus.ports.worker import Limits
from taktus.shared.v1 import Compression, Consumption, LedgerEntry

from ..run.test_estimates import ISSUE, priced
from ..run.test_llm_steps import WORK, ModelHarness, llm


def finished(step: str, consumption: Consumption, seq: int = 1) -> LedgerEntry:
    return LedgerEntry.model_validate(
        {
            "seq": seq,
            "ts": datetime(2026, 10, 28, tzinfo=UTC) + timedelta(seconds=seq),
            "kind": "step.finished",
            "prev_hash": None,
            "hash": "sha256:" + "0" * 64,
            "refs": {"tenant": "t", "run_id": "run_1", "step_id": step},
            "method": "worker",
            "consumption": consumption.document(),
            "outcome": "succeeded",
        }
    )


def test_the_meter_of_a_step_keeps_its_price_kinds_turns_and_compression_apart() -> None:
    first = Consumption(
        tokens_by_model={"m@1": {"input": 10, "cache_read": 900, "cache_write": 90, "output": 5}},
        turns=3,
        compression=Compression(before=1500, after=1000),
    )
    again = Consumption(
        tokens_by_model={"m@1": {"input": 4, "output": 2}},
        turns=1,
        compression=Compression(before=100, after=60),
    )
    other = Consumption(tokens_by_model={"m@1": {"input": 7}})
    by_step = meter_by_step(
        [finished("code", first, 1), finished("code", again, 2), finished("check", other, 3)]
    )
    assert list(by_step) == ["code", "check"]
    code = by_step["code"]
    kinds = code.tokens["m@1"]
    assert (kinds.input, kinds.cache_read, kinds.cache_write, kinds.output) == (14, 900, 90, 7)
    assert code.turns == 4
    assert code.compression == Compression(before=1600, after=1060)
    assert code.compression.saved == 540
    assert by_step["check"].turns == 0 and by_step["check"].compression is None


def test_turns_alone_are_no_consumption() -> None:
    with pytest.raises(ValueError, match="at least one quantity"):
        Consumption(turns=3)


async def test_a_run_shows_its_spend_per_step_at_its_own_table() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    run = await h.start(Limits(currency={"usd": 1.0}))
    spend = await SpendHandler(h.ledger, h.objects, h.persistence).of_run(SpendOfRun(run.id, "t"))
    assert [s.step_id for s in spend.steps] == ["issue", "refine"]
    refine = next(s for s in spend.steps if s.step_id == "refine")
    used = run.step_run("refine").consumption
    assert used is not None
    expected = (used.tokens_in or 0) * 3.0 / 1e6 + (used.tokens_out or 0) * 15.0 / 1e6
    assert refine.amount == pytest.approx(expected)
    assert refine.method == "llm" and refine.outcome == "succeeded"
    assert spend.amount == pytest.approx(expected), "the rule step costs nothing at the table"
    assert spend.table == "test-1" and spend.currency == "usd"
    shown = render_spend(spend)
    assert "refine" in shown and "test-1" in shown


async def test_two_runs_of_the_same_task_are_shown_side_by_side() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    one = await h.start(Limits(currency={"usd": 1.0}))
    two = await h.start(Limits(currency={"usd": 1.0}))
    handler = SpendHandler(h.ledger, h.objects, h.persistence)
    compared = await handler.compare(CompareRuns(one.id, two.id, "t"))
    assert compared.comparable == (), "the same process at the same table"
    assert compared.left.run_id == one.id and compared.right.run_id == two.id
    refine = next(d for d in compared.steps if d.step_id == "refine")
    assert refine.amount == pytest.approx(0.0) and refine.turns == 0
    assert compared.amount == pytest.approx(0.0)
    shown = render_comparison(compared)
    assert one.id in shown and two.id in shown and "refine" in shown


async def test_a_process_shows_its_spend_per_step_over_a_window() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    one = await h.start(Limits(currency={"usd": 1.0}))
    await h.start(Limits(currency={"usd": 1.0}))
    handler = SpendHandler(h.ledger, h.objects, h.persistence)
    process = (one.process_version or "").partition("@")[0]
    spend = await handler.of_process(SpendOfProcess(process, "t"))
    assert spend.runs == 2
    refine = next(s for s in spend.steps if s.step_id == "refine")
    assert refine.finished == 2
    single = await handler.of_run(SpendOfRun(one.id, "t"))
    assert spend.amounts["usd"] == pytest.approx(2 * (single.amount or 0))
    empty = await handler.of_process(
        SpendOfProcess(process, "t", since=datetime(2999, 1, 1, tzinfo=UTC))
    )
    assert empty.runs == 0 and empty.steps == ()
