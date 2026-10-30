"""The identity component's use cases: placing a sender, linking an account, administering.

`IdentityDirectory` serves the identity port (`ports/identity.py`) and the acts around it:

- **Placing a sender.** An active link for the account on the channel names the identity, and
  the identity names its tenant and organisational path. Without one, the organisation's
  identity source is asked, when one is configured, and what it answers becomes a link. Nothing
  else places anybody: a matching name or address is never looked at.
- **Linking an account.** A person proves their identity with its account key and creates a
  link code for one channel; writing the code in that channel from the account links it. A
  second link for an account that has one is refused.
- **Signing in to the web app.** A person exchanges their account key once for a browser
  session (ADR-0119). The session proves the identity until its time is up, until the person
  signs out, or until the identity's key is replaced, whichever comes first.
- **Administering.** An administrator adds an identity, issues a new key for one, lists every
  link of a tenant and revokes one. The next event from a revoked account is from an unknown
  sender.
- **A person's own agent** (ADR-0131). The person, or an administrator, issues an agent key: it
  proves the identity on the MCP surface and nowhere else. An administrator grants a role the
  rights an agent needs to act there, and withdraws them; an identity holds the rights of its
  roles, read at every call.

Every identity added and every link made or revoked is a ledger entry in the same transaction:
`identity.created`, `identity.linked` (outcome `confirmed` or `source`), `identity.unlinked`
(outcome `revoked`); so is every agent key issued, `identity.agent_key_issued`, and every right
granted or withdrawn, `identity.right_granted` and `identity.right_withdrawn`. An
entry carries identifiers and a digest, never the account or a name (ADR-0006); the actor is
the identity that acted, where one did. A sign-in and a sign-out are no entry: when a person
uses the web app is nobody's measure (principle 14, ADR-0119 §6).

An account belongs to at most one identity across every tenant the instance serves: a link is
looked for in each of them, and refused where one is active in any. Which tenants it serves is
asked of `ServedTenants` at every act, so that a tenant created while the instance runs is
served from its creation on (ADR-0104).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from taktus.components.identity.domain.model import (
    AGENT_KEY_PREFIX,
    CODE,
    CODE_PREFIX,
    CODE_VALIDITY,
    KEY_PREFIX,
    SESSION_LIFETIME,
    SESSION_PREFIX,
    BrowserSession,
    ChannelLink,
    Identity,
    LinkCode,
    LinkOrigin,
    Right,
    RoleRights,
    code_id,
    digest,
    link_id,
    session_id,
)
from taktus.ports.clock import Clock, Randomness
from taktus.ports.identity import (
    IdentityResolver,
    IdentitySource,
    Resolution,
    ServedTenants,
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
AGENT_KEY_ISSUED = "identity.agent_key_issued"
RIGHT_GRANTED = "identity.right_granted"
RIGHT_WITHDRAWN = "identity.right_withdrawn"


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
        tenants: ServedTenants,
        identities: Repository[Identity],
        links: Repository[ChannelLink],
        codes: Repository[LinkCode],
        sessions: Repository[BrowserSession],
        rights: Repository[RoleRights],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        randomness: Randomness,
        source: IdentitySource | None = None,
        session_lifetime: timedelta = SESSION_LIFETIME,
    ) -> None:
        self._tenants = tenants
        self._identities = identities
        self._links = links
        self._codes = codes
        self._sessions = sessions
        self._rights = rights
        self._session_lifetime = session_lifetime
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._randomness = randomness
        self._source = source

    async def tenants(self) -> tuple[Tenant, ...]:
        """The tenants the instance serves now."""
        return await self._tenants.served()

    # --- the port ---------------------------------------------------------------------------

    async def resolve(
        self, channel: Capability, account: str, *, tenant: Tenant | None = None
    ) -> Resolution | None:
        served = await self._tenants.served()
        searched = served if tenant is None else (tenant,)
        found = await self._active_link(channel, account, searched)
        if found is not None:
            return _resolution(found[1])
        if self._source is None:
            return None
        answer = await self._source.lookup(channel, account)
        if answer is None or answer.tenant not in searched:
            return None
        if tenant is not None and await self._active_link(channel, account, served):
            return None  # the account is another tenant's; it maps to at most one identity
        return await self._link_from_source(
            channel, account, answer.tenant, answer.identity, answer.org_path
        )

    async def identity(self, tenant: Tenant, identity: str) -> Resolution | None:
        if tenant not in await self._tenants.served():
            return None
        async with self._work.transaction(tenant):
            known = await self._identities.get(tenant, identity)
        return None if known is None else _resolution(known)

    async def unknown_sender(
        self, channel: Capability, account: str, said: str
    ) -> UnknownSenderAnswer:
        served = await self._tenants.served()
        for code in dict.fromkeys(CODE.findall(said)):
            for tenant in served:
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
        if await self._active_link(channel, account, await self._tenants.served()) is not None:
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
        for tenant in await self._tenants.served():
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

    # --- a person, signed in to the web app (ADR-0119) --------------------------------------

    @property
    def session_lifetime(self) -> timedelta:
        """How long a browser session lasts from its sign-in."""
        return self._session_lifetime

    async def sign_in(self, key: str) -> tuple[str, BrowserSession] | None:
        """A browser session for the identity the account key proves, or None. The token is
        returned to be set as the cookie once; only its digest is kept."""
        who = await self.authenticate(key)
        if who is None:
            return None
        token = SESSION_PREFIX + self._randomness.token(32)
        now = self._clock.now()
        session = BrowserSession(
            id=session_id(token),
            tenant=who.tenant,
            identity=who.identity,
            key_digest=digest(key),
            created_at=now,
            expires_at=now + self._session_lifetime,
        )
        async with self._work.transaction(who.tenant):
            await self._sessions.put(who.tenant, session)
        return token, session

    async def session(self, token: str) -> Resolution | None:
        """The identity the browser session proves, or None: a token nobody handed out, a
        session that ended or expired, or one exchanged for a key the identity holds no
        longer."""
        found = await self._session_of(token)
        if found is None:
            return None
        session, identity = found
        return _resolution(identity) if session.holds(identity, self._clock.now()) else None

    async def sign_out(self, token: str) -> bool:
        """The browser session ends now. False when the token names no session that still
        held."""
        found = await self._session_of(token)
        if found is None:
            return False
        session, identity = found
        now = self._clock.now()
        if not session.holds(identity, now):
            return False
        async with self._work.transaction(session.tenant):
            await self._sessions.put(session.tenant, session.model_copy(update={"ended_at": now}))
        return True

    async def _session_of(self, token: str) -> tuple[BrowserSession, Identity] | None:
        if not token.startswith(SESSION_PREFIX):
            return None
        wanted = session_id(token)
        for tenant in await self._tenants.served():
            async with self._work.transaction(tenant):
                session = await self._sessions.get(tenant, wanted)
                identity = (
                    None
                    if session is None
                    else await self._identities.get(tenant, session.identity)
                )
            if session is not None:
                return None if identity is None else (session, identity)
        return None

    # --- a person's own agent (ADR-0131) ------------------------------------------------------

    async def authenticate_agent(self, key: str) -> Resolution | None:
        """The identity whose agent key this is, or None. An account key is not an agent key:
        the MCP surface accepts only the one, the HTTP surface only the other (ADR-0131 §2)."""
        if not key.startswith(AGENT_KEY_PREFIX):
            return None
        wanted = digest(key)
        for tenant in await self._tenants.served():
            async with self._work.transaction(tenant):
                identities = await self._identities.list(tenant)
            for identity in identities:
                if identity.agent_key_digest is not None and hmac.compare_digest(
                    identity.agent_key_digest, wanted
                ):
                    return _resolution(identity)
        return None

    async def issue_agent_key(self, tenant: Tenant, identity: str, *, by: str | None = None) -> str:
        """A new agent key for an identity, returned to be shown once; the one before stops
        working (ADR-0131 §2)."""
        await self._served(tenant)
        key = AGENT_KEY_PREFIX + self._randomness.token(32)
        async with self._work.transaction(tenant):
            existing = await self._identities.get(tenant, identity)
            if existing is None:
                raise UnknownIdentity(tenant, identity)
            await self._identities.put(
                tenant, existing.model_copy(update={"agent_key_digest": digest(key)})
            )
            await self._record(
                tenant,
                AGENT_KEY_ISSUED,
                "issued",
                actor=by or identity,
                document={"identity": identity},
            )
        return key

    async def rights(self, who: Resolution) -> frozenset[Right]:
        """The rights the identity holds through its roles, as they are now (ADR-0131 §3)."""
        held: set[Right] = set()
        async with self._work.transaction(who.tenant):
            for role in who.roles:
                found = await self._rights.get(who.tenant, role)
                if found is not None:
                    held.update(found.rights)
        return frozenset(held)

    async def granted(self, tenant: Tenant) -> list[RoleRights]:
        """Every role of the tenant that holds a right, by role."""
        await self._served(tenant)
        async with self._work.transaction(tenant):
            listed = await self._rights.list(tenant)
        return sorted((r for r in listed if r.rights), key=lambda r: r.id)

    async def grant(
        self, tenant: Tenant, role: str, right: Right, *, by: str | None = None
    ) -> RoleRights:
        """The role holds the right from now on; granting one it holds changes nothing."""
        return await self._set_right(tenant, role, right, held=True, by=by)

    async def withdraw(
        self, tenant: Tenant, role: str, right: Right, *, by: str | None = None
    ) -> RoleRights:
        """The role holds the right no longer; withdrawing one it does not hold changes
        nothing."""
        return await self._set_right(tenant, role, right, held=False, by=by)

    async def _set_right(
        self, tenant: Tenant, role: str, right: Right, *, held: bool, by: str | None
    ) -> RoleRights:
        await self._served(tenant)
        async with self._work.transaction(tenant):
            existing = await self._rights.get(tenant, role) or RoleRights(id=role, tenant=tenant)
            if (right in existing.rights) == held:
                return existing
            kept = [r for r in existing.rights if r is not right]
            rights = sorted([*kept, right] if held else kept, key=lambda r: r.value)
            changed = RoleRights(id=role, tenant=tenant, rights=tuple(rights))
            await self._rights.put(tenant, changed)
            await self._record(
                tenant,
                RIGHT_GRANTED if held else RIGHT_WITHDRAWN,
                "granted" if held else "withdrawn",
                actor=by,
                document={"role": role, "right": right.value},
            )
        return changed

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
        await self._served(tenant)
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
        await self._served(tenant)
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

    async def role_holders(self, tenant: Tenant) -> dict[str, int]:
        """Per role the tenant's identities hold, how many hold it: the tenant's structure as
        a count, never the names (ADR-0146). A figure by role is shown only where at least two
        hold it (ADR-0015)."""
        async with self._work.transaction(tenant):
            identities = await self._identities.list(tenant)
        held: dict[str, int] = {}
        for identity in identities:
            for role in identity.roles:
                held[role] = held.get(role, 0) + 1
        return dict(sorted(held.items()))

    async def role_units(self, tenant: Tenant) -> dict[str, tuple[str, ...]]:
        """Per role the tenant's identities hold, the units of the structure its holders sit
        in, each as its `org_path` joined by `/`: where a role is, never who holds it
        (ADR-0159 §6)."""
        async with self._work.transaction(tenant):
            identities = await self._identities.list(tenant)
        units: dict[str, set[str]] = {}
        for identity in identities:
            for role in identity.roles:
                units.setdefault(role, set()).add("/".join(identity.org_path))
        return {role: tuple(sorted(found)) for role, found in sorted(units.items())}

    async def roles(self, tenant: Tenant) -> frozenset[str]:
        """Every role an identity of the tenant holds: registration's port (ADR-0146)."""
        return frozenset(await self.role_holders(tenant))

    async def issue_key(self, tenant: Tenant, identity: str, *, by: str | None = None) -> str:
        """A new account key for an identity; the old one stops working, and so does every
        browser session exchanged for it (ADR-0119)."""
        await self._served(tenant)
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
        await self._served(tenant)
        async with self._work.transaction(tenant):
            return sorted(await self._links.list(tenant), key=lambda link: link.linked_at)

    async def revoke(self, tenant: Tenant, link: str, *, by: str | None = None) -> ChannelLink:
        """The link is revoked; the account is from an unknown sender from now on."""
        await self._served(tenant)
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

    async def _served(self, tenant: Tenant) -> None:
        if tenant not in await self._tenants.served():
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
