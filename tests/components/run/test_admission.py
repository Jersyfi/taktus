"""Admission control as a table: demand against what remains, every applicable limit at once."""

from __future__ import annotations

import pytest

from taktus.components.run.domain.service.admission import admit, remaining
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import ConsumptionQuantities as Q

BUDGET = Limits(
    currency={"eur": 10.0},
    quota=QuotaLimit(units=100),
    compute=ComputeLimit(seconds=60, resource_class="cpu.small"),
)
NOTHING = Q()

CASES = [
    ("nothing demanded", Q(), NOTHING, True, []),
    ("compute fits", Q(compute_seconds=30, resource_class="cpu.small"), NOTHING, True, []),
    ("compute exactly fits", Q(compute_seconds=60, resource_class="cpu.small"), NOTHING, True, []),
    (
        "compute exceeds",
        Q(compute_seconds=61, resource_class="cpu.small"),
        NOTHING,
        False,
        ["61.0s of cpu.small needed, 60.000s left"],
    ),
    (
        "compute after use",
        Q(compute_seconds=30, resource_class="cpu.small"),
        Q(compute_seconds=40, resource_class="cpu.small"),
        False,
        ["30.0s of cpu.small needed, 20.000s left"],
    ),
    (
        "foreign class",
        Q(compute_seconds=1, resource_class="gpu.small"),
        NOTHING,
        False,
        ["covers 'cpu.small' only"],
    ),
    ("money fits", Q(currency={"eur": 9.99}), NOTHING, True, []),
    ("money exceeds", Q(currency={"eur": 10.01}), NOTHING, False, ["10.01 eur needed, 10.0 left"]),
    (
        "money after use",
        Q(currency={"eur": 5}),
        Q(currency={"eur": 6}),
        False,
        ["5.0 eur needed, 4.0 left"],
    ),
    ("currency not budgeted", Q(currency={"usd": 1000}), NOTHING, True, []),
    ("quota fits", Q(quota_units=100), NOTHING, True, []),
    (
        "quota exceeds",
        Q(quota_units=100.5),
        NOTHING,
        False,
        ["100.5 quota units needed, 100.0 left"],
    ),
    ("tokens are not limited", Q(tokens_in=10**9, tokens_out=10**9), NOTHING, True, []),
    (
        "every failing limit is named",
        Q(currency={"eur": 11}, quota_units=101, compute_seconds=61, resource_class="cpu.small"),
        NOTHING,
        False,
        ["11.0 eur needed", "101.0 quota units needed", "61.0s of cpu.small needed"],
    ),
]


@pytest.mark.parametrize(
    ("name", "demand", "used", "fits", "fragments"), CASES, ids=[c[0] for c in CASES]
)
def test_admission(name: str, demand: Q, used: Q, fits: bool, fragments: list[str]) -> None:
    verdict = admit(demand, remaining(BUDGET, used), BUDGET)
    assert verdict.fits is fits, verdict.findings
    assert len(verdict.findings) == len(fragments)
    for fragment, finding in zip(fragments, verdict.findings, strict=True):
        assert fragment in finding


def test_remaining_subtracts_what_was_used() -> None:
    left = remaining(
        BUDGET,
        Q(currency={"eur": 4}, quota_units=30, compute_seconds=15, resource_class="cpu.small"),
    )
    assert left is not None
    assert left.currency == {"eur": 6.0}
    assert left.quota is not None and left.quota.units == 70
    assert left.compute is not None and left.compute.seconds == 45


def test_an_exhausted_kind_disappears_and_an_exhausted_budget_is_none() -> None:
    left = remaining(BUDGET, Q(quota_units=100, compute_seconds=60, resource_class="cpu.small"))
    assert left is not None
    assert left.quota is None and left.compute is None and left.currency == {"eur": 10.0}
    only_compute = Limits(compute=ComputeLimit(seconds=1, resource_class="cpu.small"))
    assert remaining(only_compute, Q(compute_seconds=1, resource_class="cpu.small")) is None


def test_nothing_left_admits_nothing_that_is_limited() -> None:
    only_compute = Limits(compute=ComputeLimit(seconds=1, resource_class="cpu.small"))
    left = remaining(only_compute, Q(compute_seconds=1, resource_class="cpu.small"))
    assert not admit(Q(compute_seconds=0.001, resource_class="cpu.small"), left, only_compute).fits
    assert admit(Q(), left, only_compute).fits
