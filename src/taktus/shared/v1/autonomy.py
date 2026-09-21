"""Autonomy.json: the autonomy of a process with its reason (ADR-0026)."""

from __future__ import annotations

from pydantic import Field, model_validator

from taktus.shared.v1.autonomy_level import AutonomyLevel
from taktus.shared.v1.value import Value


class Autonomy(Value):
    """The level a process runs at, why, and what is missing to go one level higher. Below
    level 4 `toward_next` is required — either what is missing or what forbids the next
    level; at level 4 there is no next level and it is absent."""

    level: AutonomyLevel
    reason: str = Field(min_length=1)
    toward_next: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _toward_next_below_four(self) -> Autonomy:
        if self.level == 4 and self.toward_next is not None:
            raise ValueError("at level 4 there is no next level; toward_next is absent")
        if self.level < 4 and self.toward_next is None:
            raise ValueError(
                "below level 4, toward_next says what is missing to go higher, or what forbids it"
            )
        return self
