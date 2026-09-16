"""The base of every bound type: frozen, closed, and dumped the way the schema reads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Value(BaseModel):
    """A value object of the shared kernel.

    Frozen: an instance never changes after construction; every invariant is checked in the
    constructor. Closed: a field the schema does not know is a validation error, as
    `additionalProperties: false` makes it in the schema. Aliased fields (`class`) may be given
    by their Python name too.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    def document(self) -> dict[str, Any]:
        """The instance as the JSON document the schema describes: aliases applied, absent
        optional fields left out rather than written as null."""
        # The document is JSON-shaped by construction (mode="json"); Any is what json gives.
        result: dict[str, Any] = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        return result
