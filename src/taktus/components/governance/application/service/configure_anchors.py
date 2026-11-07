"""Use case: configure a tenant's anchors, and read the anchors in force (ADR-0042).

The configuration is a document: `anchors`, a list in the shape of
`contracts/shared/v1/Anchor.json`, and `risk_classes`, a map from a risk class to the tool
actions it covers, and `levels`, the ceiling of a risk class (ADR-0170).
One that would leave the legal or the correction class empty, select an
undefined risk class, or name an anchor twice is refused, and nothing is stored. A stored
configuration replaces the one before it; the ledger entry `anchors.configured` carries the
digest of what was stored and the identity who configured it, in the same transaction.

A tenant that configured nothing holds the shipped default (`shipped_default`). A configuration
that would leave a domain of the tenant without a legal anchor in force is refused as well
(UC-15.5, ADR-0259), and the anchors in force are read within the scope the tenant's domains
give them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from taktus.components.governance.domain.model.anchors import (
    AnchorConfiguration,
    shipped_default,
)
from taktus.components.governance.domain.model.domains import Domain
from taktus.components.governance.domain.service.anchors import applying, ceilings, legal_for
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Anchor, LedgerRefs

CONFIGURED = "anchors.configured"


class AnchorsRefused(Exception):
    """The configuration is not stored; the message says why."""


@dataclass(frozen=True)
class ConfigureAnchors:
    tenant: Tenant
    document: Mapping[str, Any]
    """`{"anchors": [...], "risk_classes": {...}, "levels": {...}}`."""
    actor: str


class ConfigureAnchorsHandler:
    def __init__(
        self,
        configurations: Repository[AnchorConfiguration],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        domains: Repository[Domain] | None = None,
    ) -> None:
        self._configurations = configurations
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._domains = domains

    async def execute(self, command: ConfigureAnchors) -> AnchorConfiguration:
        unknown = set(command.document) - {"anchors", "risk_classes", "levels"}
        if unknown:
            raise AnchorsRefused(f"unknown keys: {', '.join(sorted(unknown))}")
        try:
            configuration = AnchorConfiguration.model_validate(
                {
                    "id": command.tenant,
                    "tenant": command.tenant,
                    "anchors": command.document.get("anchors", []),
                    "risk_classes": command.document.get("risk_classes", {}),
                    "levels": command.document.get("levels", {}),
                    "configured_at": self._clock.now(),
                    "configured_by": command.actor,
                }
            )
        except ValidationError as error:
            raise AnchorsRefused(_explained(error)) from error
        digest = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(configuration.document(), sort_keys=True).encode("utf-8")
            ).hexdigest()
        )
        async with self._work.transaction(command.tenant):
            domains = [] if self._domains is None else await self._domains.list(command.tenant)
            emptied = sorted(d.id for d in domains if not legal_for(configuration, d))
            if emptied:
                raise AnchorsRefused(
                    f"the domain(s) {', '.join(emptied)} would keep no legal anchor in force: a "
                    "domain's catalogue can be reduced but never emptied (UC-15.5)"
                )
            await self._configurations.put(command.tenant, configuration)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=command.actor),
                    outcome="configured",
                    content_digest=digest,
                ),
            )
        return configuration


class AnchorsInForce:
    """The anchors a tenant holds now: its configuration, or the shipped default."""

    def __init__(
        self,
        configurations: Repository[AnchorConfiguration],
        work: UnitOfWork,
        domains: Repository[Domain] | None = None,
    ) -> None:
        self._configurations = configurations
        self._work = work
        self._domains = domains

    async def of(self, tenant: Tenant) -> AnchorConfiguration:
        async with self._work.transaction(tenant):
            stored = await self._configurations.get(tenant, tenant)
        return stored if stored is not None else shipped_default(tenant)

    async def applying(
        self, tenant: Tenant, process: str, actions: Sequence[str]
    ) -> tuple[Anchor, ...]:
        """The anchors that name a step's act, within the scope the tenant's domains give
        them (ADR-0259)."""
        domains: list[Domain] = []
        if self._domains is not None:
            async with self._work.transaction(tenant):
                domains = list(await self._domains.list(tenant))
        return applying(await self.of(tenant), process=process, actions=actions, domains=domains)

    async def ceilings(self, tenant: Tenant, actions: Sequence[str]) -> Mapping[str, int]:
        """The ceiling a risk class sets on each of `actions` it covers (ADR-0170)."""
        found = ceilings(await self.of(tenant), actions)
        return {action: level for action, (level, _) in found.items()}


def _explained(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'configuration'}: {e['msg']}"
        for e in error.errors()
    )
