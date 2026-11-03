"""Identities, the links from channel accounts to them, and the codes a link is made with.

An **identity** is a person, or an automation acting for one, inside one tenant, with its place
in the organisation's structure (`org_path`, control-plane.md §2). Who may act as it on the
control plane's surface is proved by its **account key**, of which only a digest is kept.

A **channel link** maps one account on one channel — as the channel's source system names it,
an opaque identifier — to one identity. Its identifier is derived from the channel and the
account, so that a second link for the same account is the same record and cannot exist beside
the first (UC-1.7). A revoked link is kept, revoked: its history is in the ledger, and the
record says the account is no longer anyone's.

A **link code** is what a person creates in their Taktus account to link an account on one
channel: single-use, valid for `CODE_VALIDITY`, kept only as a digest. Writing it in the channel
from the account proves that the person holds the account; creating it proves that they hold
the identity. Neither a matching name nor a matching address ever links anything.

A **browser session** is what the web app is signed in with (ADR-0119). The instance hands it
out once, in exchange for the account key, as a cookie the page's scripts cannot read. Only the
digest of its token is kept. It ends when its time is up, when the person signs out, and when
the identity's key is replaced.

An **agent key** is what a person's own agent proves the person with on the MCP surface
(ADR-0131). It opens that surface and nothing else, and only its digest is kept. What the agent
may do there beyond reading are the **rights** the person's roles hold: a role's rights are one
record per role, and a right is never granted to a named person (UC-7.3).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1 import Capability, Value

CODE_VALIDITY = timedelta(minutes=30)
CODE_PREFIX = "tkl-"
CODE = re.compile(r"\btkl-[0-9a-f]{24}\b")
"""A link code as it appears in what a sender wrote: the prefix and 96 bits as hex."""
KEY_PREFIX = "tka_"
SESSION_PREFIX = "tks_"
AGENT_KEY_PREFIX = "tkg_"
"""The prefix of an agent key, which only the MCP surface accepts (ADR-0131 §2)."""
SESSION_LIFETIME = timedelta(hours=12)
"""How long a browser session lasts unless the operator sets another time (ADR-0119)."""


def digest(secret: str) -> str:
    """The digest a code or an account key is kept as; the value itself is kept nowhere."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def link_id(channel: Capability, account: str) -> str:
    """The one identifier a link for this account on this channel can have."""
    return "lnk_" + digest(f"{channel}\n{account}")[:32]


def code_id(code: str) -> str:
    return "lkc_" + digest(code)[:40]


def session_id(token: str) -> str:
    """The identifier a browser session is kept under: a digest of its token, never the token."""
    return "ses_" + digest(token)[:40]


class Identity(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    org_path: tuple[str, ...] = Field(min_length=1)
    """Tenant → department or group → team → project: the first element is the tenant."""
    roles: tuple[str, ...] = ()
    """The roles the identity holds. An anchor names the role that decides its act, and the
    identities holding it are the deciders its requests are addressed to (ADR-0042)."""
    key_digest: str | None = None
    """The digest of the account key that proves this identity on the control plane's surface;
    None while no key was issued."""
    agent_key_digest: str | None = None
    """The digest of the agent key the person's own agent proves this identity with on the MCP
    surface; None while none was issued (ADR-0131 §2)."""
    created_at: datetime

    @model_validator(mode="after")
    def _the_path_starts_at_the_tenant(self) -> Identity:
        if any(not r for r in self.roles) or len(set(self.roles)) != len(self.roles):
            raise ValueError(f"the roles of {self.id!r} are names, each once")
        if self.org_path[0] != self.tenant:
            raise ValueError(
                f"the organisational path of {self.id!r} starts at its tenant {self.tenant!r}"
            )
        return self


class LinkOrigin(StrEnum):
    CONFIRMED = "confirmed"
    """The person created a link code in their Taktus account and wrote it from the account."""
    SOURCE = "source"
    """The organisation's identity source mapped the account to the identity."""


class ChannelLink(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    channel: Capability
    account: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    origin: LinkOrigin
    linked_at: datetime
    revoked_at: datetime | None = None
    revoked_by: str | None = Field(default=None, min_length=1)

    @property
    def active(self) -> bool:
        return self.revoked_at is None

    @model_validator(mode="after")
    def _the_identifier_is_derived(self) -> ChannelLink:
        if self.id != link_id(self.channel, self.account):
            raise ValueError("a link's identifier is derived from its channel and account")
        return self


class LinkCode(Value):
    id: str = Field(min_length=1)
    """`code_id(code)`: the code itself is kept nowhere."""
    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    channel: Capability
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def redeemable(self, channel: Capability, now: datetime) -> bool:
        return self.used_at is None and self.channel == channel and now < self.expires_at


class BrowserSession(Value):
    """A sign-in of the web app, held by the browser as a cookie (ADR-0119)."""

    id: str = Field(min_length=1)
    """`session_id(token)`: the token itself is kept nowhere."""
    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    key_digest: str = Field(min_length=1)
    """The digest of the account key the session was exchanged for. A new key for the identity
    ends every session exchanged for the one before."""
    created_at: datetime
    expires_at: datetime
    ended_at: datetime | None = None
    """When the person signed out; None while the session was not ended."""

    def holds(self, identity: Identity, now: datetime) -> bool:
        """Whether the session still proves `identity`: not ended, not expired, and exchanged
        for the key the identity holds now."""
        return (
            self.ended_at is None
            and now < self.expires_at
            and identity.id == self.identity
            and identity.key_digest == self.key_digest
        )


class Right(StrEnum):
    """What a role may let an agent do on the MCP surface beyond reading (ADR-0131 §3)."""

    START = "agent.start"
    """Start a process's active version."""
    ANSWER = "agent.answer"
    """Answer a decision request addressed to the person, and confirm its reading."""
    TAKE_OVER = "agent.take-over"
    """Take over a running step, and hand its result back."""
    STEER = "agent.steer"
    """Send a message to a running step (ADR-0156 §7)."""


class RoleRights(Value):
    """The rights one role of a tenant holds. The record is keyed by the role: there is no
    record a right could be granted to a person in (UC-7.3)."""

    id: str = Field(min_length=1)
    """The role."""
    tenant: str = Field(min_length=1)
    rights: tuple[Right, ...] = ()

    @model_validator(mode="after")
    def _each_right_once(self) -> RoleRights:
        if len(set(self.rights)) != len(self.rights):
            raise ValueError(f"the rights of the role {self.id!r} are named each once")
        return self
