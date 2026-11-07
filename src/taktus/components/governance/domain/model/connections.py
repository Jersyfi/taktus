"""A tenant's grant of writing on one connection (ADR-0262 §2, UC-5.6).

A connection of a capability in `READ_UNLESS_GRANTED` reads until a person grants writing on
it. The grant is one record per tenant and capability, stored under the capability. A
withdrawal keeps the record, withdrawn: what was granted and withdrawn is in the ledger, with
the person who did it as its actor, never a field here (principle 14).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from taktus.shared.v1 import Capability, Value

GRANTING_ROLE = "owner"
"""The role that holds the right to grant writing on a connection (ADR-0262 §2)."""


class ConnectionGrant(Value):
    id: str = Field(min_length=1)
    """The capability whose connection it is about."""
    tenant: str = Field(min_length=1)
    capability: Capability
    created_at: datetime
    """When it was granted, or withdrawn where it is."""
    withdrawn: bool = False

    @model_validator(mode="after")
    def _stored_under_its_capability(self) -> ConnectionGrant:
        if self.id != self.capability:
            raise ValueError(f"a grant is stored under its capability {self.capability!r}")
        return self

    @property
    def in_force(self) -> bool:
        return not self.withdrawn
