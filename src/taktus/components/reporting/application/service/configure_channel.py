"""Use case: a tenant configures its owner-facing channel (ADR-0045).

The configuration names the owner, whom the owner named, the channel and the address reports go
to, the ticket system if any, and the phrasebook in the owner's language — its own, or by
`language` one Taktus ships. One that does not hold
— no owner, a phrasebook missing a sentence or using a value it does not have — is refused and
nothing is stored. `owner_channel.configured` records its digest and who configured it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from taktus.components.reporting.application.service._ledger import CONFIGURED, digest
from taktus.components.reporting.application.service.errors import ChannelRefused
from taktus.components.reporting.domain.model import OwnerChannel
from taktus.components.reporting.ports.phrasebooks import Phrasebooks
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs


@dataclass(frozen=True)
class ConfigureChannel:
    tenant: Tenant
    document: Mapping[str, Any]
    actor: str


class ConfigureChannelHandler:
    def __init__(
        self,
        channels: Repository[OwnerChannel],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        phrasebooks: Phrasebooks | None = None,
    ) -> None:
        self._channels = channels
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._phrasebooks = phrasebooks

    async def execute(self, command: ConfigureChannel) -> OwnerChannel:
        given = {
            k: v
            for k, v in command.document.items()
            if k not in ("id", "tenant", "configured_at", "configured_by", "language")
        }
        language = command.document.get("language")
        if "phrasebook" not in given:
            shipped = (
                self._phrasebooks.shipped(language)
                if isinstance(language, str) and self._phrasebooks is not None
                else None
            )
            if shipped is None:
                raise ChannelRefused(
                    "the owner-facing channel is not configured: it gives no `phrasebook`, "
                    f"and Taktus ships none for the language {language!r}"
                )
            given["phrasebook"] = dict(shipped)
        try:
            channel = OwnerChannel.model_validate(
                {
                    **given,
                    "id": command.tenant,
                    "tenant": command.tenant,
                    "configured_at": self._clock.now(),
                    "configured_by": command.actor,
                }
            )
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'channel'}: {e['msg']}"
                for e in error.errors()
            )
            raise ChannelRefused(
                f"the owner-facing channel is not configured: {problems}"
            ) from error
        canonical = json.dumps(channel.document(), ensure_ascii=False, sort_keys=True)
        async with self._work.transaction(command.tenant):
            await self._channels.put(command.tenant, channel)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=command.actor),
                    outcome="configured",
                    content_digest=digest(canonical),
                ),
            )
        return channel


class ChannelOf:
    """The tenant's owner-facing channel, or None when it configured none."""

    def __init__(self, channels: Repository[OwnerChannel], work: UnitOfWork) -> None:
        self._channels = channels
        self._work = work

    async def of(self, tenant: Tenant) -> OwnerChannel | None:
        async with self._work.transaction(tenant):
            return await self._channels.get(tenant, tenant)
