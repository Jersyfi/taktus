"""The run's port `Shares`, answered from the catalogue's shares and the identity directory
(ADR-0246, ADR-0247; UC-8.6, UC-8.7, UC-8.8). Components never import each other; the
composition root joins them here.

It also reads an entry's use per organisational unit from the ledger and the runs, with the
viewer's own use apart and nobody else's (ADR-0246 §6).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from typing import Any

from taktus.components.catalog.application.service import CatalogueShares
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    AgentCore,
    CallerCredential,
    CatalogueShare,
    ShareKind,
    SkillOwnership,
    SkillVersion,
)
from taktus.components.catalog.domain.service import shares as rules
from taktus.components.run.domain.model import Run
from taktus.components.run.ports import CallerCall
from taktus.ports.clock import Clock
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

BIND = "taktusctl catalogue bind-credential"
CALLS: dict[ShareKind, str] = {
    ShareKind.MODEL: "step.finished",
    ShareKind.CONNECTOR: "step.finished",
    ShareKind.AGENT: "agent.called",
}


class SharesOfTheRun:
    def __init__(self, shares: CatalogueShares, identities: IdentityResolver) -> None:
        self.shares = shares
        """The use case itself, for the command line that shares and withdraws."""
        self._identities = identities

    async def _path(self, tenant: Tenant, identity: str) -> tuple[str, ...]:
        placed = await self._identities.identity(tenant, identity)
        return () if placed is None else placed.org_path

    async def unshared_models(
        self, tenant: Tenant, identity: str, adapters: Collection[str]
    ) -> frozenset[str]:
        path = await self._path(tenant, identity)
        unshared: set[str] = set()
        for adapter in adapters:
            if not await self.shares.admits(tenant, ShareKind.MODEL, adapter, identity, path):
                unshared.add(adapter)
        return frozenset(unshared)

    async def connector_call(
        self, tenant: Tenant, identity: str, adapter: str, names: Sequence[str]
    ) -> CallerCall:
        path = await self._path(tenant, identity)
        if not await self.shares.admits(tenant, ShareKind.CONNECTOR, adapter, identity, path):
            return CallerCall(
                refusal="outside_circle",
                why=f"{adapter} is not shared with a circle {identity} is inside",
            )
        resolved = await self.shares.caller_credentials(tenant, adapter, identity, names)
        if resolved is None:
            return CallerCall()
        if resolved.lacking:
            return CallerCall(
                refusal="no_caller_credential",
                why=(
                    f"{identity} has no credential of their own for {', '.join(resolved.lacking)}"
                    f" on the shared {adapter}; a call never acts with someone else's ({BIND})"
                ),
            )
        return CallerCall(names=resolved.names)


class CatalogueUse:
    """An entry's use, per organisational unit and the viewer's own (ADR-0246 §6)."""

    def __init__(self, runs: Repository[Run], ledger: Ledger, work: UnitOfWork) -> None:
        self._runs = runs
        self._ledger = ledger
        self._work = work

    async def of(self, tenant: Tenant, kind: ShareKind, subject: str, viewer: str) -> rules.Use:
        if kind is ShareKind.SKILL:
            async with self._work.transaction(tenant):
                runs = list(await self._runs.list(tenant))
            calls = [
                rules.Call(run_id=r.id, org_unit=r.org_unit, identity=r.identity)
                for r in runs
                if subject in r.skills
            ]
            return rules.use(calls, viewer)
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, [CALLS[kind]])
        if kind is ShareKind.AGENT:
            mine = [
                e for e in entries if e.refs.agent_id and e.refs.agent_id.startswith(subject + ":")
            ]
        else:
            mine = [e for e in entries if e.adapter == subject]
        run_ids = {e.refs.run_id for e in mine if e.refs.run_id}
        async with self._work.transaction(tenant):
            placed = {i: await self._runs.get(tenant, i) for i in run_ids}
        calls = []
        for entry in mine:
            run = placed.get(entry.refs.run_id or "")
            calls.append(
                rules.Call(
                    run_id=entry.refs.run_id or "",
                    org_unit=None if run is None else run.org_unit,
                    identity=None if run is None else run.identity,
                )
            )
        return rules.use(calls, viewer)


def shares_of(
    of: Callable[[type[Any]], Any],
    work: UnitOfWork,
    ledger: Ledger,
    clock: Clock,
    identities: IdentityResolver,
) -> SharesOfTheRun:
    """The catalogue's shares over the stores, answering the run's port."""
    return SharesOfTheRun(
        CatalogueShares(
            of(CatalogueShare),
            of(CallerCredential),
            of(AdapterMaturity),
            of(SkillVersion),
            of(SkillOwnership),
            of(AgentCore),
            work,
            ledger,
            clock,
        ),
        identities,
    )
