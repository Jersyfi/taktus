"""PROVISIONAL: one configured operator identity per tenant, until the identity component exists.

Nothing executes without an identity (control-plane.md §2), and the identity component that
would authenticate a sender and map a channel account to an identity is due with `0.2.0`. In
the meantime the smallest thing that lets a command carry one: `TAKTUS_PROVISIONAL_IDENTITY`
names, per tenant, the identity every command in that tenant acts as — the operator's.

What this adapter does **not** do, and the identity component will: it does not look at the
account. Every sender of every channel resolves to the tenant's operator, so an intake event a
webhook delivered is completed as the operator, whoever caused it. That is acceptable only
while the operator is the one person who both configures the instance and owns the channels
it listens to — the state of this repository — and it is why every resolution carries
`provisional: true` and why the variable's name says so. DEC-0013 records the replacement.

Placement without a tenant — an intake, where the channel does not say which tenant it belongs
to — works only when exactly one tenant is configured; with several, the sender is not placed
and the intake is refused as unknown, because guessing a tenant is what this adapter exists to
stop.
"""

from __future__ import annotations

from collections.abc import Mapping

from taktus.ports.identity import IdentityResolver, Resolution
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Capability


class ProvisionalOperatorIdentity(IdentityResolver):
    def __init__(self, operators: Mapping[str, str]) -> None:
        """`operators` maps a tenant to the identity that acts for it."""
        self._operators = dict(operators)

    @property
    def tenants(self) -> tuple[str, ...]:
        return tuple(self._operators)

    async def resolve(
        self, channel: Capability, account: str, *, tenant: Tenant | None = None
    ) -> Resolution | None:
        if tenant is None:
            if len(self._operators) != 1:
                return None
            (tenant,) = self._operators
        identity = self._operators.get(tenant)
        if identity is None:
            return None
        return Resolution(tenant=tenant, identity=identity, org_path=(tenant,), provisional=True)
