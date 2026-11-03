"""The Takt is measured, not charged (UC-8.5, ADR-0010, DEC-0131, DEC-0132): every run's
breakdown in Takte at the weighting table in force when it started, named by digest; the same
Takte recomputed from the ledger at another table on request; nothing the table does not weigh
counted as zero; "uncalibrated" beside every figure; and the tenant's rate over the window."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from fakes.guarded import NoWholeReads
from fakes.maturity import VERIFIED

from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driving.cli.cost_command import render, render_rate
from taktus.components.accounting.application.service import (
    CostOfRun,
    CostOfRunHandler,
    SpendHandler,
    SpendOfRun,
    TaktRate,
    TaktRateHandler,
    TaktRateOf,
)
from taktus.components.accounting.domain.service import TAKT, Meter, meter, weigh
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.settings import WEIGHTING_TABLES, weighting_table_in_force
from taktus.conformance.contracts import contracts_root
from taktus.ports.model import WeightingTable, price
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import LedgerEntry, PriceKinds

from ..run.test_engine import worker
from ..run.test_estimates import ISSUE, TABLE
from ..run.test_llm_steps import WORK, ModelHarness, llm

V0 = weighting_table_in_force()
CLASSES = {"fake-model@1": "medium"}
LIMITS = Limits(currency={"usd": 1.0}, compute=ComputeLimit(seconds=10, resource_class="cpu.small"))

PUBLISHED = {
    "0": "sha256:cd74c996463ada706c3dd5f781220318d476135d07aa10d9236bed34ba673abb",
}
"""The digest of every weighting table the repository published. A table is never changed once
used (ADR-0010): a test that fails here means a published table was edited — make a new
version instead."""


def weighed(h: ModelHarness, weights: WeightingTable | None = V0) -> ModelHarness:
    """The harness's engine, with the test price table and a weighting table in force."""
    h.engine = RunEngine(
        maturities=VERIFIED,
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
        options=EngineOptions(
            prices=TABLE.model_copy(update={"compute": {"cpu.small": 0.002}}),
            weights=weights,
            model_classes=CLASSES,
        ),
    )
    return h


def refine_and_do() -> ModelHarness:
    return ModelHarness(
        ISSUE, llm("refine", WORK, after=("issue",)), worker("do", after=("refine",))
    )


def by_hand(run: Run, table: WeightingTable, factor: float) -> float:
    """The Takte of the run at the table, computed by hand from what its steps recorded."""
    refine = run.step_run("refine").consumption
    do = run.step_run("do").consumption
    assert refine is not None and refine.tokens_by_model is not None
    assert do is not None and do.compute_seconds
    kinds = refine.tokens_by_model["fake-model@1"]
    tokens = sum(
        (getattr(kinds, kind) or 0) / table.unit_tokens * table.tokens[kind] * factor
        for kind in ("input", "output", "cache_read", "cache_write")
        if getattr(kinds, kind)
    )
    compute = do.compute_seconds / 60 * table.compute_per_minute["cpu.small"]
    return tokens + compute + table.steps["rule"]


def test_the_table_in_force_is_dec_0131s_version_0_and_never_changes() -> None:
    assert V0.version == "0" and not V0.calibrated
    assert V0.tokens == {"output": 1.0, "input": 0.25, "cache_write": 0.3, "cache_read": 0.025}
    assert V0.model_classes == {"small": 0.25, "medium": 1.0, "large": 4.0}
    assert V0.compute_per_minute == {
        "cpu.small": 0.1,
        "cpu.large": 0.4,
        "gpu.small": 2.0,
        "accelerator.large": 8.0,
    }
    assert V0.steps == {"rule": 0.01, "statistics": 0.01}
    assert V0.storage_per_mib == 0.001 and V0.rate_window_days == 30
    directory = contracts_root().joinpath(*WEIGHTING_TABLES)
    for path in sorted(directory.glob("*.json")):
        table = WeightingTable.model_validate(json.loads(path.read_text(encoding="utf-8")))
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        assert PUBLISHED.get(table.version) == digest, (
            f"{path.name}: a published table was changed, or a new one is not listed"
        )


