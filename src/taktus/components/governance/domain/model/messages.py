"""What a tenant rules about its outward messages, and the cases a person answered in
(ADR-0142, UC-7.6).

**Message rules**: the label added to a message a model drafted, the delay after a message is
approved, the quiet hours in which nothing is sent, and the most recipients an outward step
may address without a person. A tenant that configured none holds the shipped default
(NTC-0234): no label, so that no message a model wrote is sent; ten minutes' delay; no quiet
hours; ten recipients.

**A case answered**: a person answered in a case of a process. The process sends nothing more
in that case.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, time, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

DELAY_SECONDS = 600
RECIPIENT_LIMIT = 10
LABEL_LENGTH = 500


class MessageRules(Value):
    """One tenant's rules, stored under the tenant's own identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1, max_length=LABEL_LENGTH)
    """The wording of the label; what the law asks it to say is the tenant's (UC-7.6 §3)."""
    delay_seconds: int = Field(default=DELAY_SECONDS, ge=0)
    quiet_begins: time | None = None
    quiet_ends: time | None = None
    zone: str = "UTC"
    """The zone the quiet hours are read in."""
    recipient_limit: int = Field(default=RECIPIENT_LIMIT, ge=1)
    configured_at: datetime | None = None
    """When it was configured; None for the shipped default, which nobody configured."""

    @model_validator(mode="after")
    def _sound(self) -> MessageRules:
        if self.id != self.tenant:
            raise ValueError(f"message rules are stored under their tenant {self.tenant!r}")
        if (self.quiet_begins is None) != (self.quiet_ends is None):
            raise ValueError("quiet hours have a beginning and an end, or neither")
        if self.quiet_begins is not None and self.quiet_begins == self.quiet_ends:
            raise ValueError("quiet hours begin and end at different times of the day")
        if self.label is not None and not self.label.strip():
            raise ValueError("a label says something")
        self.tz  # noqa: B018 — a zone that cannot be read is refused here, not when sending
        return self

    @property
    def tz(self) -> tzinfo:
        if self.zone == "UTC":
            return UTC
        try:
            return ZoneInfo(self.zone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"{self.zone!r} is not a time zone") from error


def shipped_rules(tenant: str) -> MessageRules:
    """What a tenant that configured nothing holds (NTC-0234)."""
    return MessageRules(id=tenant, tenant=tenant)


class CaseAnswer(Value):
    """A person answered in a case of a process: the process sends nothing more in it."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    process: str = Field(min_length=1)
    case: str = Field(min_length=1)
    answered_at: datetime

    @model_validator(mode="after")
    def _keyed(self) -> CaseAnswer:
        if self.id != case_key(self.process, self.case):
            raise ValueError("a case answer is stored under the key of its process and case")
        return self


def case_key(process: str, case: str) -> str:
    """The identifier of a case of a process: a digest, so that a case identifier of any form
    is a key of the same form."""
    digest = hashlib.sha256(f"{process}\n{case}".encode()).hexdigest()
    return f"case_{digest[:32]}"
