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


def digest(secret: str) -> str:
    """The digest a code or an account key is kept as; the value itself is kept nowhere."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def link_id(channel: Capability, account: str) -> str:
    """The one identifier a link for this account on this channel can have."""
    return "lnk_" + digest(f"{channel}\n{account}")[:32]


def code_id(code: str) -> str:
    return "lkc_" + digest(code)[:40]


class Identity(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    org_path: tuple[str, ...] = Field(min_length=1)
    """Tenant → department or group → team → project: the first element is the tenant."""
    key_digest: str | None = None
    """The digest of the account key that proves this identity on the control plane's surface;
    None while no key was issued."""
    created_at: datetime

    @model_validator(mode="after")
    def _the_path_starts_at_the_tenant(self) -> Identity:
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
