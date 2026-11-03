"""Metering: what a run used, from the ledger, in the breakdown every figure is computed from.

ADR-0010 asks that the Takt be recomputable from the ledger; ADR-0005 asks the same of money.
Both are functions of one breakdown, built once here: tokens per model and per price kind,
compute seconds per resource class, quota units, bytes of state written, and steps per method.
Money is that breakdown at a price table (`ports/model.py`, `price`); the Takt is the same
breakdown at a weighting table (`weighing`). Pure: ledger entries in, a meter out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import Field

from taktus.shared.v1 import Compression, LedgerEntry, PriceKinds, Value, add_tokens_by_model


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
    storage_bytes: int = 0
    """Bytes of state written."""
    steps: Mapping[str, int] = Field(default_factory=dict)
    """Finished steps per method."""
    currency_reported: Mapping[str, float] = Field(default_factory=dict)
    """Money as the workers reported it, beside what the price table computes."""
    turns: int = 0
    """The calls to a language model the agents made: where the tokens went (#449)."""
    compression: Compression | None = None
    """The input before and after, summed over the steps where a compression ran (#449)."""


def meter(entries: Iterable[LedgerEntry]) -> Meter:
    """The breakdown of every `step.finished` among the entries — what the steps actually used,
    never what was estimated or reserved for them."""
    tokens: dict[str, PriceKinds] | None = None
    unattributed = 0
    compute: dict[str, float] = {}
    quota = 0.0
    storage = 0
    steps: dict[str, int] = {}
    money: dict[str, float] = {}
    turns = 0
    compression: Compression | None = None
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
        storage += used.storage_bytes or 0
        for code, amount in (used.currency or {}).items():
            money[code] = money.get(code, 0.0) + amount
        turns += used.turns or 0
        if used.compression is not None:
            compression = (
                used.compression if compression is None else compression.plus(used.compression)
            )
    return Meter(
        tokens=tokens or {},
        tokens_unattributed=unattributed,
        compute_seconds=compute,
        quota_units=quota,
        storage_bytes=storage,
        steps=steps,
        currency_reported=money,
        turns=turns,
        compression=compression,
    )


def meter_by_step(entries: Iterable[LedgerEntry]) -> dict[str, Meter]:
    """The breakdown of each step, by its identifier, in the order the steps first finished:
    where a run spent (#449). An entry without a step is in no step's meter."""
    by_step: dict[str, list[LedgerEntry]] = {}
    for entry in entries:
        if entry.kind == "step.finished" and entry.refs.step_id is not None:
            by_step.setdefault(entry.refs.step_id, []).append(entry)
    return {step: meter(found) for step, found in by_step.items()}


def combine(left: Meter, right: Meter) -> Meter:
    """The two breakdowns summed, quantity by quantity: the meter of both sets of entries."""

    def summed(a: Mapping[str, float], b: Mapping[str, float]) -> dict[str, float]:
        return {key: a.get(key, 0.0) + b.get(key, 0.0) for key in {*a, *b}}

    return Meter(
        tokens=add_tokens_by_model(dict(left.tokens), dict(right.tokens)) or {},
        tokens_unattributed=left.tokens_unattributed + right.tokens_unattributed,
        compute_seconds=summed(left.compute_seconds, right.compute_seconds),
        quota_units=left.quota_units + right.quota_units,
        storage_bytes=left.storage_bytes + right.storage_bytes,
        steps={k: int(v) for k, v in summed(left.steps, right.steps).items()},
        currency_reported=summed(left.currency_reported, right.currency_reported),
        turns=left.turns + right.turns,
        compression=(
            left.compression.plus(right.compression)
            if left.compression is not None and right.compression is not None
            else left.compression or right.compression
        ),
    )
