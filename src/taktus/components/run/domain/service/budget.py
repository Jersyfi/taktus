"""A budget is a budget (ADR-0005, second and third amendment): the rules, without I/O.

Four things are decided here, each a function of values the caller observed.

**The line the run is held to.** A named safety margin is subtracted from every limit before
the first step is admitted (`held`). The budget, the margin and the line are all stated.

**What a step reserves.** Admission debits the estimate, scaled by the measured error of the
adapter that gave it (`reserve`). The scale is a statistic over pairs of estimate and actual —
the ledger's `step.admitted` and `step.finished` entries of the same adapter and method — and
for a worker nothing has measured yet, a seed: the first live run (`SEED`). A worker that
underestimates earns a larger reservation automatically; one that overestimates keeps its own
figure, never less (`factors`).

**What a budget can promise.** A budget in a currency is only as strong as the provider allows
(principle 8). `promise` derives, from the model adapters' declarations, the price table and the
workers' consumption kinds, how each limited kind is held — exactly per step, as an estimate,
only as a share of a time window, or not at all — and the run records that statement when its
budget is set, not afterwards.

**Where a worker must stop.** The reservation, grown by the run's margin, is the worker's hard
ceiling (`grow`, `ceiling`), and never more than what is left of the whole budget: the worker
halts at its next boundary when its running total would cross it (W-14). The margin is what
absorbs a step that overruns its estimate; with no margin the ceiling is the reservation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from taktus.ports.model import Calculability
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit, TokenLimit
from taktus.shared.v1 import ConsumptionQuantities, Method, Value

WINDOW = 20
"""How many of an adapter's most recent observations its scale is computed over."""


# --- the held line --------------------------------------------------------------------------


def held(budget: Limits, margin: float) -> Limits:
    """Every limit less the margin: the line admission holds the run to."""
    keep = 1.0 - margin
    return Limits(
        currency=None
        if budget.currency is None
        else {code: amount * keep for code, amount in budget.currency.items()},
        quota=None if budget.quota is None else QuotaLimit(units=budget.quota.units * keep),
        compute=None
        if budget.compute is None
        else ComputeLimit(
            seconds=budget.compute.seconds * keep, resource_class=budget.compute.resource_class
        ),
        tokens=None
        if budget.tokens is None
        else TokenLimit.of(
            _floor(budget.tokens.tokens_in, keep), _floor(budget.tokens.tokens_out, keep)
        ),
    )


def _floor(value: int | None, keep: float) -> int | None:
    return None if value is None else max(1, math.floor(value * keep))


# --- calibration ----------------------------------------------------------------------------


class Observation(Value):
    """One step's estimate beside what it actually used, for one adapter and method."""

    adapter: str
    method: Method
    estimate: ConsumptionQuantities
    actual: ConsumptionQuantities


SCALED = ("tokens_in", "tokens_out", "quota_units", "compute_seconds")
"""The scalar quantities a reservation scales; currency is scaled per code."""


def factors(observations: Sequence[Observation], window: int = WINDOW) -> dict[str, float]:
    """Per quantity, the largest ratio of actual to estimate over the last `window`
    observations, and never below 1: an adapter is reserved at least what it estimates, and as
    much more as it has underestimated at worst. A quantity nobody estimated has no factor."""
    ratios: dict[str, float] = {}
    for observation in list(observations)[-window:]:
        for name, estimated, used in _pairs(observation.estimate, observation.actual):
            if estimated > 0:
                ratios[name] = max(ratios.get(name, 1.0), used / estimated)
    return ratios


def _pairs(
    estimate: ConsumptionQuantities, actual: ConsumptionQuantities
) -> Iterable[tuple[str, float, float]]:
    for name in SCALED:
        estimated = getattr(estimate, name)
        if estimated is not None:
            yield name, float(estimated), float(getattr(actual, name) or 0)
    for code, amount in (estimate.currency or {}).items():
        yield f"currency.{code}", amount, (actual.currency or {}).get(code, 0.0)


def reserve(estimate: ConsumptionQuantities, scale: Mapping[str, float]) -> ConsumptionQuantities:
    """The estimate scaled by the adapter's factors: what admission debits for the step."""
    scaled: dict[str, object] = {}
    for name in SCALED:
        value = getattr(estimate, name)
        if value is None:
            continue
        factor = scale.get(name, 1.0)
        scaled[name] = math.ceil(value * factor) if isinstance(value, int) else value * factor
    if estimate.currency:
        scaled["currency"] = {
            code: amount * scale.get(f"currency.{code}", scale.get("currency.*", 1.0))
            for code, amount in estimate.currency.items()
        }
    if estimate.resource_class is not None:
        scaled["resource_class"] = estimate.resource_class
    if estimate.tokens_by_model:
        scaled["tokens_by_model"] = estimate.tokens_by_model
    return ConsumptionQuantities.model_validate(scaled)


@dataclass(frozen=True)
class Seed:
    """Observations measured before this instance measured any: a prior for every adapter that
    serves the same capabilities by the same method, until it has observations of its own."""

    method: Method
    capabilities: frozenset[str]
    observations: tuple[Observation, ...]
    source: str


