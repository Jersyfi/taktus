"""Metering: what a run used, from the ledger, in the breakdown every figure is computed from.

ADR-0010 asks that the Takt be recomputable from the ledger; ADR-0005 asks the same of money.
Both are functions of one breakdown, built once here: tokens per model and per price kind,
compute seconds per resource class, quota units, and steps per method. Money is that breakdown
at a price table (`ports/model.py`, `price`); the Takt will be the same breakdown at a
weighting table once its weights are decided (M4.3 of the Taktus anchors: the owner's). Pure:
ledger entries in, a meter out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import Field

from taktus.shared.v1 import LedgerEntry, PriceKinds, Value, add_tokens_by_model


class Meter(Value):
    """What was used, as recorded: the one breakdown money and the Takt are computed from."""

    tokens: Mapping[str, PriceKinds] = Field(default_factory=dict)
    """Per model, per price kind."""
    tokens_unattributed: int = 0
    """Input and output tokens recorded without a model: their money cannot be computed and is
    reported as such, never priced at zero."""
    compute_seconds: Mapping[str, float] = Field(default_factory=dict)
    """Per resource class."""
    quota_units: float = 0.0
    steps: Mapping[str, int] = Field(default_factory=dict)
    """Finished steps per method."""
    currency_reported: Mapping[str, float] = Field(default_factory=dict)
    """Money as the workers reported it, beside what the price table computes."""


def meter(entries: Iterable[LedgerEntry]) -> Meter:
    """The breakdown of every `step.finished` among the entries — what the steps actually used,
    never what was estimated or reserved for them."""
    tokens: dict[str, PriceKinds] | None = None
    unattributed = 0
    compute: dict[str, float] = {}
    quota = 0.0
    steps: dict[str, int] = {}
    money: dict[str, float] = {}
    for entry in entries:
        if entry.kind != "step.finished":
            continue
        if entry.method is not None:
            steps[str(entry.method)] = steps.get(str(entry.method), 0) + 1
        used = entry.consumption
        if used is None:
            continue
        if used.tokens_by_model:
            tokens = add_tokens_by_model(tokens, used.tokens_by_model)
        else:
            unattributed += (used.tokens_in or 0) + (used.tokens_out or 0)
        if used.compute_seconds is not None and used.resource_class is not None:
            compute[used.resource_class] = (
                compute.get(used.resource_class, 0.0) + used.compute_seconds
            )
        quota += used.quota_units or 0.0
        for code, amount in (used.currency or {}).items():
            money[code] = money.get(code, 0.0) + amount
    return Meter(
        tokens=tokens or {},
        tokens_unattributed=unattributed,
        compute_seconds=compute,
        quota_units=quota,
        steps=steps,
        currency_reported=money,
    )
