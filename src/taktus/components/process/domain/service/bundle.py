"""A registered version written back as a bundle, so that it can be registered again under a new
version: what a rollback does (UC-4.15, ADR-0091 §5). Pure.

The bundle is the shape registration reads (`control-plane.md` §4, `examples/processes/README.md`):
each step with its `work` beside it, the autonomy statement, the triggers, the inputs, the
service level and the expectation in seconds, the limits, the caps on open work (ADR-0132), the
deadlines (ADR-0133) and the evaluation (ADR-0134). Every field a version declares is written
back, so that a rollback restores the version as it was, its caps included (#611). Registered
again, it gives the same version under the new name, with the author and the reason the
rollback gives.
"""

from __future__ import annotations

from typing import Any

from taktus.components.process.domain.model.process import (
    DeadlineAction,
    DeadlineDeclaration,
    OpenWorkCap,
    ProcessVersion,
)


def bundle_of(
    version: ProcessVersion, *, as_version: str, author: str | None, reason: str
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for step in version.steps:
        document = step.document()
        work = version.work.get(step.id)
        if work is not None:
            document["work"] = dict(work)
        steps.append(document)
    bundle: dict[str, Any] = {
        "id": version.process_id,
        "version": as_version,
        "name": version.name,
        "autonomy": version.autonomy.document(),
        "steps": steps,
        "reason": reason,
    }
    if author is not None:
        bundle["author"] = author
    if version.triggers:
        bundle["triggers"] = [trigger.document() for trigger in version.triggers]
    if version.inputs:
        bundle["inputs"] = {name: given.document() for name, given in version.inputs.items()}
    if version.limits is not None:
        bundle["limits"] = dict(version.limits)
    if version.slo is not None:
        slo = {
            name: value.total_seconds()
            for name, value in (
                ("freshness", version.slo.freshness),
                ("latency", version.slo.latency),
            )
            if value is not None
        }
        if slo:
            bundle["slo"] = slo
    if version.expect is not None:
        expect: dict[str, Any] = {}
        if version.expect.schedule is not None:
            expect["schedule"] = version.expect.schedule
        for name, value in (("gap", version.expect.gap), ("bound", version.expect.bound)):
            if value is not None:
                expect[name] = value.total_seconds()
        bundle["expect"] = expect
    if version.open_work:
        bundle["open_work"] = {kind: _cap(cap) for kind, cap in version.open_work.items()}
    if version.deadlines:
        bundle["deadlines"] = {
            name: _deadline(deadline) for name, deadline in version.deadlines.items()
        }
    if version.evaluation is not None:
        bundle["evaluation"] = version.evaluation.document()
    return bundle


def _cap(cap: OpenWorkCap) -> dict[str, Any]:
    """A cap as `open_work.<kind>` declares it, its interval in seconds."""
    document: dict[str, Any] = {"cap": cap.cap, "check_every": cap.check_every.total_seconds()}
    if cap.reading is not None:
        document["reading"] = cap.reading.document()
    return document


def _deadline(deadline: DeadlineDeclaration) -> dict[str, Any]:
    """A deadline as `deadlines.<name>` declares it (ADR-0133 §1), its durations in seconds."""
    starting: str | dict[str, str] = "run"
    if deadline.after is not None:
        starting = {"after": deadline.after}
    elif deadline.date_input is not None:
        starting = {"date": deadline.date_input}
    document: dict[str, Any] = {
        "from": starting,
        "limit": deadline.limit.total_seconds(),
        "counts": "working" if deadline.working else "calendar",
        "until": {"step": deadline.until},
        "at_limit": _action(deadline.at_limit),
    }
    if deadline.lead is not None:
        document["lead"] = deadline.lead.total_seconds()
    if deadline.at_lead is not None:
        document["at_lead"] = _action(deadline.at_lead)
    return document


def _action(action: DeadlineAction) -> dict[str, Any]:
    """`{remind: <role>}`, `{escalate: <role>}` or `{start: {process, inputs}}`."""
    if action.kind == "start":
        return {"start": {"process": action.process, "inputs": dict(action.inputs)}}
    return {action.kind: action.role}


def next_version(registered: list[str]) -> str:
    """The name a rollback registers under when the person names none: one above the highest
    whole-number version, or the count of versions plus one where none is a whole number,
    never a name already taken."""
    numbers = [int(v) for v in registered if v.isdigit()]
    candidate = (max(numbers) + 1) if numbers else len(registered) + 1
    while str(candidate) in registered:
        candidate += 1
    return str(candidate)
