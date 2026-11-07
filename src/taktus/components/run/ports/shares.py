"""Who may use a shared model or connector, and with whose credential, seen from the run
(ADR-0246, ADR-0247).

The catalogue keeps the shares and every identity's own credential parameters; the composition
root answers this port from it, because components never import each other. An entry with no
share is the tenant's, as the operator configured it, and every answer then leaves the run as it
was.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Literal, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class CallerCall(Value):
    """What a connector call of a run may name: the caller's own parameters, or a refusal."""

    refusal: Literal["outside_circle", "no_caller_credential"] | None = None
    why: str | None = Field(default=None, min_length=1)
    names: tuple[str, ...] | None = None
    """The parameters the call names in place of the work's; None: what the work names."""


class Shares(Protocol):
    async def unshared_models(
        self, tenant: Tenant, identity: str, adapters: Collection[str]
    ) -> frozenset[str]:
        """Of these model adapters, those shared with no circle the identity is inside. Opens
        its own unit of work."""
        ...

    async def connector_call(
        self, tenant: Tenant, identity: str, adapter: str, names: Sequence[str]
    ) -> CallerCall:
        """Whether the identity may call the connector, and the credential parameters it calls
        with. Opens its own unit of work."""
        ...
