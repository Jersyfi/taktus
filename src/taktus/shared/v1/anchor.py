"""Anchor.json: an act that stays with a person regardless of the autonomy level."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1.capability import CapabilityPattern
from taktus.shared.v1.value import Value


class AnchorClass(StrEnum):
    LEGAL = "legal"
    STRATEGIC = "strategic"


class AppliesTo(Value):
    """What triggers the anchor: at least one selector."""

    actions: tuple[CapabilityPattern, ...] | None = Field(default=None, min_length=1)
    processes: tuple[str, ...] | None = Field(default=None, min_length=1)
    risk_classes: tuple[str, ...] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _at_least_one_selector(self) -> AppliesTo:
        if not self.document():
            raise ValueError("an anchor needs at least one selector")
        for name in ("actions", "processes", "risk_classes"):
            values = getattr(self, name)
            if values is None:
                continue
            if any(not v for v in values):
                raise ValueError(f"{name} contains an empty item")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} lists an item twice")
        return self


class AnchorScope(Value):
    tenant: str | None = Field(default=None, min_length=1)
    domain: str | None = Field(default=None, min_length=1)
    jurisdiction: str | None = Field(default=None, pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")


class Decider(Value):
    role: str = Field(min_length=1)


class Anchor(Value):
    id: str = Field(min_length=1)
    class_: AnchorClass = Field(alias="class")
    act: str = Field(min_length=1)
    applies_to: AppliesTo
    scope: AnchorScope | None = None
    decider: Decider
