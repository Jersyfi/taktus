"""What a failed call says about the interface it went through (ADR-0047, issue #100).

Every call a connector step makes goes through an *interface*: the connector the instance
configured for the step's capability, named by its adapter identifier, and the service behind it.
When a call fails, a rule reads its cause and says whether the failure speaks about that
interface. Nothing else decides: no model, no estimate, no reading of a reason in words
(ADR-0023 requires the same of an automatic stop).

Two kinds of failure speak about the interface:

- **unforeseen** — the interface stopped behaving as its adapter expects. The connector answered
  outside its contract (`contract`); the service refused Taktus's authentication
  (`unauthenticated`); the service answered a status or a shape the connector does not foresee
  (`unexpected`). A retry is not their remedy.
- **transient** — the interface did not answer for now. The connector's target was unavailable
  (`unavailable`), its answer did not arrive (`unknown`), or the connector itself could not be
  reached (`unreachable`). A retry is their remedy, and only a retry that fails as well says
  that the interface stopped working (`reporting`'s rule reads that).

Every other cause — `forbidden`, `not_found`, `invalid`, `conflict` — is the service answering
about the input or the state, as the contract foresees and the adapter expects. It says nothing
about the interface.

Every failure that speaks about the interface is written to the ledger as `interface.failed`,
beside the step's own entry: the run and the step, the adapter, and the cause token as its
outcome. The ledger is what a broken interface is noticed from, and it holds no text (ADR-0006).

Pure: a cause in, a token or None out.
"""

from __future__ import annotations

from taktus.ports.connector import Cause

RECORD_KIND = "interface.failed"
"""The ledger entry of a failed call that speaks about its interface."""

CONTRACT = "contract"
"""The connector answered, outside its contract."""
UNREACHABLE = "unreachable"
"""The connector did not answer at all."""

UNFORESEEN: frozenset[str] = frozenset({CONTRACT, "unauthenticated", "unexpected"})
TRANSIENT: frozenset[str] = frozenset({"unavailable", "unknown", UNREACHABLE})
"""The two lists are the reporting component's too; a test holds them equal."""

_OF_CAUSE: dict[Cause, str | None] = {
    Cause.UNAUTHENTICATED: "unauthenticated",
    Cause.UNEXPECTED: "unexpected",
    Cause.UNAVAILABLE: "unavailable",
    Cause.UNKNOWN: "unknown",
    Cause.FORBIDDEN: None,
    Cause.NOT_FOUND: None,
    Cause.INVALID: None,
    Cause.CONFLICT: None,
}


def of_cause(cause: Cause) -> str | None:
    """The token a classified failure is recorded with, or None when its cause is the service
    answering about the input or the state."""
    return _OF_CAUSE[cause]