async def test_a_run_is_weighed_at_the_table_in_force_when_it_started() -> None:
    h = weighed(refine_and_do())
    run = await h.start(LIMITS)
    assert run.state is RunState.FINISHED
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    assert cost.takt is not None
    assert cost.takt.takte == pytest.approx(by_hand(run, V0, 1.0))
    assert cost.takt.table == "0" and cost.unweighed == ()
    assert cost.weights_digest is not None
    stored = await h.objects.get(cost.weights_digest)
    assert stored is not None
    assert WeightingTable.model_validate(json.loads(stored)) == V0, "named by its digest"
    # The configuration changes; the run keeps the table it started at.
    weighed(h, V0.model_copy(update={"version": "later", "steps": {"rule": 99.0}}))
    again = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    assert again.takt == cost.takt


async def test_the_takte_stand_beside_the_money_and_say_uncalibrated() -> None:
    h = weighed(refine_and_do())
    run = await h.start(LIMITS)
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    shown = render(cost).splitlines()
    priced = next(i for i, line in enumerate(shown) if line.startswith("priced"))
    takt = shown[priced + 1]
    assert takt.startswith("takt ") and "Takte at weighting table 0, uncalibrated" in takt
    document = cost.document()
    assert document["takt"]["calibration"] == "uncalibrated", "and in --json"
    assert document["priced"]["amount"] > 0


async def test_another_table_recomputes_the_takte_from_the_ledger() -> None:
    h = weighed(refine_and_do())
    run = await h.start(LIMITS)
    other = V0.model_copy(
        update={
            "version": "compare",
            "calibrated": True,
            "tokens": {k: v * 2 for k, v in V0.tokens.items()},
            "compute_per_minute": {"cpu.small": 0.2},
            "steps": {"rule": 0.02},
        }
    )
    handler = CostOfRunHandler(h.ledger, h.objects, h.persistence)
    own = await handler.execute(CostOfRun(run.id, "t"))
    compared = await handler.execute(CostOfRun(run.id, "t", weights=other))
    assert own.takt is not None and compared.takt is not None
    assert compared.takt.takte == pytest.approx(2 * own.takt.takte)
    assert compared.takt.calibration == "calibrated" and compared.weights_digest is None
    large = await handler.execute(CostOfRun(run.id, "t", model_classes={"fake-model@1": "large"}))
    assert large.takt is not None and large.takt.tokens == pytest.approx(4 * own.takt.tokens)


async def test_what_the_table_does_not_weigh_is_named_never_counted_as_zero() -> None:
    h = weighed(refine_and_do())
    run = await h.start(LIMITS)
    narrow = V0.model_copy(update={"version": "narrow", "compute_per_minute": {"gpu.small": 2.0}})
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t", weights=narrow, model_classes={})
    )
    assert cost.takt is not None
    assert cost.takt.takte == pytest.approx(0.01), "only the rule step is weighed"
    assert any("fake-model@1: the model is in no class" in u for u in cost.unweighed)
    assert any("compute cpu.small" in u for u in cost.unweighed)
    shown = render(cost)
    assert "unweighed" in shown and "the model is in no class" in shown


def test_a_meter_names_every_quantity_its_table_leaves_out() -> None:
    used = Meter(
        tokens={"fake-model@1": PriceKinds(output=1000), "unknown@1": PriceKinds(input=10)},
        tokens_unattributed=7,
        compute_seconds={"cpu.small": 120.0},
        storage_bytes=2 * 1024 * 1024,
        steps={"rule": 3, "human": 1, "wait": 2, "llm": 1, "worker": 1},
    )
    takt = weigh(used, V0, {"fake-model@1": "small", "unknown@1": "huge"})
    assert takt.tokens == pytest.approx(1.0 * 0.25)
    assert takt.compute == pytest.approx(0.2)
    assert takt.steps == pytest.approx(0.03)
    assert takt.storage == pytest.approx(0.002)
    assert takt.takte == pytest.approx(0.25 + 0.2 + 0.03 + 0.002)
    assert takt.unweighed == (
        "10 token(s) of unknown@1: table 0 gives the class huge no factor",
        "7 token(s) recorded without the model that used them",
        "1 human step(s): table 0 gives the method no weight",
        "2 wait step(s): table 0 gives the method no weight",
    ), "an llm or worker step is weighed by what it used, not counted again"


