"""Use case: a process bundle becomes a validated process version and is stored.

The bundle arrives as data — the parsed document, whatever the file format was — and leaves as
a `ProcessVersion` or as `InvalidProcess` naming every finding. Field by field, the shape is the
one docs/architecture/control-plane.md §4 describes and `examples/processes/README.md` shows.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from taktus.components.process.domain.model import (
    InputDeclaration,
    InvalidProcess,
    ProcessVersion,
    Slo,
    Trigger,
)
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Step

type Document = Mapping[str, Any]

DURATION = re.compile(r"^(\d+)\s*(s|m|h|d)$")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


@dataclass(frozen=True)
class RegisterProcessVersion:
    bundle: Document
    tenant: Tenant


class RegisterProcessVersionHandler:
    def __init__(self, versions: Repository[ProcessVersion], work: UnitOfWork) -> None:
        self._versions = versions
        self._work = work

    async def execute(self, command: RegisterProcessVersion) -> ProcessVersion:
        version = parse_bundle(command.bundle)
        async with self._work.transaction(command.tenant):
            await self._versions.put(command.tenant, version)
        return version


def parse_bundle(bundle: Document) -> ProcessVersion:
    """The bundle document as a process version, or InvalidProcess with every finding."""
    findings: list[str] = []
    steps: list[Step] = []
    work: dict[str, Mapping[str, Any]] = {}
    raw_steps = bundle.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise InvalidProcess(("a bundle lists at least one step under `steps`",))
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, Mapping):
            findings.append(f"step {index + 1} is not a mapping")
            continue
        fields = dict(raw)
        step_work = fields.pop("work", None)
        try:
            step = Step.model_validate(fields)
        except ValidationError as error:
            findings.extend(_describe(f"step {fields.get('id', index + 1)!r}", error))
            continue
        steps.append(step)
        if step_work is not None:
            if not isinstance(step_work, Mapping):
                findings.append(f"step {step.id!r}: `work` is not a mapping")
            else:
                work[step.id] = step_work
    if findings:
        raise InvalidProcess(tuple(findings))
    try:
        return ProcessVersion(
            process_id=bundle.get("id", ""),
            version=str(bundle.get("version", "")),
            name=bundle.get("name", ""),
            autonomy_level=bundle.get("autonomy", 2),
            steps=tuple(steps),
            triggers=tuple(Trigger.model_validate(t) for t in bundle.get("triggers", ())),
            slo=_slo(bundle.get("slo")),
            work=work,
            limits=bundle.get("limits"),
            inputs=_inputs(bundle.get("inputs")),
            author=bundle.get("author"),
            reason=bundle.get("reason"),
        )
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("bundle", error))) from error


def _inputs(raw: Any) -> dict[str, InputDeclaration]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`inputs` is not a mapping of name to declaration",))
    declared: dict[str, InputDeclaration] = {}
    for name, declaration in raw.items():
        try:
            declared[str(name)] = InputDeclaration.model_validate(declaration)
        except ValidationError as error:
            raise InvalidProcess(tuple(_describe(f"input {name!r}", error))) from error
    return declared


def _slo(raw: Any) -> Slo | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`slo` is not a mapping",))
    return Slo(
        freshness=_duration(raw.get("freshness")),
        latency=_duration(raw.get("latency")),
    )


def _duration(raw: Any) -> timedelta | None:
    """`24h`, `30m`, `90s`, `2d`, or a number of seconds."""
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return timedelta(seconds=float(raw))
    match = DURATION.match(str(raw).strip())
    if match is None:
        raise InvalidProcess((f"{raw!r} is not a duration such as 24h, 30m or 90s",))
    return timedelta(seconds=int(match.group(1)) * UNIT_SECONDS[match.group(2)])


def _describe(where: str, error: ValidationError) -> list[str]:
    out = []
    for item in error.errors():
        location = ".".join(str(p) for p in item["loc"])
        message = item["msg"].removeprefix("Value error, ")
        out.append(f"{where}: {location + ': ' if location else ''}{message}")
    return out
