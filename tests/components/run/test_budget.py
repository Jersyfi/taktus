"""The budget's rules as tables (ADR-0005, second and third amendment): the line a run is held
to, the scale calibration earns an adapter, the reservation, the worker's ceiling, and what a
budget can promise for each billing basis. No I/O; every rule is a function of values."""

from __future__ import annotations

import pytest

from taktus.components.run.domain.service import budget as b
from taktus.ports.model import Calculability
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit, TokenLimit
from taktus.shared.v1 import ConsumptionQuantities as Q
from taktus.shared.v1 import Method, PriceKinds


def observation(estimate: Q, actual: Q, adapter: str = "worker.a") -> b.Observation:
    return b.Observation(adapter=adapter, method=Method.WORKER, estimate=estimate, actual=actual)


def declared(**changes: object) -> Calculability:
    base: dict[str, object] = {
        "input_count": "exact",
        "output_cap": "hard",
        "usage_kinds": ("input", "output"),
        "billing": "per_token",
    }
    return Calculability.model_validate({**base, **changes})


def test_the_line_is_the_budget_less_the_margin() -> None:
    budget = Limits(
        currency={"usd": 5.0},
        quota=QuotaLimit(units=200),
        compute=ComputeLimit(seconds=100, resource_class="cpu.small"),
        tokens=TokenLimit.of(1000, 100),
    )
    line = b.held(budget, 0.10)
    assert line.currency == {"usd": 4.5}
    assert line.quota is not None and line.quota.units == 180
    assert line.compute is not None and line.compute.seconds == 90
    assert line.tokens is not None and (line.tokens.tokens_in, line.tokens.tokens_out) == (900, 90)
    assert b.held(budget, 0.0) == budget


@pytest.mark.parametrize(
    ("estimated", "used", "factor"),
    [
        (100, 250, 2.5),  # underestimated: the worst ratio is the scale
        (100, 40, None),  # overestimated: never reserved below the estimate
        (100, 100, None),  # right: the estimate as given
    ],
)
def test_calibration_scales_up_never_down(estimated: int, used: int, factor: float | None) -> None:
    scale = b.factors([observation(Q(tokens_in=estimated), Q(tokens_in=used))])
    assert scale.get("tokens_in", 1.0) == (factor or 1.0)


def test_the_scale_is_the_worst_of_the_recent_window() -> None:
    old = [observation(Q(tokens_in=10), Q(tokens_in=100))]  # ratio 10, outside the window
    recent = [observation(Q(tokens_in=10), Q(tokens_in=20)) for _ in range(b.WINDOW)]
    assert b.factors(old + recent)["tokens_in"] == 2.0


def test_the_first_run_seed_reserves_what_the_coding_worker_actually_used() -> None:
    scale, source = b.scale_for(
        "worker.endpoint",
        Method.WORKER,
        ("code.read", "code.edit", "code.test", "shell.sandboxed"),
        observed=[],
    )
    assert "first-run" in source
    reservation = b.reserve(Q(tokens_in=60_000, tokens_out=6_000, currency={"usd": 1.0}), scale)
    assert reservation.tokens_in == 257_289, "the largest input of the eight attempts"
    assert reservation.tokens_out == 6_667, "overestimated: only the margin of eight observations"
    assert reservation.currency == {"usd": pytest.approx(10 / 9)}, "attempt 4 would have fitted"


def test_own_observations_replace_the_seed_and_other_capabilities_get_none() -> None:
    own = [observation(Q(tokens_in=100), Q(tokens_in=150), adapter="worker.endpoint")]
    capabilities = ("code.read", "code.edit", "code.test", "shell.sandboxed")
    scale, source = b.scale_for("worker.endpoint", Method.WORKER, capabilities, own)
    assert scale["tokens_in"] == 1.5 and "worker.endpoint" in source
    scale, source = b.scale_for("worker.script", Method.WORKER, ("shell.script",), [])
    assert scale["compute_seconds"] == 2.0 and "DEC-0034" in source, "uncalibrated: twice"
    scale, source = b.scale_for("connector.repo", Method.RULE, (), [])
    assert scale == {} and "bound" in source, "a declared demand is taken as given"


def test_an_uncalibrated_worker_reserves_twice_its_estimate_and_history_narrows_it() -> None:
    """DEC-0034: caution towards the unknown, loosening through data."""
    estimate = Q(
        tokens_in=1000, currency={"eur": 0.5}, compute_seconds=4, resource_class="cpu.small"
    )
    scale, _ = b.scale_for("worker.new", Method.WORKER, ("shell.script",), [])
    reservation = b.reserve(estimate, scale)
    assert reservation.tokens_in == 2000 and reservation.compute_seconds == 8
    assert reservation.currency == {"eur": 1.0}
    c = "cpu.small"

    def seen(times: int, used: float) -> list[b.Observation]:
        return [
            observation(
                Q(compute_seconds=4, resource_class=c),
                Q(compute_seconds=used, resource_class=c),
                adapter="worker.new",
            )
            for _ in range(times)
        ]

    narrowed = [
        b.reserve(estimate, b.scale_for("worker.new", Method.WORKER, (), seen(n, 4.0))[0])
        for n in (1, 3, 9)
    ]
    assert [r.compute_seconds for r in narrowed] == [6.0, 5.0, 4.4], "half, a quarter, a tenth"
    worse = b.scale_for("worker.new", Method.WORKER, (), seen(9, 8.0))[0]
    assert b.reserve(estimate, worse).compute_seconds == 8.0, "a larger measured error wins"
    floor = b.scale_for("worker.new", Method.WORKER, (), seen(19, 4.0))[0]
    assert b.reserve(estimate, floor).compute_seconds == 4.4, "never below 10 % (DEC-0043)"
    none = b.scale_for("worker.new", Method.WORKER, (), seen(19, 4.0), uncalibrated_margin=0.0)[0]
    assert b.reserve(estimate, none).compute_seconds == 4.0, "an operator's zero is a limit too"