def test_a_dated_model_is_priced_and_weighed_at_its_undated_entry() -> None:
    """A worker records the model as its agent named it, dated; the tables name it undated
    (#279). An entry for the dated name wins; a name that differs otherwise is not matched."""
    dated = "fake-model-20251001"
    table = TABLE.model_copy(
        update={"prices": {"fake-model": {"input": 1.0, "output": 5.0, "cache_read": 0.1}}}
    )
    tokens = {dated: PriceKinds(input=1_000_000, cache_read=2_000_000, output=100_000)}
    priced = price(tokens, table)
    assert priced.amount == pytest.approx(1.0 + 0.2 + 0.5) and priced.complete
    takt = weigh(Meter(tokens=tokens), V0, {"fake-model": "medium"})
    assert takt.tokens == pytest.approx(1000 * 0.25 + 2000 * 0.025 + 100 * 1.0)
    assert takt.unweighed == ()

    exact = table.model_copy(update={"prices": {**table.prices, dated: {"input": 2.0}}})
    assert price({dated: PriceKinds(input=1_000_000)}, exact).amount == pytest.approx(2.0)
    other = price({"fake-model-2": PriceKinds(input=1)}, table)
    assert other.unpriced == ("fake-model-2 input",)


async def test_a_run_started_without_a_table_says_its_takt_is_unknown() -> None:
    h = weighed(refine_and_do(), weights=None)
    run = await h.start(LIMITS)
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    assert cost.takt is None
    assert cost.unweighed == ("the run started without a weighting table in force",)


async def test_the_takt_rate_of_a_tenant_is_its_takte_per_hour_over_the_window() -> None:
    h = weighed(refine_and_do())
    first = await h.start(LIMITS)
    second = await h.start(LIMITS)
    assert first.state is second.state is RunState.FINISHED
    handler = CostOfRunHandler(h.ledger, h.objects, h.persistence)
    takte = 0.0
    for run in (first, second):
        cost = await handler.execute(CostOfRun(run.id, "t"))
        assert cost.takt is not None
        takte += cost.takt.takte
    rate = await TaktRateHandler(h.ledger, h.objects, h.persistence, h.clock, V0).execute(
        TaktRateOf("t")
    )
    assert rate.window_days == 30 and rate.runs == 2
    assert rate.takte == pytest.approx(takte)
    assert rate.per_hour == pytest.approx(takte / (30 * 24))
    assert rate.calibration == "uncalibrated" and rate.tables == ("0 (uncalibrated)",)
    shown = render_rate(rate)
    assert "Takte per hour, uncalibrated" in shown


async def test_a_run_without_a_table_is_named_in_the_rate_not_counted_as_zero() -> None:
    h = weighed(refine_and_do(), weights=None)
    run = await h.start(LIMITS)
    rate = await TaktRateHandler(h.ledger, h.objects, h.persistence, h.clock, V0).execute(
        TaktRateOf("t")
    )
    assert rate.runs == 1 and rate.takte == 0.0
    assert rate.unweighed == (f"run {run.id}: started without a weighting table in force",)


