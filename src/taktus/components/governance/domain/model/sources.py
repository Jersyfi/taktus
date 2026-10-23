"""What a tenant declares about the data behind its capabilities (ADR-0130, UC-7.7).

Two lists, by capability. **Free of personal fields**: a source an analytic step may read —
a copy the business produced without personal fields, which Taktus does not produce and does
not check (UC-7.7 §3). **Personal**: a capability that serves personal data, whatever its
connector declares; a step that calls it without a case scope waits for a person. A
capability is on one list at most. A tenant that declared nothing holds both empty
(NTC-0224): no analytic step may read a source, and only a connector's own declaration says
that a capability serves personal data.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from taktus.shared.v1 import Capability, Value


class SourceDeclaration(Value):
    """One tenant's declaration, stored under the tenant's own identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    free: tuple[Capability, ...] = ()
    """The capabilities that serve data free of personal fields."""
    personal: tuple[Capability, ...] = ()
    """The capabilities that serve personal data."""
    configured_at: datetime | None = None
    """When it was configured; None for the shipped default, which nobody configured."""

    @model_validator(mode="after")
    def _sound(self) -> SourceDeclaration:
        if self.id != self.tenant:
            raise ValueError(f"a source declaration is stored under its tenant {self.tenant!r}")
        both = sorted(set(self.free) & set(self.personal))
        if both:
            raise ValueError(
                f"{', '.join(both)} cannot be free of personal fields and personal at once"
            )
        for name, listed in (("free", self.free), ("personal", self.personal)):
            if len(set(listed)) != len(listed):
                raise ValueError(f"{name} lists a capability twice")
        return self


def shipped_declaration(tenant: str) -> SourceDeclaration:
    """What a tenant that declared nothing holds (NTC-0224): nothing free, nothing personal."""
    return SourceDeclaration(id=tenant, tenant=tenant)