def test_a_workers_history_resets_when_its_model_version_changes() -> None:
    """DEC-0043: a calibration for one model says nothing about the next."""

    def made_with(model: str, used: int) -> b.Observation:
        kinds = PriceKinds(input=used, output=10)
        return observation(
            Q(tokens_in=1000),
            Q(tokens_in=used, tokens_by_model={model: kinds}),
            adapter="worker.coding",
        )

    old = [made_with("model-a-1", 1000) for _ in range(9)]
    estimate = Q(tokens_in=1000)
    calibrated, _ = b.scale_for("worker.coding", Method.WORKER, (), old)
    assert b.reserve(estimate, calibrated).tokens_in == 1100, "nine observations: the floor"
    one_new = [*old, made_with("model-a-2", 1000)]
    reset, source = b.scale_for("worker.coding", Method.WORKER, (), one_new)
    assert b.reserve(estimate, reset).tokens_in == 1500, "one observation of the new version"
    assert "current model" in source
    named = b.scale_for("worker.coding", Method.WORKER, (), old, models=frozenset({"model-b-1"}))
    assert b.reserve(estimate, named[0]).tokens_in == 2000, "an estimate naming a new model"
    unnamed = [*old, observation(Q(tokens_in=1000), Q(tokens_in=1000), adapter="worker.coding")]
    kept = b.scale_for("worker.coding", Method.WORKER, (), unnamed)[0]
    assert b.reserve(estimate, kept).tokens_in == 1100, "naming no model is no change"


def test_the_ceiling_is_the_reservation_and_never_more_than_is_left() -> None:
    budget = Limits(compute=ComputeLimit(seconds=100, resource_class="cpu.small"))
    left = Limits(compute=ComputeLimit(seconds=30, resource_class="cpu.small"))
    small = b.ceiling(Q(compute_seconds=12, resource_class="cpu.small"), left, budget)
    large = b.ceiling(Q(compute_seconds=50, resource_class="cpu.small"), left, budget)
    assert small.compute is not None and small.compute.seconds == 12
    assert large.compute is not None and large.compute.seconds == 30


@pytest.mark.parametrize(
    ("declaration", "priced", "how"),
    [
        (declared(), True, b.HELD),
        (declared(billing="per_window"), True, b.WINDOW_SHARE),
        (declared(billing="per_hardware_time"), True, b.COMPUTE_TIME),
        (declared(), False, b.UNPRICED),
        (declared(input_count="estimate"), True, b.ESTIMATE),
        (declared(output_cap="soft"), True, b.ESTIMATE),
        (declared(input_count="upper_bound"), True, b.HELD),
    ],
)
def test_a_currency_budget_promises_what_the_provider_permits(
    declaration: Calculability, priced: bool, how: str
) -> None:
    (promise,) = b.promise(Limits(currency={"usd": 1.0}), [("model.a", declaration, priced)], [])
    assert promise.kind == "currency" and promise.how == how
    assert promise.reason


def test_a_window_share_is_said_plainly_where_the_budget_is_set() -> None:
    (promise,) = b.promise(
        Limits(currency={"usd": 1.0}), [("model.a", declared(billing="per_window"), True)], []
    )
    assert "cannot be enforced" in promise.reason and "share of the window" in promise.reason


def test_money_reported_per_assignment_is_held_as_an_estimate() -> None:
    (promise,) = b.promise(Limits(currency={"usd": 1.0}), [], ["the worker step(s) implement"])
    assert promise.how == b.ESTIMATE and "one inner step" in promise.reason


def test_the_margin_absorbs_an_overrun_and_nothing_beyond_it() -> None:
    reservation = Q(compute_seconds=9.0, resource_class="cpu.small", currency={"usd": 0.9})
    grown = b.grow(reservation, 0.10)
    assert grown.compute_seconds == pytest.approx(10.0)
    assert grown.currency == {"usd": pytest.approx(1.0)}
    assert b.grow(reservation, 0.0) == reservation, "no margin: the reservation is the ceiling"
    budget = Limits(compute=ComputeLimit(seconds=9.5, resource_class="cpu.small"))
    capped = b.ceiling(grown, budget, budget)
    assert capped.compute is not None and capped.compute.seconds == 9.5, "never past the budget"