async def whole_ledger_rate(h: ModelHarness, handler: TaktRateHandler, days: int = 30) -> TaktRate:
    """The rate as it was computed from every entry of the ledger, before it was read by kind
    and time (ADR-0105 §9): the result the handler must equal."""
    until = h.clock.now()
    since = until - timedelta(days=days)
    by_run: dict[str, list[LedgerEntry]] = {}
    async with h.persistence.transaction("t"):
        for entry in await h.ledger.entries("t"):
            if entry.refs.run_id is not None:
                by_run.setdefault(entry.refs.run_id, []).append(entry)
    takte, runs = 0.0, 0
    for _, of_run in sorted(by_run.items()):
        inside = [e for e in of_run if e.kind == "step.finished" and since <= e.ts <= until]
        if not inside:
            continue
        runs += 1
        digests = [e.content_digest for e in of_run if e.kind == "budget.set"]
        reference = await handler._reference(
            next((d for d in reversed(digests) if d is not None), None)
        )
        table = await handler._table(reference)
        assert table is not None
        takte += weigh(meter(inside), table, reference.get("model_classes") or {}).takte
    return TaktRate.model_construct(runs=runs, takte=round(takte, 9))


async def test_the_rate_reads_the_window_not_the_ledger_and_equals_the_whole_ledgers() -> None:
    h = weighed(refine_and_do())
    await h.start(LIMITS)
    h.clock.current += timedelta(days=40)  # the first run's steps leave the window
    await h.start(LIMITS)
    await h.start(LIMITS)
    guard = NoWholeReads(h.ledger)
    handler = TaktRateHandler(guard, h.objects, h.persistence, h.clock, V0)  # type: ignore[arg-type]
    rate = await handler.execute(TaktRateOf("t"))
    expected = await whole_ledger_rate(h, handler)
    assert rate.runs == expected.runs == 2
    assert rate.takte == pytest.approx(expected.takte) and rate.takte > 0


@pytest.mark.parametrize("window", [30, 40])
async def test_the_rate_over_days_equals_the_whole_ledgers_and_the_rebuilt_projection(
    window: int,
) -> None:
    """Runs on many days, the window starting inside a day: the whole days come from the
    projection, the two partial days from the entries, a window longer than the projection keeps
    from the entries alone. Each equals the rate computed from every entry, and the stored
    projection equals the one rebuilt from the ledger (ADR-0105 §3, §9)."""
    h = weighed(refine_and_do())
    weights = V0.model_copy(update={"rate_window_days": window})
    start = h.clock.current
    for hours in (0, 3, 20, 24 * 3 + 5, 24 * 29 + 22, 24 * 31 + 1, 24 * 35, 24 * 50 + 2):
        h.clock.current = start + timedelta(hours=hours)
        await h.start(LIMITS)
        await h.start(LIMITS)
    h.clock.current = start + timedelta(days=50, hours=9, minutes=30)
    guard = NoWholeReads(h.ledger)
    handler = TaktRateHandler(guard, h.objects, h.persistence, h.clock, weights)  # type: ignore[arg-type]
    rate = await handler.execute(TaktRateOf("t"))
    expected = await whole_ledger_rate(h, handler, window)
    assert rate.runs == expected.runs and rate.runs > 2
    assert rate.takte == pytest.approx(expected.takte) and rate.takte > 0
    async with h.persistence.transaction("t"):
        stored = await h.ledger.project("t", TAKT)
        rebuilt = await h.ledger.rebuilt("t", TAKT)
    assert stored == rebuilt
    again = await handler.execute(TaktRateOf("t"))
    assert again.takte == rate.takte and again.runs == rate.runs


async def test_the_takte_of_each_step_add_up_to_the_run_s() -> None:
    """#449: the spend per step carries each step's Takte at the run's own weighting table, and
    the steps' Takte together are the run's, with the word beside them."""
    h = weighed(refine_and_do())
    run = await h.start(LIMITS)
    cost = await CostOfRunHandler(h.ledger, h.objects, h.persistence).execute(
        CostOfRun(run.id, "t")
    )
    spend = await SpendHandler(h.ledger, h.objects, h.persistence).of_run(SpendOfRun(run.id, "t"))
    assert cost.takt is not None
    assert all(step.takte is not None for step in spend.steps)
    assert spend.takte == pytest.approx(cost.takt.takte)
    assert spend.calibration == cost.takt.calibration
