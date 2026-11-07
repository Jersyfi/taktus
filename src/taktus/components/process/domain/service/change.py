"""Whether a change of a process lies within the frame its owner declares (UC-4.3, ADR-0255).
Pure: the active version and the changed one in, every change in words out.

`always_outside` names every change that is outside whatever the frame says: a level raised,
a method kind changed, an exactness class loosened, an anchor the version carries removed or
narrowed, a step's reach widened, the frame changed. `changes` names every change with its kind
of §1 — `work`, `step_added`, `checks_added`, `takeover` — or None where it is of no kind the
frame can list. `verdict` puts them together: a change is within the frame when nothing is
always outside and the frame lists the kind of every change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from taktus.components.process.domain.model.process import (
    STRICTNESS,
    FrameKind,
    ProcessVersion,
)
from taktus.components.process.domain.service import autonomy
from taktus.shared.v1 import Check, CheckKind, Method, Step

type Change = tuple[FrameKind | None, str]


@dataclass(frozen=True)
class Verdict:
    within: bool
    changes: tuple[str, ...]
    """Every change against the active version, in words."""
    outside: tuple[str, ...]
    """Why it is outside the frame; empty where it is within."""


def verdict(before: ProcessVersion, after: ProcessVersion) -> Verdict:
    found = changes(before, after)
    reasons = always_outside(before, after)
    allowed = set(() if before.frame is None else before.frame.changes)
    reasons.extend(
        f"{words}: a change the frame does not list"
        if kind is None
        else f"{words}: of the kind {kind!r}, which the frame does not list"
        for kind, words in found
        if kind is None or kind not in allowed
    )
    if not found and not reasons:
        reasons.append("the bundle changes nothing")
    return Verdict(
        within=not reasons,
        changes=tuple(words for _, words in found),
        outside=tuple(dict.fromkeys(reasons)),
    )


def always_outside(before: ProcessVersion, after: ProcessVersion) -> list[str]:
    """Every change outside the frame whatever it says (ADR-0255 §2)."""
    found = [
        f"raises {raised} (ADR-0026)" for raised in autonomy.raises(before.autonomy, after.autonomy)
    ]
    old = {step.id: step for step in before.steps}
    new = {step.id: step for step in after.steps}
    for step_id, was in old.items():
        now = new.get(step_id)
        if now is None:
            if was.method is Method.HUMAN:
                found.append(f"removes the person's step {step_id!r}, an anchor (ADR-0008)")
            found.extend(_anchors_lost(step_id, was.checks or (), ()))
            continue
        if now.method is not was.method:
            found.append(
                f"changes the method of step {step_id!r} from {was.method} to {now.method} "
                "(ADR-0004)"
            )
        if _looser(was, now):
            found.append(
                f"loosens the exactness of step {step_id!r} from {was.exactness} to "
                f"{now.exactness or 'none'} (ADR-0014)"
            )
        found.extend(_anchors_lost(step_id, was.checks or (), now.checks or ()))
    before_reach = _reach(before)
    for step_id, reach in _reach(after).items():
        known = set().union(*before_reach.values()) if before_reach else set()
        own = before_reach.get(step_id, set())
        for item in sorted(reach - own):
            kind, _, name = item.partition(":")
            if kind == "uses" and name in known:
                continue
            found.append(f"widens what step {step_id!r} may reach: {kind} {name} (UC-7.3)")
    if before.frame != after.frame:
        found.append("changes the frame, which is the owner's (ADR-0255 §1)")
    return found


def changes(before: ProcessVersion, after: ProcessVersion) -> list[Change]:
    """Every change against the active version, each with its kind of the frame, or None."""
    found: list[Change] = []
    old = {step.id: step for step in before.steps}
    new = {step.id: step for step in after.steps}
    for step_id in old.keys() - new.keys():
        found.append((None, f"step {step_id}: removed"))
    for step in after.steps:
        was = old.get(step.id)
        if was is None:
            found.append(("step_added", f"step {step.id}: added"))
            continue
        if before.work.get(step.id) != after.work.get(step.id):
            same_call = _call(before.work.get(step.id)) == _call(after.work.get(step.id))
            found.append(("work" if same_call else None, f"step {step.id}: its work changed"))
        rest = {"checks", "work"}
        if was.model_dump(exclude=rest) != step.model_dump(exclude=rest):
            found.append((None, f"step {step.id}: its declaration changed"))
        if (was.checks or ()) != (step.checks or ()):
            kept = tuple(step.checks or ())[: len(was.checks or ())] == tuple(was.checks or ())
            found.append(
                (
                    "checks_added" if kept else None,
                    f"step {step.id}: checks added" if kept else f"step {step.id}: checks changed",
                )
            )
    if before.takeover != after.takeover:
        found.append(("takeover", "the takeover instructions changed"))
    rest = {"version", "steps", "work", "takeover", "author", "reason", "change", "frame"}
    for name in sorted(set(ProcessVersion.model_fields) - rest):
        if getattr(before, name) != getattr(after, name):
            found.append((None, f"`{name}` changed"))
    return found


def _call(work: Mapping[str, Any] | None) -> tuple[Any, ...]:
    """What a step's work calls: its operation, its capability and what it waits on."""
    given = work or {}
    until = given.get("until") if isinstance(given.get("until"), Mapping) else {}
    return (given.get("operation"), given.get("capability"), (until or {}).get("operation"))


def _looser(was: Step, now: Step) -> bool:
    if was.exactness is None:
        return False
    if now.exactness is None:
        return True
    return STRICTNESS.index(now.exactness) > STRICTNESS.index(was.exactness)


def _anchors_lost(step_id: str, was: Sequence[Check], now: Sequence[Check]) -> list[str]:
    """An approval or a sampling check removed, or held to less (ADR-0255 §2)."""
    found: list[str] = []
    for check in was:
        if check.kind is CheckKind.APPROVAL:
            same = [c for c in now if c.kind is CheckKind.APPROVAL and c.role == check.role]
            if not same or all((c.threshold or 0) > (check.threshold or 0) for c in same):
                found.append(f"narrows the approval of step {step_id!r} by {check.role} (ADR-0008)")
        if check.kind is CheckKind.SAMPLING:
            same = [c for c in now if c.kind is CheckKind.SAMPLING and c.role == check.role]
            if not same or all((c.share or 0) < (check.share or 0) for c in same):
                found.append(f"narrows the sampling of step {step_id!r} by {check.role} (ADR-0008)")
    return found


def _reach(version: ProcessVersion) -> dict[str, set[str]]:
    """What each step may reach: the actions it uses, the credentials and hosts its work names."""
    reach: dict[str, set[str]] = {}
    for step in version.steps:
        work = version.work.get(step.id) or {}
        items = {f"uses:{a}" for a in autonomy.actions_used((step,), version.work)}
        items.update(f"credential:{name}" for name in _named(work, "credentials"))
        items.update(
            f"host:{host}" for host in work.get("allowed_hosts") or () if isinstance(host, str)
        )
        reach[step.id] = items
    return reach


def _named(node: Any, key: str) -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for name, value in node.items():
            if name == key and isinstance(value, list):
                found.extend(
                    str(item.get("name")) if isinstance(item, Mapping) else str(item)
                    for item in value
                )
            else:
                found.extend(_named(value, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(_named(item, key))
    return found
