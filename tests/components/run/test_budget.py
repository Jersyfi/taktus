"""The budget's rules as tables (ADR-0005, second and third amendment): the line a run is held
to, the scale calibration earns an adapter, the reservation, the worker's ceiling, and what a
budget can promise for each billing basis. No I/O; every rule is a function of values."""

from __future__ import annotations

import pytest

from taktus.components.run.domain.service import budget as b
from taktus.ports.model import Calculability
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit, TokenLimit
from taktus.shared.v1 import ConsumptionQuantities as Q
from taktus.shared.v1 import Method


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
    assert reservation.tokens_out == 6_000, "the output was overestimated; it stays as given"
    assert reservation.currency == {"usd": pytest.approx(1.078)}, "attempt 4 would have fitted"


def test_own_observations_replace_the_seed_and_other_capabilities_get_none() -> None:
    own = [observation(Q(tokens_in=100), Q(tokens_in=150), adapter="worker.endpoint")]
    capabilities = ("code.read", "code.edit", "code.test", "shell.sandboxed")
    scale, source = b.scale_for("worker.endpoint", Method.WORKER, capabilities, own)
    assert scale == {"tokens_in": 1.5} and "worker.endpoint" in source
    scale, source = b.scale_for("worker.script", Method.WORKER, ("shell.script",), [])
    assert scale == {} and "as given" in source


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
