"""The identity component's use cases: placing a sender, linking an account, administering.

`IdentityDirectory` serves the identity port (`ports/identity.py`) and the acts around it:

- **Placing a sender.** An active link for the account on the channel names the identity, and
  the identity names its tenant and organisational path. Without one, the organisation's
  identity source is asked, when one is configured, and what it answers becomes a link. Nothing
  else places anybody: a matching name or address is never looked at.
- **Linking an account.** A person proves their identity with its account key and creates a
  link code for one channel; writing the code in that channel from the account links it. A
  second link for an account that has one is refused.
- **Administering.** An administrator adds an identity, issues a new key for one, lists every
  link of a tenant and revokes one. The next event from a revoked account is from an unknown
  sender.

Every identity added and every link made or revoked is a ledger entry in the same transaction:
`identity.created`, `identity.linked` (outcome `confirmed` or `source`), `identity.unlinked`
(outcome `revoked`). An entry carries identifiers and a digest, never the account or a name
(ADR-0006); the actor is the identity that acted, where one did.

An account belongs to at most one identity across every tenant the instance serves: a link is
looked for in each of them, and refused where one is active in any.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from taktus.components.identity.domain.model import (
    CODE,
    CODE_PREFIX,
    CODE_VALIDITY,
    KEY_PREFIX,
    ChannelLink,
    Identity,
    LinkCode,
    LinkOrigin,
    code_id,
    digest,
    link_id,
)
from taktus.ports.clock import Clock, Randomness
from taktus.ports.identity import (
    IdentityResolver,
    IdentitySource,
    Resolution,
    UnknownSenderAnswer,
)
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability, LedgerRefs

CREATED = "identity.created"
LINKED = "identity.linked"
UNLINKED = "identity.unlinked"
KEY_ISSUED = "identity.key_issued"
ROLES_SET = "identity.roles_set"


class IdentityError(Exception):
    """An identity act that cannot be done as asked; the message says why."""


class UnknownTenant(IdentityError):
    def __init__(self, tenant: Tenant) -> None:
        super().__init__(f"this instance serves no tenant {tenant!r}")


class UnknownIdentity(IdentityError):
    def __init__(self, tenant: Tenant, identity: str) -> None:
        super().__init__(f"tenant {tenant!r} has no identity {identity!r}")


class IdentityExists(IdentityError):
    def __init__(self, identity: Identity) -> None:
        self.identity = identity
        super().__init__(
            f"tenant {identity.tenant!r} has an identity {identity.id!r} already, under "
            f"{'/'.join(identity.org_path)}"
        )


class AlreadyLinked(IdentityError):
    def __init__(self, channel: Capability) -> None:
        super().__init__(
            f"this account on {channel} is linked to an identity already; one account maps to "
            "at most one identity, and an administrator revokes a link before another is made"
        )


class UnknownLink(IdentityError):
    def __init__(self, tenant: Tenant, link: str) -> None:
        super().__init__(f"tenant {tenant!r} has no active link {link!r}")


def offer(channel: Capability) -> str:
    """What an unknown sender is told: nothing was done, and how to link the account."""
    return (
        "Taktus does not know this account yet, so nothing was done with this message. "
        "If you have a Taktus account, create a link code for "
        f"{channel} there and write the code here; from then on, what you write here is done "
        "as you. If you have none, ask your administrator to register you."
    )


LINKED_REPLY = (
    "This account is now linked to your Taktus account. The message with the code was not "
    "acted on; write your request again."
)
TAKEN_REPLY = (
    "This account is linked to another Taktus identity already, so the code linked nothing. "
    "Ask your administrator to revoke the existing link first."
)


def _digest_of(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdentityDirectory(IdentityResolver):
    def __init__(
        self,
        *,
        tenants: Sequence[Tenant],
        identities: Repository[Identity],
        links: Repository[ChannelLink],
        codes: Repository[LinkCode],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        randomness: Randomness,
        source: IdentitySource | None = None,
    ) -> None:
        self._tenants = tuple(tenants)
        self._identities = identities
        self._links = links
        self._codes = codes
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._randomness = randomness
        self._source = source

    @property
    def tenants(self) -> tuple[Tenant, ...]:
        return self._tenants

    # --- the port ---------------------------------------------------------------------------

    async def resolve(
        self, channel: Capability, account: str, *, tenant: Tenant | None = None
    ) -> Resolution | None:
        searched = self._tenants if tenant is None else (tenant,)
        found = await self._active_link(channel, account, searched)
        if found is not None:
            return _resolution(found[1])
        if self._source is None:
            return None
        answer = await self._source.lookup(channel, account)
        if answer is None or answer.tenant not in searched:
            return None
        if tenant is not None and await self._active_link(channel, account, self._tenants):
            return None  # the account is another tenant's; it maps to at most one identity
        return await self._link_from_source(
            channel, account, answer.tenant, answer.identity, answer.org_path
        )

    async def identity(self, tenant: Tenant, identity: str) -> Resolution | None:
        if tenant not in self._tenants:
            return None
        async with self._work.transaction(tenant):
            known = await self._identities.get(tenant, identity)
        return None if known is None else _resolution(known)

    async def unknown_sender(
        self, channel: Capability, account: str, said: str
    ) -> UnknownSenderAnswer:
        for code in dict.fromkeys(CODE.findall(said)):
            for tenant in self._tenants:
                linked = await self._redeem(tenant, code, channel, account)
                if linked is not None:
                    return linked
        return UnknownSenderAnswer(reply=offer(channel))

    async def _redeem(
        self, tenant: Tenant, code: str, channel: Capability, account: str
    ) -> UnknownSenderAnswer | None:
        """The code's answer when the tenant holds it and it can still be redeemed for this
        channel; None otherwise."""
        now = self._clock.now()
        async with self._work.transaction(tenant):
            held = await self._codes.get(tenant, code_id(code))
        if held is None or not held.redeemable(channel, now):
            return None
        if await self._active_link(channel, account, self._tenants) is not None:
            return UnknownSenderAnswer(reply=TAKEN_REPLY)
        async with self._work.transaction(tenant):
            held = await self._codes.get(tenant, code_id(code))
            identity = await self._identities.get(tenant, held.identity) if held else None
            if held is None or identity is None or not held.redeemable(channel, now):
                return None
            await self._codes.put(tenant, held.model_copy(update={"used_at": now}))
            await self._put_link(tenant, channel, account, identity.id, LinkOrigin.CONFIRMED, now)
        return UnknownSenderAnswer(reply=LINKED_REPLY, linked=_resolution(identity))

    # --- a person, in their Taktus account --------------------------------------------------

    async def authenticate(self, key: str) -> Resolution | None:
        """The identity whose account key this is, or None. Only the key's digest is compared,
        and in constant time."""
        if not key.startswith(KEY_PREFIX):
            return None
        wanted = digest(key)
        for tenant in self._tenants:
            async with self._work.transaction(tenant):
                identities = await self._identities.list(tenant)
            for identity in identities:
                if identity.key_digest is not None and hmac.compare_digest(
                    identity.key_digest, wanted
                ):
                    return _resolution(identity)
        return None

    async def create_link_code(self, who: Resolution, channel: Capability) -> tuple[str, LinkCode]:
        """A single-use code that links the account `who` writes it from on `channel`. The
        code is returned to be shown once; only its digest is kept."""
        code = CODE_PREFIX + self._randomness.token(12)
        now = self._clock.now()
        record = LinkCode(
            id=code_id(code),
            tenant=who.tenant,
            identity=who.identity,
            channel=channel,
            created_at=now,
            expires_at=now + CODE_VALIDITY,
        )
        async with self._work.transaction(who.tenant):
            if await self._identities.get(who.tenant, who.identity) is None:
                raise UnknownIdentity(who.tenant, who.identity)
            await self._codes.put(who.tenant, record)
        return code, record

    # --- an administrator --------------------------------------------------------------------

    async def add(
        self,
        tenant: Tenant,
        identity: str,
        org_path: Sequence[str],
        *,
        by: str | None = None,
        roles: Sequence[str] = (),
    ) -> tuple[Identity, str]:
        """A new identity with its first account key; the key is returned to be handed to the
        person once. `IdentityExists` when the tenant has one of that name."""
        self._served(tenant)
        key = self._new_key()
        added = Identity(
            id=identity,
            tenant=tenant,
            org_path=tuple(org_path) or (tenant,),
            roles=tuple(dict.fromkeys(roles)),
            key_digest=digest(key),
            created_at=self._clock.now(),
        )
        async with self._work.transaction(tenant):
            existing = await self._identities.get(tenant, identity)
            if existing is not None:
                raise IdentityExists(existing)
            await self._identities.put(tenant, added)
            await self._record(
                tenant,
                CREATED,
                "created",
                actor=by or identity,
                document={
                    "identity": identity,
                    "org_path": list(added.org_path),
                    "roles": list(added.roles),
                },
            )
        return added, key

    async def set_roles(
        self, tenant: Tenant, identity: str, roles: Sequence[str], *, by: str | None = None
    ) -> Identity:
        """The roles the identity holds from now on, replacing the ones before."""
        self._served(tenant)
        async with self._work.transaction(tenant):
            existing = await self._identities.get(tenant, identity)
            if existing is None:
                raise UnknownIdentity(tenant, identity)
            changed = existing.model_copy(update={"roles": tuple(dict.fromkeys(roles))})
            Identity.model_validate(changed.document())
            await self._identities.put(tenant, changed)
            await self._record(
                tenant,
                ROLES_SET,
                "set",
                actor=by,
                document={"identity": identity, "roles": list(changed.roles)},
            )
        return changed

    async def issue_key(self, tenant: Tenant, identity: str, *, by: str | None = None) -> str:
        """A new account key for an identity; the old one stops working."""
        self._served(tenant)
        key = self._new_key()
        async with self._work.transaction(tenant):
            existing = await self._identities.get(tenant, identity)
            if existing is None:
                raise UnknownIdentity(tenant, identity)
            await self._identities.put(
                tenant, existing.model_copy(update={"key_digest": digest(key)})
            )
            await self._record(
                tenant, KEY_ISSUED, "issued", actor=by or identity, document={"identity": identity}
            )
        return key

    async def links(self, tenant: Tenant) -> list[ChannelLink]:
        """Every link of the tenant, active and revoked."""
        self._served(tenant)
        async with self._work.transaction(tenant):
            return sorted(await self._links.list(tenant), key=lambda link: link.linked_at)

    async def revoke(self, tenant: Tenant, link: str, *, by: str | None = None) -> ChannelLink:
        """The link is revoked; the account is from an unknown sender from now on."""
        self._served(tenant)
        now = self._clock.now()
        async with self._work.transaction(tenant):
            existing = await self._links.get(tenant, link)
            if existing is None or not existing.active:
                raise UnknownLink(tenant, link)
            revoked = existing.model_copy(update={"revoked_at": now, "revoked_by": by})
            await self._links.put(tenant, revoked)
            await self._record(
                tenant,
                UNLINKED,
                "revoked",
                actor=by,
                document={"link": link, "identity": existing.identity},
            )
        return revoked

    # --- inside -----------------------------------------------------------------------------

    def _served(self, tenant: Tenant) -> None:
        if tenant not in self._tenants:
            raise UnknownTenant(tenant)

    def _new_key(self) -> str:
        return KEY_PREFIX + self._randomness.token(32)

    async def _active_link(
        self, channel: Capability, account: str, tenants: Sequence[Tenant]
    ) -> tuple[ChannelLink, Identity] | None:
        """The active link of the account in any of `tenants`, with its identity; each tenant
        is read in a transaction of its own."""
        wanted = link_id(channel, account)
        for tenant in tenants:
            async with self._work.transaction(tenant):
                found = await self._link_in(tenant, wanted)
            if found is not None:
                return found
        return None

    async def _link_in(self, tenant: Tenant, wanted: str) -> tuple[ChannelLink, Identity] | None:
        link = await self._links.get(tenant, wanted)
        if link is None or not link.active:
            return None
        identity = await self._identities.get(tenant, link.identity)
        return None if identity is None else (link, identity)

    async def _link_from_source(
        self,
        channel: Capability,
        account: str,
        tenant: Tenant,
        name: str,
        org_path: tuple[str, ...],
    ) -> Resolution | None:
        now = self._clock.now()
        async with self._work.transaction(tenant):
            identity = await self._identities.get(tenant, name)
            if identity is None:
                identity = Identity(id=name, tenant=tenant, org_path=org_path, created_at=now)
                await self._identities.put(tenant, identity)
                await self._record(
                    tenant,
                    CREATED,
                    "source",
                    actor=name,
                    document={"identity": name, "org_path": list(org_path)},
                )
            await self._put_link(tenant, channel, account, identity.id, LinkOrigin.SOURCE, now)
        return _resolution(identity)

    async def _put_link(
        self,
        tenant: Tenant,
        channel: Capability,
        account: str,
        identity: str,
        origin: LinkOrigin,
        now: datetime,
    ) -> None:
        """Inside the caller's transaction for `tenant`: the link and its ledger entry."""
        existing = await self._links.get(tenant, link_id(channel, account))
        if existing is not None and existing.active:
            raise AlreadyLinked(channel)
        link = ChannelLink(
            id=link_id(channel, account),
            tenant=tenant,
            channel=channel,
            account=account,
            identity=identity,
            origin=origin,
            linked_at=now,
        )
        await self._links.put(tenant, link)
        await self._record(
            tenant,
            LINKED,
            str(origin),
            actor=identity,
            document={"link": link.id, "channel": channel, "identity": identity},
        )

    async def _record(
        self,
        tenant: Tenant,
        kind: str,
        outcome: str,
        *,
        actor: str | None,
        document: dict[str, Any],
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(tenant=tenant, actor=actor),
                outcome=outcome,
                content_digest=_digest_of(document),
            ),
        )


def _resolution(identity: Identity) -> Resolution:
    return Resolution(
        tenant=identity.tenant,
        identity=identity.id,
        org_path=identity.org_path,
        roles=identity.roles,
    )
