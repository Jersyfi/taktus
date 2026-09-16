"""Consumption.json: the raw quantities one step used or is expected to use."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from taktus.shared.v1.value import Value

type ResourceClass = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(\.[a-z0-9-]+)*$")]
"""A class of compute, named by the operator: cpu.small, gpu.small."""

type CurrencyAmounts = Annotated[
    dict[Annotated[str, StringConstraints(pattern=r"^[a-z]{3}$")], Annotated[float, Field(ge=0)]],
    Field(min_length=1),
]
"""Money by ISO 4217 code in lowercase, {"eur": 3.2}; never a fixed currency."""

QUANTITIES = (
    "tokens_in",
    "tokens_out",
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

    def quantities(self) -> dict[str, float | int | dict[str, float]]:
        """The quantities that are present, by name."""
        present: dict[str, float | int | dict[str, float]] = {}
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
