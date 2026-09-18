"""Who acts: how a sender on a channel becomes a Taktus identity in a tenant.

The identity component (`0.2.0`) will own tenants, accounts, the mapping from a channel account
to an identity, and roles; this port is what the rest of the core asks of it. A resolution
places a sender: the tenant the command belongs to, the identity that acts, the organisational
path for visibility and cost attribution (control-plane.md §2). A sender that cannot be placed
gets no execution.

Until the component exists, the port is served by a **provisional** adapter — one configured
operator identity per tenant (`adapters/driven/identity/provisional.py`, DEC-0013) — and every
resolution it answers says so in `provisional`, so that nothing downstream mistakes it for an
authenticated identity.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Capability, Value


class Resolution(Value):
    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    org_path: tuple[str, ...] = Field(min_length=1)
    provisional: bool
    """True when the identity was configured, not authenticated: the provisional operator
    identity of DEC-0013. The identity component answers False."""


class IdentityResolver(Protocol):
    async def resolve(
        self, channel: Capability, account: str, *, tenant: Tenant | None = None
    ) -> Resolution | None:
        """Place a sender: the account as the channel's source system names them (an opaque
        identifier), optionally within a tenant the caller already knows. None when the sender
        cannot be placed — an unknown sender gets no execution."""
        ...
