"""A person's pause or cancellation of one run, as the tenant keeps it (ADR-0236, UC-1.5).

A **steering request** asks one run to pause or to be cancelled. It is a person's act, recorded
with the identity that asked, and it lands on the run's next step boundary: the step that runs
may finish, up to its hard ceiling (ADR-0005). A run that waits — for a person, after a halt —
is at a boundary already, and the request takes effect at once.

One record per run, keyed by the run's identifier: the request asked last. The ledger holds
every request and when it took effect (`run.pause_asked`, `run.cancel_asked`, `run.halted`
with outcome `paused` or `cancelled`), so that a second request after a resume replaces the
record and loses nothing of the history.

A paused run resumes at its boundary, as every halted run does. A cancelled run never resumes.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from taktus.shared.v1 import Value


class SteeringKind(StrEnum):
    PAUSE = "pause"
    CANCEL = "cancel"


class SteeringState(StrEnum):
    ASKED = "asked"
    """Recorded and acknowledged; the run has not reached its boundary yet."""
    TOOK_EFFECT = "took_effect"
    """The run halted at its boundary with the request's cause."""
    CONFIRMED = "confirmed"
    """That it took effect was said to whoever asked, in the channel they asked in."""


class SteeringReply(Value):
    """Where the second message — that the request took effect — is said: the channel, the
    address and the thread the request arrived in. None for a request without a channel to
    answer in, such as the command line, which waits and prints."""

    channel: str = Field(min_length=1)
    address: str = Field(min_length=1)
    thread: str | None = None


class RunSteering(Value):
    id: str = Field(min_length=1)
    """The run's identifier: one record per run, the request asked last."""
    tenant: str = Field(min_length=1)
    kind: SteeringKind
    requested_by: str = Field(min_length=1)
    """The identity that asked, as the ledger names it."""
    requested_at: datetime
    state: SteeringState = SteeringState.ASKED
    took_effect_at: datetime | None = None
    reply: SteeringReply | None = None

    @property
    def pending(self) -> bool:
        return self.state is SteeringState.ASKED
