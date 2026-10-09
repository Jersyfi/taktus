"""Admission control (ADR-0005): does a step's reserved demand fit what remains of the budget?

Every applicable limit is checked at once: money per currency, tokens in and out, quota units,
compute seconds in the budget's resource class. A limit the budget does not set does not apply.
A demand in a resource class the budget does not name has no budget at all and does not fit.
The verdict lists every quantity that does not fit, so that the reason is complete rather than
the first one. What remains is the line the run is held to — the budget less the margin — less
what every step used and every running step reserved (`Run.consumed`).
"""

from __future__ import annotations

from taktus.ports.worker import ComputeLimit, LimitKind, Limits, QuotaLimit, TokenLimit
from taktus.shared.v1 import ConsumptionQuantities, Value


class Admission(Value):
    fits: bool
    findings: tuple[str, ...] = ()
    kinds: tuple[LimitKind, ...] = ()
    """The consumption kinds that did not fit, each once: what the block is booked by
    (`block.limit_account`)."""


def remaining(budget: Limits, consumed: ConsumptionQuantities) -> Limits | None:
    """The budget less what was used; None when nothing is left of any kind."""
    currency: dict[str, float] | None = None
    if budget.currency is not None:
        currency = {
            code: max(0.0, amount - (consumed.currency or {}).get(code, 0.0))
            for code, amount in budget.currency.items()
        }
    quota: QuotaLimit | None = None
    if budget.quota is not None:
        left = budget.quota.units - (consumed.quota_units or 0.0)
        quota = QuotaLimit(units=left) if left > 0 else None
    compute: ComputeLimit | None = None
    if budget.compute is not None:
        used = (
            consumed.compute_seconds
            if consumed.resource_class == budget.compute.resource_class
            else 0.0
        )
        left = budget.compute.seconds - (used or 0.0)
        compute = (
            ComputeLimit(seconds=left, resource_class=budget.compute.resource_class)
            if left > 0
            else None
        )
    tokens: TokenLimit | None = None
    if budget.tokens is not None:
        left_in = _left(budget.tokens.tokens_in, consumed.tokens_in)
        left_out = _left(budget.tokens.tokens_out, consumed.tokens_out)
        if left_in or left_out:
            tokens = TokenLimit.of(left_in or None, left_out or None)
    exhausted_currency = currency is not None and all(v <= 0 for v in currency.values())
    if (
        (currency is None or exhausted_currency)
        and quota is None
        and compute is None
        and tokens is None
    ):
        return None
    return Limits(
        currency=None if exhausted_currency else currency,
        quota=quota,
        compute=compute,
        tokens=tokens,
    )


def _left(limit: int | None, used: int | None) -> int | None:
    """What is left of a token limit; None where the budget sets none, 0 where none is left."""
    if limit is None:
        return None
    return max(0, limit - (used or 0))


def admit(demand: ConsumptionQuantities, left: Limits | None, budget: Limits) -> Admission:
    """Whether the demand fits within what is left."""
    findings: list[str] = []
    kinds: list[LimitKind] = []
    for code, amount in (demand.currency or {}).items():
        if budget.currency is None or code not in budget.currency:
            continue
        available = 0.0 if left is None or left.currency is None else left.currency.get(code, 0.0)
        if amount > available:
            findings.append(f"{amount} {code} needed, {available} left")
            kinds.append("currency")
    if demand.quota_units is not None and budget.quota is not None:
        available = 0.0 if left is None or left.quota is None else left.quota.units
        if demand.quota_units > available:
            findings.append(f"{demand.quota_units} quota units needed, {available} left")
            kinds.append("quota")
    if budget.tokens is not None:
        for name, limit, needed in (
            ("input", budget.tokens.tokens_in, demand.tokens_in),
            ("output", budget.tokens.tokens_out, demand.tokens_out),
        ):
            if limit is None or needed is None:
                continue
            tokens = None if left is None else left.tokens
            available = (
                0
                if tokens is None
                else (getattr(tokens, f"tokens_{'in' if name == 'input' else 'out'}") or 0)
            )
            if needed > available:
                findings.append(f"{needed} {name} tokens needed, {available} left")
                kinds.append("tokens")
    if demand.compute_seconds is not None and budget.compute is not None:
        if demand.resource_class != budget.compute.resource_class:
            findings.append(
                f"compute in {demand.resource_class!r} needed, the budget covers "
                f"{budget.compute.resource_class!r} only"
            )
            kinds.append("compute")
        else:
            available = 0.0 if left is None or left.compute is None else left.compute.seconds
            if demand.compute_seconds > available:
                findings.append(
                    f"{demand.compute_seconds}s of {demand.resource_class} needed, "
                    f"{available:.3f}s left"
                )
                kinds.append("compute")
    return Admission(fits=not findings, findings=tuple(findings), kinds=tuple(dict.fromkeys(kinds)))
