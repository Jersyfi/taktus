"""A broken interface: an interface Taktus depends on that stopped behaving as its adapter
expects, noticed from Taktus's own calls (ADR-0047, issue #100, DEC-0058).

An *interface* is a connector the instance configured, named by its adapter identifier, and the
service behind it. Every call through it that failed in a way that speaks about it is a
*failed call*, recorded by the run with a cause token. A **broken interface** is one interface
and one cause, and every failed call that counts toward it, oldest first: one per interface and
cause, never one per call.

It is not a product finding (UC-6.12, ADR-0046). A finding is what the product lacks; a broken
interface is an interface that worked and stopped. It goes to the owner of the instance, through
the owner-facing channel, as a report of kind `failure` (ADR-0045).

Every field is an identifier, a time, a count or a cause token, each held to a pattern, so that
no content and no person can pass into it (ADR-0006, principle 14).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from taktus.components.reporting.domain.model.finding import RUN_PATTERN, short
from taktus.shared.v1 import StepId, Value

type InterfaceCause = Literal[
    "contract", "unauthenticated", "unexpected", "unavailable", "unknown", "unreachable"
]

UNFORESEEN: frozenset[str] = frozenset({"contract", "unauthenticated", "unexpected"})
"""The interface stopped behaving as its adapter expects; a retry is not the remedy."""
TRANSIENT: frozenset[str] = frozenset({"unavailable", "unknown", "unreachable"})
"""The interface did not answer for now; a retry is the remedy, until a retry fails as well.
The run records both lists' tokens; a test holds them equal to the run's."""

INTERFACE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
ID_PREFIX = "interface-"
"""Every report of a broken interface has an identifier that starts with this."""


class FailedCall(Value):
    """One failed call, as the run recorded it: where in the chain, when, through which
    interface, why, and the run and the step that made it."""

    seq: int = Field(ge=1)
    at: datetime
    interface: str = Field(pattern=INTERFACE_PATTERN, max_length=128)
    cause: InterfaceCause
    run_id: str = Field(pattern=RUN_PATTERN, max_length=128)
    step_id: StepId


class BrokenInterface(Value):
    """One interface, one cause, and every failed call that counts toward it, oldest first."""

    interface: str = Field(pattern=INTERFACE_PATTERN, max_length=128)
    cause: InterfaceCause
    calls: tuple[FailedCall, ...] = Field(min_length=1)

    @property
    def id(self) -> str:
        """The identity of this broken interface, derived and never stored: the interface, the
        cause and its first failed call. It is the identifier of the report to the owner."""
        return ID_PREFIX + short(f"{self.interface}|{self.cause}|{self.calls[0].seq}")

    @property
    def first(self) -> FailedCall:
        return self.calls[0]

    @property
    def last(self) -> FailedCall:
        return self.calls[-1]

    @property
    def held(self) -> tuple[tuple[str, str], ...]:
        """Every run and step a failed call ended, each once, in the order they failed."""
        seen: dict[tuple[str, str], None] = {}
        for call in self.calls:
            seen.setdefault((call.run_id, call.step_id), None)
        return tuple(seen)
