"""A report to the owner: one event that something is needed from them, and everything that
happened to it since (ADR-0045, UC-6.11).

**One event, one record.** A decision request, a need, a date or a failure Taktus noticed about
itself becomes one report. The report is the record the ledger entry `report.raised` points to.
Its three renderings — the repository text, the message in the owner's channel and the view —
are composed from it and from nothing else, so they cannot disagree (`domain/service/rendering.py`).

**Four items or nothing.** A report names what is needed, the steps to provide it, the work that
stands still for want of it, and the date it is needed by (ADR-0028). Each is required here, so a
report without one cannot exist, and the use case that raises one refuses it before anything is
sent.

**What it keeps of a conversation.** Where a delivery went and where an answer was given — the
channel, the address, the thread — and the answer the owner confirmed. Never the text of a
message: what the conversation was stays in the channel.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from taktus.shared.v1 import Value

WORD = r"^[a-z][a-z0-9_]*$"


class ReportKind(StrEnum):
    DECISION = "decision"
    """A decision request addressed to the owner (ADR-0008, ADR-0042)."""
    NEED = "need"
    """Something only the owner can provide (ADR-0028)."""
    DATE = "date"
    """A date the owner must act by."""
    FAILURE = "failure"
    """A failure Taktus noticed about itself (DEC-0058)."""


class ReportState(StrEnum):
    OPEN = "open"
    """Waiting for an answer."""
    REFLECTED = "reflected"
    """An answer was read and its reading sent back; waiting for the person to confirm it."""
    FILED = "filed"
    """The confirmed answer is filed where it belongs."""


class Link(Value):
    """A file, an issue, a pull request or a view the report concerns."""

    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class Offered(Value):
    """One answer the owner may give: an option of a decision request, or the one answer of a
    need, a date or a failure — that it is done."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    recommended: bool = False
    """The option a decision request recommends; its reason is in the steps."""


class DeliveryChannel(StrEnum):
    MESSAGE = "message"
    """The owner's chat channel."""
    TASK = "task"
    """The organisation's ticket system, where one is configured."""


class DeliveryState(StrEnum):
    DELIVERED = "delivered"
    FAILED = "failed"
    """The connector did not deliver it, or no connector serves the configured channel."""
    WITHHELD = "withheld"
    """It was not sent: it would have carried a secret value."""


class Delivery(Value):
    """One attempt to deliver a rendering, and what came of it."""

    channel: DeliveryChannel
    state: DeliveryState
    at: datetime
    reason: str | None = Field(default=None, pattern=WORD)
    """Why it was not delivered, as a token; None when it was."""
    address: str | None = Field(default=None, min_length=1)
    thread: str | None = Field(default=None, min_length=1)
    """For a message: the thread an answer to it is given in."""
    record: str | None = Field(default=None, min_length=1)
    """The record the delivery made in the target system, as the connector names it."""
    url: str | None = Field(default=None, min_length=1)


class Happened(Value):
    """One entry of the report's history: what happened, when, and who acted — an identity, or
    None when Taktus did."""

    at: datetime
    event: str = Field(pattern=WORD)
    by: str | None = Field(default=None, min_length=1)


class Reading(Value):
    """How an answer was read, sent back and waiting for the same person to confirm it."""

    answer: str = Field(min_length=1)
    by: str = Field(min_length=1)
    at: datetime
    kept: bool = False
    """Whether the answer said more than the option; that rest is not acted on."""


class Filed(Value):
    """The confirmed answer, and where it was filed."""

    answer: str = Field(min_length=1)
    by: str = Field(min_length=1)
    at: datetime
    record: str | None = Field(default=None, min_length=1)
    """The record the answer became where it belongs — a decision's register entry."""
    where: str | None = Field(default=None, min_length=1)
    """Where the answer was given: the channel, the address and the thread. The link, never the
    content."""


class Report(Value):
    id: str = Field(min_length=1)
    """The identifier of the event: a decision request's own, or the need's, the date's or the
    failure's. Every rendering carries it."""
    tenant: str = Field(min_length=1)
    kind: ReportKind
    title: str = Field(min_length=1)
    needed: tuple[str, ...] = Field(min_length=1)
    steps: tuple[str, ...] = Field(min_length=1)
    standing_still: tuple[str, ...] = Field(min_length=1)
    due: date
    offered: tuple[Offered, ...] = Field(min_length=1)
    links: tuple[Link, ...] = ()
    raised_at: datetime
    state: ReportState = ReportState.OPEN
    reading: Reading | None = None
    filed: Filed | None = None
    deliveries: tuple[Delivery, ...] = ()
    history: tuple[Happened, ...] = ()

    def message(self) -> Delivery | None:
        """The delivered message an answer is given under; None when none was delivered."""
        delivered = [
            d
            for d in self.deliveries
            if d.channel is DeliveryChannel.MESSAGE and d.state is DeliveryState.DELIVERED
        ]
        return delivered[-1] if delivered else None

    def task(self) -> Delivery | None:
        delivered = [
            d
            for d in self.deliveries
            if d.channel is DeliveryChannel.TASK and d.state is DeliveryState.DELIVERED
        ]
        return delivered[-1] if delivered else None

    def answers_in(self, address: str, thread: str | None) -> bool:
        """Whether a message at this address and in this thread answers this report."""
        message = self.message()
        return (
            message is not None
            and thread is not None
            and message.address == address
            and message.thread == thread
        )

    def offer(self, answer: str) -> Offered:
        return next(o for o in self.offered if o.id == answer)
