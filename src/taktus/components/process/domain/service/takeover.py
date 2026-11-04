"""What registration holds a version's takeover instructions to (ADR-0180 §2). Pure.

The instructions cover the version's steps exactly; a step that names a credential literally
has its entry name it; and no text names a Taktus identifier a person could not look up
without Taktus. Whether the prose is right is not checked here: only a trial finds that.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from taktus.components.process.domain.model.takeover import (
    StepInstructions,
    TakeoverInstructions,
    TakeoverTrial,
)
from taktus.shared.v1 import Step

UNLOOKABLE = (
    (re.compile(r"\$(input|from|run|otherwise)\b|\$\{"), "a template reference"),
    (re.compile(r"\b(ADR|DEC|NTC|NEED)-\d{4}\b|\bUC-\d+\.\d+\b"), "a record of the register"),
    (re.compile(r"\b[a-z]{3}_(?=[0-9a-z]*\d)[0-9a-z]{4,}\b"), "an identifier of an instance"),
)
"""What a person could not look up without Taktus, with what it is."""

MISSING = "a bundle carries its takeover instructions under `takeover` (UC-6.3, ADR-0180)"


def findings(
    instructions: TakeoverInstructions,
    steps: Sequence[Step],
    credentials: Mapping[str, Sequence[str]],
) -> list[str]:
    """Every finding that refuses the instructions; `credentials` is, per step, the
    credentials its work names literally."""
    found: list[str] = []
    ids = [step.id for step in steps]
    found.extend(
        f"the takeover instructions describe {step_id!r}, which is not a step of this process"
        for step_id in instructions.steps
        if step_id not in ids
    )
    found.extend(
        f"the takeover instructions omit the step {step_id!r}: a person could not do it by hand"
        for step_id in ids
        if step_id not in instructions.steps
    )
    for step_id, names in credentials.items():
        entry = instructions.steps.get(step_id)
        if entry is None:
            continue
        pointed = {c.parameter for c in entry.credentials}
        found.extend(
            f"the step {step_id!r} uses the credential {name}, and its takeover instructions "
            "do not say where a person finds it"
            for name in sorted(set(names) - pointed)
        )
    for where, text in texts(instructions):
        for pattern, what in UNLOOKABLE:
            match = pattern.search(text)
            if match is not None:
                found.append(
                    f"the takeover instructions' {where} name {match.group(0)!r}, {what} a "
                    "person could not look up without Taktus"
                )
    return found


def texts(instructions: TakeoverInstructions) -> Iterable[tuple[str, str]]:
    yield "sequence", instructions.sequence
    for step_id, entry in instructions.steps.items():
        for name in ("system", "do", "expertise", "done"):
            yield f"{name} of {step_id!r}", getattr(entry, name)
        for credential in entry.credentials:
            yield f"credential {credential.parameter} of {step_id!r}", credential.where


def rendered(
    instructions: TakeoverInstructions,
    steps: Sequence[Step],
    skills: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """The instructions as a person reads them, in the order the steps run, each with the
    skills it uses at their version in production (`skills`, by step)."""
    return {
        "sequence": instructions.sequence,
        "steps": [
            step_document(step.id, instructions.steps[step.id], skills.get(step.id, ()))
            for step in steps
            if step.id in instructions.steps
        ],
    }


def step_document(
    step_id: str, entry: StepInstructions, skills: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {"step": step_id, **entry.document(), "skills": [dict(s) for s in skills]}


def untried(level: int, trials: Iterable[TakeoverTrial], version: str) -> bool:
    """A version at level 3 or 4 without a passed trial on it (UC-6.3 §2)."""
    return level >= 3 and not any(t.passed and t.process_version == version for t in trials)