def _first_run() -> Seed:
    """The eight attempts of P-03 `implement` on 2026-09-23 (docs/runs/first-run.md §2): the
    coding worker estimated the same configured constant every time and used this."""
    estimate = ConsumptionQuantities(tokens_in=60_000, tokens_out=6_000, currency={"usd": 1.00})
    actuals = (
        (116_902, 106, 0.449),
        (161_491, 122, 0.567),
        (110_531, 84, 0.833),
        (247_401, 192, 1.078),
        (148_015, 128, 0.789),
        (257_289, 195, 0.736),
        (219_773, 157, 0.875),
        (206_393, 170, 0.766),
    )
    return Seed(
        method=Method.WORKER,
        capabilities=frozenset({"code.read", "code.edit", "code.test", "shell.sandboxed"}),
        observations=tuple(
            Observation(
                adapter="first-run",
                method=Method.WORKER,
                estimate=estimate,
                actual=ConsumptionQuantities(
                    tokens_in=tokens_in, tokens_out=tokens_out, currency={"usd": usd}
                ),
            )
            for tokens_in, tokens_out, usd in actuals
        ),
        source="docs/runs/first-run.md §2, P-03 implement, eight attempts on 2026-09-23",
    )


SEED: tuple[Seed, ...] = (_first_run(),)
"""The seeds this version ships. A seed is evidence, not configuration: it changes only with a
measured run, recorded with its source."""


UNCALIBRATED_MARGIN = 1.0
"""What a worker nothing has measured yet reserves beyond its estimate: 100 %, twice the estimate
(DEC-0034). The only worker measured so far underestimated by a factor of two to four. Caution
towards the unknown, loosening through data: after n observations the margin is 1/(n+1) of this
— half after one, a tenth after nine, a twentieth over the full window — and a worker whose
measured error is larger reserves that instead."""


def scale_for(
    adapter: str,
    method: Method,
    capabilities: Iterable[str],
    observed: Sequence[Observation],
    seeds: Sequence[Seed] = SEED,
    uncalibrated_margin: float = UNCALIBRATED_MARGIN,
) -> tuple[dict[str, float], str]:
    """The factors for one adapter and method, and where they come from: the adapter's own
    observations when it has any, else a seed whose capabilities the step requires. A worker
    reserves at least its estimate plus the uncalibrated margin divided by one more than the
    observations it has, and its measured error where that is larger (DEC-0034). Any other
    method's estimate is a bound — a counted prompt, a declared demand — and takes no margin."""
    own = [o for o in observed if o.adapter == adapter and o.method is method]
    required = frozenset(capabilities)
    history, source = own, f"{len(own[-WINDOW:])} observation(s) of {adapter}"
    if not own:
        seed = next((x for x in seeds if x.method is method and x.capabilities <= required), None)
        history = [] if seed is None else list(seed.observations)
        source = "no observation yet" if seed is None else f"the seed from {seed.source}"
    if method is not Method.WORKER:
        return (factors(history), source) if history else ({}, "a bound, taken as given")
    # A worker's margin narrows with every observation: all of it with none, half with one, a
    # third with two — and never below what it has measured (DEC-0034).
    count = len(history[-WINDOW:])
    margin = uncalibrated_margin / (1 + count)
    scale = factors(history)
    for name in [*SCALED, "currency.*"]:
        scale[name] = max(scale.get(name, 1.0), 1.0 + margin)
    for name in [key for key in scale if key.startswith("currency.") and key != "currency.*"]:
        scale[name] = max(scale[name], 1.0 + margin)
    return scale, f"{source}: the measured error, or the estimate plus {margin:.0%} (DEC-0034)"


# --- the ceiling a worker is given ------------------------------------------------------------


def grow(reservation: ConsumptionQuantities, margin: float) -> ConsumptionQuantities:
    """The reservation with its share of the margin: what a step may use before its worker
    must halt. The margin is held back from the budget to absorb exactly this — a step that
    overruns its estimate — so a worker may use it, and nothing beyond it."""
    if margin <= 0:
        return reservation
    return reserve(reservation, {name: 1 / (1 - margin) for name in _factor_names(reservation)})


def _factor_names(quantities: ConsumptionQuantities) -> list[str]:
    names = [name for name in SCALED if getattr(quantities, name) is not None]
    return names + [f"currency.{code}" for code in quantities.currency or {}]


