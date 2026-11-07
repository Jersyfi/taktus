"""Use case: an entry of the catalogue shared with circles, withdrawn, and used with the caller's
own credential (ADR-0246, ADR-0247).

This is the one writer of `CatalogueShare` and `CallerCredential`. Each act opens one unit of
work: the record changes and its ledger entry is written in the same transaction. An act the
records refuse writes `catalogue.share_refused` with the reason as outcome, commits it, and
raises `ShareError`; nothing else changes.

- **Sharing** checks that the share is whole for its kind, and what the entry's own records
  require: a skill approved or in production, and shared by its owner where it was drawn from
  a person's own use; an agent with an active core, shared by a person.
- **Withdrawing** a model or a connector takes effect only with its removal verdict known.
- **Reading** returns only the shares a viewer is inside.
- **A call's credentials** are the caller's own parameters, or the call is not made.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from taktus.components.catalog.domain.model.agent import AgentCore, CoreState
from taktus.components.catalog.domain.model.maturity import AdapterMaturity
from taktus.components.catalog.domain.model.shares import (
    CallerCredential,
    CatalogueShare,
    CostModel,
    Location,
    Origin,
    ShareError,
    ShareKind,
    ShareState,
    credential_id,
    share_id,
)
from taktus.components.catalog.domain.model.skill import (
    SkillOwnership,
    SkillStage,
    SkillVersion,
)
from taktus.components.catalog.domain.service import shares as rules
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

SHARED = "catalogue.shared"
WITHDRAWN = "catalogue.withdrawn"
SHARE_REFUSED = "catalogue.share_refused"
CREDENTIAL_BOUND = "credential.bound"

HUB_STAGES = (SkillStage.APPROVED, SkillStage.PRODUCTION)
"""The stages at which a skill appears in the hub (UC-14.3)."""


@dataclass(frozen=True)
class ShareEntry:
    tenant: Tenant
    kind: ShareKind
    subject: str
    owner: str
    purpose: str
    circles: Sequence[str]
    actor: str | None
    """The person who shares it, as the ledger names them; None when no person acts."""
    location: Location | None = None
    cost_model: CostModel | None = None
    origin: Origin | None = None
    version: str | None = None
    evaluations: Sequence[str] = ()


class CatalogueShares:
    def __init__(
        self,
        shares: Repository[CatalogueShare],
        credentials: Repository[CallerCredential],
        maturities: Repository[AdapterMaturity],
        skills: Repository[SkillVersion],
        owners: Repository[SkillOwnership],
        cores: Repository[AgentCore],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._shares = shares
        self._credentials = credentials
        self._maturities = maturities
        self._skills = skills
        self._owners = owners
        self._cores = cores
        self._work = work
        self._ledger = ledger
        self._clock = clock

    # --- reading ----------------------------------------------------------------------------

    async def get(self, tenant: Tenant, kind: ShareKind, subject: str) -> CatalogueShare | None:
        async with self._work.transaction(tenant):
            return await self._shares.get(tenant, share_id(kind, subject))

    async def visible(
        self, tenant: Tenant, identity: str, org_path: Sequence[str]
    ) -> list[CatalogueShare]:
        """The shares the viewer is inside, and no other."""
        async with self._work.transaction(tenant):
            found = await self._shares.list(tenant)
        return rules.visible(found, identity, org_path)

    async def admits(
        self,
        tenant: Tenant,
        kind: ShareKind,
        subject: str,
        identity: str,
        org_path: Sequence[str],
    ) -> bool:
        """Whether the identity may use the entry. An entry with no share is the tenant's, as
        the operator configured it (ADR-0246 §3)."""
        share = await self.get(tenant, kind, subject)
        return share is None or share.admits(identity, org_path)

    async def skill_hub(
        self, tenant: Tenant, identity: str, org_path: Sequence[str]
    ) -> list[SkillVersion]:
        """The skill versions a viewer finds in the hub: approved or in production, and either
        unshared or shared with a circle the viewer is inside. A private draft is no entry."""
        async with self._work.transaction(tenant):
            versions = await self._skills.list(tenant)
            found = {s.subject: s for s in await self._shares.list(tenant) if s.kind == "skill"}
        hub = []
        for version in versions:
            if version.stage not in HUB_STAGES or version.private:
                continue
            share = found.get(version.name)
            if share is not None and not share.admits(identity, org_path):
                continue
            hub.append(version)
        return sorted(hub, key=lambda v: v.id)

    # --- sharing ----------------------------------------------------------------------------

    async def share(self, entry: ShareEntry) -> CatalogueShare:
        """The entry shared with its circles, replacing the circles it was shared with."""
        identifier = share_id(entry.kind, entry.subject)
        if entry.actor is None:
            await self._refuse(entry.tenant, entry.kind, entry.subject, None, "not_accepted")
            raise ShareError(
                "not_accepted",
                f"{identifier} is shared only by a person's act; Taktus never shares on its own",
            )
        await self._entry_allows(entry)
        try:
            share = CatalogueShare(
                id=identifier,
                tenant=entry.tenant,
                kind=entry.kind,
                subject=entry.subject,
                owner=entry.owner,
                purpose=entry.purpose,
                circles=tuple(entry.circles),
                location=entry.location,
                cost_model=entry.cost_model,
                origin=entry.origin,
                version=entry.version,
                evaluations=tuple(entry.evaluations),
                shared_at=self._clock.now(),
                shared_by=entry.actor,
            )
        except ValidationError as error:
            findings = "; ".join(
                str(e["msg"]).removeprefix("Value error, ") for e in error.errors()
            )
            await self._refuse(entry.tenant, entry.kind, entry.subject, entry.actor, "incomplete")
            raise ShareError("incomplete", f"{identifier} cannot be shared: {findings}") from None
        async with self._work.transaction(entry.tenant):
            await self._shares.put(entry.tenant, share)
            await self._record(
                entry.tenant, share.kind, share.subject, SHARED, "shared", entry.actor
            )
        return share

    async def _entry_allows(self, entry: ShareEntry) -> None:
        """What the entry's own records require before it is shared."""
        tenant, subject = entry.tenant, entry.subject
        if entry.kind is ShareKind.SKILL:
            async with self._work.transaction(tenant):
                versions = [v for v in await self._skills.list(tenant) if v.name == subject]
                owners = [await self._owners.get(tenant, v.id) for v in versions if v.owned]
            ready = [v for v in versions if v.stage in HUB_STAGES]
            if not ready:
                await self._refuse(tenant, entry.kind, subject, entry.actor, "not_approved")
                raise ShareError(
                    "not_approved",
                    f"the skill {subject!r} has no version approved through its lifecycle",
                )
            others = sorted({o.owner for o in owners if o is not None} - {entry.actor or ""})
            if others:
                await self._refuse(tenant, entry.kind, subject, entry.actor, "not_owner")
                raise ShareError(
                    "not_owner",
                    f"the skill {subject!r} was drawn from a person's own use, and only that "
                    "person shares it",
                )
        elif entry.kind is ShareKind.AGENT:
            async with self._work.transaction(tenant):
                active = [
                    c
                    for c in await self._cores.list(tenant)
                    if c.agent == subject and c.state is CoreState.ACTIVE
                ]
            if not active:
                await self._refuse(tenant, entry.kind, subject, entry.actor, "not_accepted")
                raise ShareError(
                    "not_accepted", f"the agent {subject!r} has no active core to share"
                )

    async def withdraw(
        self,
        tenant: Tenant,
        kind: ShareKind,
        subject: str,
        actor: str,
        *,
        despite_broke: bool = False,
    ) -> CatalogueShare:
        """The share withdrawn from every circle. A model or a connector only with its removal
        verdict known (ADR-0246 §5)."""
        identifier = share_id(kind, subject)
        async with self._work.transaction(tenant):
            share = await self._shares.get(tenant, identifier)
            record = await self._maturities.get(tenant, subject)
        if share is None or share.state is ShareState.WITHDRAWN:
            raise ShareError("unknown", f"{identifier} is not shared")
        outcome = "withdrawn"
        if kind in (ShareKind.MODEL, ShareKind.CONNECTOR):
            decided = rules.withdrawal(
                None if record is None else record.removal, despite_broke=despite_broke
            )
            if not decided.allowed:
                await self._refuse(tenant, kind, subject, actor, decided.outcome)
                raise ShareError(
                    decided.outcome, f"{identifier} is not withdrawn: {decided.reason}"
                )
            outcome = decided.outcome
        withdrawn = share.model_copy(update={"state": ShareState.WITHDRAWN})
        async with self._work.transaction(tenant):
            await self._shares.put(tenant, withdrawn)
            await self._record(tenant, kind, subject, WITHDRAWN, outcome, actor)
        return withdrawn

    # --- a caller's own credential ----------------------------------------------------------

    async def bind_credential(
        self, tenant: Tenant, identity: str, name: str, suffix: str, actor: str
    ) -> CallerCredential:
        binding = CallerCredential(
            id=credential_id(identity, name),
            tenant=tenant,
            identity=identity,
            name=name,
            suffix=suffix,
            bound_at=self._clock.now(),
        )
        async with self._work.transaction(tenant):
            await self._credentials.put(tenant, binding)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=CREDENTIAL_BOUND,
                    refs=LedgerRefs(tenant=tenant, actor=actor),
                    adapter=None,
                    outcome="bound",
                ),
            )
        return binding

    async def caller_credentials(
        self, tenant: Tenant, connector: str, identity: str, names: Sequence[str]
    ) -> rules.Resolved | None:
        """The parameters a call through the connector names for its caller; None where the
        connector is not shared, so that the call names what its work names (ADR-0247 §2)."""
        share = await self.get(tenant, ShareKind.CONNECTOR, connector)
        if share is None or share.state is ShareState.WITHDRAWN:
            return None
        async with self._work.transaction(tenant):
            bound = list(await self._credentials.list(tenant))
        return rules.credentials(names, identity, bound)

    # --- the ledger -------------------------------------------------------------------------

    async def _refuse(
        self, tenant: Tenant, kind: ShareKind, subject: str, actor: str | None, reason: str
    ) -> None:
        async with self._work.transaction(tenant):
            await self._record(tenant, kind, subject, SHARE_REFUSED, reason, actor)

    async def _record(
        self,
        tenant: Tenant,
        kind: ShareKind,
        subject: str,
        fact: str,
        outcome: str,
        actor: str | None,
    ) -> None:
        adapter = subject if kind in (ShareKind.MODEL, ShareKind.CONNECTOR) else None
        await self._ledger.record(
            tenant,
            Fact(
                kind=fact,
                refs=LedgerRefs(
                    tenant=tenant,
                    actor=actor,
                    agent_id=subject if kind is ShareKind.AGENT else None,
                    skill_id=subject if kind is ShareKind.SKILL else None,
                ),
                adapter=adapter,
                outcome=outcome,
            ),
        )
