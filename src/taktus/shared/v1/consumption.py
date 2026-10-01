"""Consumption.json: the raw quantities one step used or is expected to use."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, StringConstraints, model_validator

from taktus.shared.v1.value import Value

type ResourceClass = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(\.[a-z0-9-]+)*$")]
"""A class of compute, named by the operator: cpu.small, gpu.small."""

type CurrencyAmounts = Annotated[
    dict[Annotated[str, StringConstraints(pattern=r"^[a-z]{3}$")], Annotated[float, Field(ge=0)]],
    Field(min_length=1),
]
"""Money by ISO 4217 code in lowercase, {"eur": 3.2}; never a fixed currency."""

MODEL_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$"

type ModelName = Annotated[str, StringConstraints(pattern=MODEL_NAME_PATTERN)]
"""A model as the endpoint named it when it answered: the name the provenance records."""

PRICE_KINDS = ("input", "output", "cache_read", "cache_write")
"""The kinds of token a provider prices differently: uncached input, output (reasoning
included), input read from a cache, input written to one."""


class PriceKinds(Value):
    """Consumption.json#/$defs/priceKinds: the tokens of one model, by price kind."""

    input: int | None = Field(default=None, ge=0)
    output: int | None = Field(default=None, ge=0)
    cache_read: int | None = Field(default=None, ge=0)
    cache_write: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _at_least_one_kind(self) -> PriceKinds:
        if all(getattr(self, kind) is None for kind in PRICE_KINDS):
            raise ValueError("a model's tokens name at least one price kind")
        return self

    @property
    def tokens_in(self) -> int:
        """Every input-side token, whatever its price."""
        return (self.input or 0) + (self.cache_read or 0) + (self.cache_write or 0)

    def plus(self, other: PriceKinds) -> PriceKinds:
        summed = {
            kind: (getattr(self, kind) or 0) + (getattr(other, kind) or 0)
            for kind in PRICE_KINDS
            if getattr(self, kind) is not None or getattr(other, kind) is not None
        }
        return PriceKinds.model_validate(summed)


type TokensByModel = Annotated[dict[ModelName, PriceKinds], Field(min_length=1)]
"""Tokens per model and price kind: what makes money computable from the record (ADR-0010)."""


def add_tokens_by_model(
    left: TokensByModel | None, right: TokensByModel | None
) -> TokensByModel | None:
    """The two breakdowns summed model by model and kind by kind."""
    if not left:
        return dict(right) if right else None
    summed = dict(left)
    for model, kinds in (right or {}).items():
        summed[model] = summed[model].plus(kinds) if model in summed else kinds
    return summed


QUANTITIES = (
    "tokens_in",
    "tokens_out",
    "tokens_by_model",
    "currency",
    "quota_units",
    "compute_seconds",
    "storage_bytes",
)


class ConsumptionQuantities(Value):
    """Consumption.json#/$defs/quantities: the measurable quantities without closure, so that
    other shapes — an estimate — can extend them."""

    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    tokens_by_model: TokensByModel | None = None
    currency: CurrencyAmounts | None = None
    quota_units: float | None = Field(default=None, ge=0)
    compute_seconds: float | None = Field(default=None, ge=0)
    resource_class: ResourceClass | None = None
    storage_bytes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _compute_names_its_class(self) -> ConsumptionQuantities:
        if self.compute_seconds is not None and self.resource_class is None:
            raise ValueError("compute_seconds is meaningless without its resource_class")
        return self

    def quantities(self) -> dict[str, Any]:
        """The quantities that are present, by name."""
        present: dict[str, Any] = {}
        for name in QUANTITIES:
            value = getattr(self, name)
            if value is not None:
                present[name] = value
        return present


class Consumption(ConsumptionQuantities):
    """What a step used: at least one quantity, raw, never converted into money."""

    @model_validator(mode="after")
    def _at_least_one_quantity(self) -> Consumption:
        if not self.quantities():
            raise ValueError("a consumption carries at least one quantity")
        return self
