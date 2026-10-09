"""Use case: configure a tenant's anchors, and read the anchors in force (ADR-0042).

The configuration is a document: `anchors`, a list in the shape of
`contracts/shared/v1/Anchor.json`, and `risk_classes`, a map from a risk class to the tool
actions it covers. One that would leave the legal or the correction class empty, select an
undefined risk class, or name an anchor twice is refused, and nothing is stored. A stored
configuration replaces the one before it; the ledger entry `anchors.configured` carries the
digest of what was stored and the identity who configured it, in the same transaction.

A tenant that configured nothing holds the shipped default (`shipped_default`).
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
from taktus.components.governance.domain.service.anchors import applying
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
    """`{"anchors": [...], "risk_classes": {...}}`."""
    actor: str


class ConfigureAnchorsHandler:
    def __init__(
        self,
        configurations: Repository[AnchorConfiguration],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._configurations = configurations
        self._work = work
        self._ledger = ledger
        self._clock = clock

    async def execute(self, command: ConfigureAnchors) -> AnchorConfiguration:
        unknown = set(command.document) - {"anchors", "risk_classes"}
        if unknown:
            raise AnchorsRefused(f"unknown keys: {', '.join(sorted(unknown))}")
        try:
            configuration = AnchorConfiguration.model_validate(
                {
                    "id": command.tenant,
                    "tenant": command.tenant,
                    "anchors": command.document.get("anchors", []),
                    "risk_classes": command.document.get("risk_classes", {}),
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

    def __init__(self, configurations: Repository[AnchorConfiguration], work: UnitOfWork) -> None:
        self._configurations = configurations
        self._work = work

    async def of(self, tenant: Tenant) -> AnchorConfiguration:
        async with self._work.transaction(tenant):
            stored = await self._configurations.get(tenant, tenant)
        return stored if stored is not None else shipped_default(tenant)

    async def applying(
        self, tenant: Tenant, process: str, actions: Sequence[str]
    ) -> tuple[Anchor, ...]:
        """The anchors that name a step's act."""
        return applying(await self.of(tenant), process=process, actions=actions)


def _explained(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'configuration'}: {e['msg']}"
        for e in error.errors()
    )