def ceiling(reservation: ConsumptionQuantities, left: Limits | None, budget: Limits) -> Limits:
    """What a worker may use: its reservation, for every kind the budget limits, and never
    more than what is left. The worker halts at its next boundary when its running total
    would cross it (W-14)."""
    currency = None
    if budget.currency is not None:
        currency = {
            code: min(
                (reservation.currency or {}).get(code, math.inf),
                math.inf if left is None or left.currency is None else left.currency.get(code, 0),
            )
            for code in budget.currency
        }
        currency = {code: value for code, value in currency.items() if math.isfinite(value)}
    quota = None
    if budget.quota is not None:
        units = min(
            reservation.quota_units if reservation.quota_units is not None else math.inf,
            math.inf if left is None or left.quota is None else left.quota.units,
        )
        quota = QuotaLimit(units=units) if math.isfinite(units) and units > 0 else None
    compute = None
    if budget.compute is not None:
        seconds = min(
            reservation.compute_seconds if reservation.compute_seconds is not None else math.inf,
            math.inf if left is None or left.compute is None else left.compute.seconds,
        )
        if math.isfinite(seconds) and seconds > 0:
            compute = ComputeLimit(seconds=seconds, resource_class=budget.compute.resource_class)
    tokens = None
    if budget.tokens is not None:
        left_tokens = None if left is None else left.tokens
        limit_in = _least(
            reservation.tokens_in, None if left_tokens is None else left_tokens.tokens_in
        )
        limit_out = _least(
            reservation.tokens_out, None if left_tokens is None else left_tokens.tokens_out
        )
        if limit_in or limit_out:
            tokens = TokenLimit.of(limit_in or None, limit_out or None)
    if not currency and quota is None and compute is None and tokens is None:
        return left if left is not None else budget
    return Limits(currency=currency or None, quota=quota, compute=compute, tokens=tokens)


def _least(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


# --- what a budget can promise ---------------------------------------------------------------


HELD = "held"
"""Exact at every step boundary: the demand is bounded before the step and measured after it."""
ESTIMATE = "estimate"
"""Held against an estimate: the actual may exceed it by one step's error, reported after."""
WINDOW_SHARE = "window_share"
"""Not enforceable in this kind: the provider bills a share of a time window, not per token."""
COMPUTE_TIME = "compute_time"
"""Not enforceable as money: the model runs on hardware whose cost is its time."""
UNPRICED = "unpriced"
"""Not enforceable as money: the price table has no price for the model."""


class Promise(Value):
    """How one limited kind of one budget is held, and why."""

    kind: str
    how: str
    reason: str


def promise(
    budget: Limits,
    models: Sequence[tuple[str, Calculability, bool]],
    currency_by_assignment: Sequence[str],
) -> tuple[Promise, ...]:
    """For every kind the budget limits: how it is held. `models` is every configured model
    as (adapter, its declaration, whether the price table prices it); `currency_by_assignment`
    names the workers that report money only when an assignment ends."""
    out: list[Promise] = []
    if budget.tokens is not None:
        worst = _weakest_count(models)
        out.append(
            Promise(
                kind="tokens",
                how=HELD if worst is None else ESTIMATE,
                reason="every model counts its input exactly or bounds it, and holds the output "
                "limit"
                if worst is None
                else worst,
            )
        )
    if budget.currency is not None:
        out.append(_currency(models, currency_by_assignment))
    if budget.quota is not None:
        out.append(
            Promise(
                kind="quota",
                how=HELD,
                reason="reported per step by workers, per call by "
                "connectors, and bounded before each by a declared demand",
            )
        )
    if budget.compute is not None:
        out.append(Promise(kind="compute", how=HELD, reason="reported per step"))
    return tuple(out)


def _weakest_count(models: Sequence[tuple[str, Calculability, bool]]) -> str | None:
    for adapter, calculability, _ in models:
        if calculability.input_count in ("estimate", "none"):
            return f"{adapter} can count its input only as {calculability.input_count}"
        if calculability.output_cap != "hard":
            return f"{adapter} declares its output limit {calculability.output_cap}"
    return None


def _currency(
    models: Sequence[tuple[str, Calculability, bool]], by_assignment: Sequence[str]
) -> Promise:
    for adapter, calculability, _ in models:
        if calculability.billing == "per_window":
            return Promise(
                kind="currency",
                how=WINDOW_SHARE,
                reason=f"{adapter} is billed as a share of a subscription's time window; money "
                "is not a function of its tokens, so a currency budget cannot be enforced for "
                "it — only a share of the window",
            )
    for adapter, calculability, _ in models:
        if calculability.billing == "per_hardware_time":
            return Promise(
                kind="currency",
                how=COMPUTE_TIME,
                reason=f"{adapter} runs on hardware whose cost is its time, not its tokens; hold "
                "it with a compute budget",
            )
    for adapter, _, priced in models:
        if not priced:
            return Promise(
                kind="currency",
                how=UNPRICED,
                reason=f"the price table has no price for {adapter}'s model, so its money cannot "
                "be computed before or after a step",
            )
    weak = _weakest_count(models)
    if weak is not None:
        return Promise(kind="currency", how=ESTIMATE, reason=weak)
    if by_assignment:
        return Promise(
            kind="currency",
            how=ESTIMATE,
            reason=", ".join(by_assignment)
            + " report money only when an assignment ends; within one the running total is "
            "their reservation, and the spend can exceed it by one inner step",
        )
    return Promise(
        kind="currency",
        how=HELD,
        reason="every model bounds its input and output before a step and is priced",
    )
