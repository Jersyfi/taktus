"""Who acts: how a sender on a channel becomes a Taktus identity in a tenant.

The identity component owns identities, the link from a channel account to an identity, and
the codes a person links an account with (`components/identity`, ADR-0040); this port is what
the rest of the core asks of it. A resolution places a sender: the tenant the command belongs
to, the identity that acts, the organisational path for visibility and cost attribution
(control-plane.md §2). A sender that cannot be placed gets no execution.

The organisation's own identity source — a directory, single sign-on — is a second port,
`IdentitySource`. The identity component asks it about an account it has no link for, and
records what it answers as a link. An adapter for a particular source is a connector of its own.
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
    roles: tuple[str, ...] = ()
    """The roles the identity holds (ADR-0042)."""


class UnknownSenderAnswer(Value):
    """What a sender the component does not know is told, in the channel they wrote on.
    `linked` is set when what they wrote carried a valid link code: the account is linked
    from now on, and the message that carried the code is still not a command."""

    reply: str = Field(min_length=1)
    linked: Resolution | None = None


class IdentityResolver(Protocol):
    async def resolve(
        self, channel: Capability, account: str, *, tenant: Tenant | None = None
    ) -> Resolution | None:
        """Place a sender: the account as the channel's source system names them (an opaque
        identifier), optionally within a tenant the caller already knows. None when the sender
        cannot be placed — an unknown sender gets no execution."""
        ...

    async def identity(self, tenant: Tenant, identity: str) -> Resolution | None:
        """An identity the component knows in the tenant, with its organisational path; None
        when it knows none of that name. What a caller that names an identity itself — the
        command line, the scheduler acting for whoever activated a process — is placed by."""
        ...

    async def unknown_sender(
        self, channel: Capability, account: str, said: str
    ) -> UnknownSenderAnswer:
        """Answer a sender `resolve` did not place: link the account when what they said
        carries a valid link code for this channel, and otherwise offer how to link it."""
        ...


class SourceAnswer(Value):
    """Who the organisation's identity source says an account belongs to."""

    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    org_path: tuple[str, ...] = Field(min_length=1)


class IdentitySource(Protocol):
    async def lookup(self, channel: Capability, account: str) -> SourceAnswer | None:
        """The identity the organisation's source maps the account to, or None when it maps it
        to none. Never a guess from a matching name or address."""
        ...
