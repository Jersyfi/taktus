"""What the instantiation of a domain reaches outside this component (ADR-0263 §2 to §4).

A proposal is the process component's, an identity the identity component's, and which adapter
declares which capability the release's and the configuration's. The composition root answers
the three ports from them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from taktus.ports.persistence import Tenant


class Refused(Exception):
    """A proposal the process component did not make, with every finding."""

    def __init__(self, findings: Sequence[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(self.findings))


class ProcessProposals(Protocol):
    async def propose(
        self, tenant: Tenant, process_id: str, bundle: Mapping[str, Any], by: str, request: str
    ) -> tuple[str, str]:
        """The proposal made of the bundle, as (proposal id, version), under the next version
        the tenant has not registered; Refused with every finding otherwise. Nothing is
        registered."""
        ...


class People(Protocol):
    async def known(self, tenant: Tenant, identity: str) -> bool:
        """Whether the identity is one the tenant knows."""
        ...


class Adapters(Protocol):
    def declaring(self, capability: str) -> tuple[str, ...]:
        """The adapters that declare the capability, by adapter identifier."""
        ...
