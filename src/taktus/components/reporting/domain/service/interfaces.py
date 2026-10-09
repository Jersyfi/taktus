"""Which failed calls make a broken interface, and the words it is reported in (ADR-0047).

**The rule.** A failed call counts when its cause is unforeseen — the connector answered outside
its contract, the service refused Taktus's authentication, or it answered a status or a shape
the connector does not foresee. A failed call whose cause is transient — unavailable, an answer
that did not arrive, a connector that could not be reached — counts only when a retry did not
resolve it: when the same step of the same run failed transiently through the same interface on
another attempt too. A transient failure that a retry resolved never counts. Nothing else
decides: no model, no estimate, no reading of a reason in words (ADR-0023 requires the same of an
automatic stop).

**One per interface and cause.** Every counted call through the same interface with the same
cause belongs to one broken interface. Once the owner answered its report that it is done, the
broken interface is closed at that moment; a call that fails after it opens a new one.

Pure: failed calls and the closing times in, broken interfaces and texts out.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime

from taktus.components.reporting.domain.model.interface import (
    TRANSIENT,
    UNFORESEEN,
    BrokenInterface,
    FailedCall,
)

WHAT_HAPPENED: dict[str, str] = {
    "contract": "its connector answered outside the connector contract",
    "unauthenticated": "the service refused Taktus's authentication",
    "unexpected": "the service answered with a status or a shape its connector does not foresee",
    "unavailable": "the service stayed unavailable when a failed call was tried again",
    "unknown": "the service's answer did not arrive, also when the call was tried again",
    "unreachable": "its connector could not be reached, also when the call was tried again",
}
"""One phrase per cause token, as the report and the operator's view say it."""

HELD_SHOWN = 10
"""How many runs that stand still a report names one by one; the rest are counted."""


def counted(calls: Iterable[FailedCall]) -> tuple[FailedCall, ...]:
    """The calls that count, in the order they were recorded."""
    ordered = sorted(calls, key=lambda c: c.seq)
    retried = Counter((c.interface, c.run_id, c.step_id) for c in ordered if c.cause in TRANSIENT)
    return tuple(
        c
        for c in ordered
        if c.cause in UNFORESEEN
        or (c.cause in TRANSIENT and retried[(c.interface, c.run_id, c.step_id)] >= 2)
    )


def broken(
    calls: Iterable[FailedCall], closed: Mapping[str, datetime]
) -> tuple[BrokenInterface, ...]:
    """Every broken interface the calls make, in the order each was first met. `closed` holds,
    by identifier, when the owner answered a broken interface's report that it is done."""
    groups: dict[tuple[str, str], list[FailedCall]] = defaultdict(list)
    for call in counted(calls):
        groups[(call.interface, call.cause)].append(call)
    found: list[BrokenInterface] = []
    for (interface, cause), group in groups.items():
        current: list[FailedCall] = []
        for call in group:
            if current:
                ended = closed.get(_made(interface, cause, current).id)
                if ended is not None and call.at > ended:
                    found.append(_made(interface, cause, current))
                    current = []
            current.append(call)
        found.append(_made(interface, cause, current))
    return tuple(sorted(found, key=lambda b: b.first.seq))


def _made(interface: str, cause: str, calls: list[FailedCall]) -> BrokenInterface:
    return BrokenInterface.model_validate(
        {"interface": interface, "cause": cause, "calls": tuple(calls)}
    )


# --- the words ------------------------------------------------------------------------------


def _at(call: FailedCall) -> str:
    return call.at.isoformat(timespec="seconds")


def title(found: BrokenInterface) -> str:
    return f"The interface {found.interface} stopped behaving as its adapter expects"


def needed(found: BrokenInterface) -> tuple[str, ...]:
    return (
        f"A look at the interface {found.interface}: {WHAT_HAPPENED[found.cause]} "
        f"(cause `{found.cause}`). Taktus reports it; the repair is a task.",
    )


def steps(found: BrokenInterface) -> tuple[str, ...]:
    first, last = found.first, found.last
    return (
        f"First failed call: run {first.run_id}, step {first.step_id}, at {_at(first)}.",
        f"Last failed call: run {last.run_id}, step {last.step_id}, at {_at(last)}; "
        f"{len(found.calls)} failed call(s) in all.",
        "Read each failed step's reason in its run, and `taktusctl interfaces` on the instance.",
        "Repair what changed — the credential, the app's installation, the connector — and "
        "resume the runs that stand still.",
    )


def standing_still(found: BrokenInterface) -> tuple[str, ...]:
    held = found.held
    named = tuple(f"Run {run}, at step {step}." for run, step in held[:HELD_SHOWN])
    rest = len(held) - HELD_SHOWN
    return named if rest <= 0 else (*named, f"And {rest} more run(s).")


def shown(found: BrokenInterface, state: str) -> str:
    """The broken interface as the operator reads it, with what became of its report."""
    first, last = found.first, found.last
    held = "; ".join(f"run {run} at step {step}" for run, step in found.held)
    return "\n".join(
        (
            f"Broken interface: {found.interface} — {WHAT_HAPPENED[found.cause]}.",
            f"Cause: {found.cause}. {len(found.calls)} failed call(s).",
            f"First: run {first.run_id}, step {first.step_id}, at {_at(first)}.",
            f"Last: run {last.run_id}, step {last.step_id}, at {_at(last)}.",
            f"Stands still: {held}.",
            f"Report {found.id}: {state}.",
        )
    )
