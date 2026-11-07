"""Whose own credential a step reads with when it acts on behalf of a person (ADR-0264).

A step whose connector call is marked `on_behalf` is served with the credential of the identity
the run acts for, never with one of Taktus's own. The tenant's configuration names, per
identity, the parameter of that identity's own credential that stands for a parameter the step
names; the operator creates the secret and maps it. The composition root answers
this port from that configuration.
"""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class PersonalCredentials(Protocol):
    async def own(self, tenant: Tenant, identity: str, parameter: str) -> str | None:
        """The parameter of the identity's own credential that stands for `parameter`, or None
        when the identity has none: then the step gets nothing from the source."""
        ...
