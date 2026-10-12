"""A registered version written back as a bundle, so that it can be registered again under a new
version: what a rollback does (UC-4.15, ADR-0091 §5). Pure.

The bundle is the shape registration reads (`control-plane.md` §4, `examples/processes/README.md`):
each step with its `work` beside it, the autonomy statement, the triggers, the inputs, the
service level in seconds and the limits. Registered again, it gives the same version under the
new name, with the author and the reason the rollback gives.
"""

from __future__ import annotations

from typing import Any

from taktus.components.process.domain.model.process import ProcessVersion


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
    return bundle


def next_version(registered: list[str]) -> str:
    """The name a rollback registers under when the person names none: one above the highest
    whole-number version, or the count of versions plus one where none is a whole number,
    never a name already taken."""
    numbers = [int(v) for v in registered if v.isdigit()]
    candidate = (max(numbers) + 1) if numbers else len(registered) + 1
    while str(candidate) in registered:
        candidate += 1
    return str(candidate)
