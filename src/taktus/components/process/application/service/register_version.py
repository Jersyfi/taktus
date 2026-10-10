"""Use case: a process bundle becomes a validated process version and is stored.

The bundle arrives as data — the parsed document, whatever the file format was — and leaves as
a `ProcessVersion` or as `InvalidProcess` naming every finding. Field by field, the shape is the
one docs/architecture/control-plane.md §4 describes and `examples/processes/README.md` shows.

Registering is where an autonomy level can rise, because the levels live in the version's
statement (ADR-0026). A version that raises a level over the one it replaces is stored only with
a person's approval and the quality history the replaced version names, read from the ledger;
otherwise it is refused with `RaiseRefused`, and the refusal is a ledger entry,
`autonomy.refused`. An admitted raise is `autonomy.raised`, with the approving person as its
actor (ADR-0039, `domain.service.autonomy`). This is the one code path that stores a version.

Registering is also where a version that would hand the instance its own platform is refused:
a step naming a credential declared to administer the platform the instance runs on, or one
declared about nothing, once the instance names its platform (ADR-0025, ADR-0052, DEC-0133).
The refusal is a ledger entry, `process.refused`, and the version is not stored. A credential
named by a reference — `{ $input: ... }` — is known only when a run resolves it; admission
checks it then.
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
    Process,
    ProcessVersion,
    RaiseRefused,
    Slo,
    Trigger,
)
from taktus.components.process.domain.service import autonomy
from taktus.ports.administration import Administration
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Autonomy, LedgerRefs, Step

type Document = Mapping[str, Any]

DURATION = re.compile(r"^(\d+)\s*(s|m|h|d)$")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


@dataclass(frozen=True)
class RegisterProcessVersion:
    bundle: Document
    tenant: Tenant
    by: str | None = None
    """The identity that registers the version and so makes it active; its schedule triggers
    act for that identity."""
    approved_by: str | None = None
    """The person who approves a raise of an autonomy level this version makes. A version that
    raises no level needs no approval. Who holds the right to approve is a right per role
    (UC-7.3); until it exists, any identity the tenant knows may."""


class RegisterProcessVersionHandler:
    """Stores the version. With `processes`, the version registered last becomes the process's
    active version: the one whose schedule triggers the scheduler fires (ADR-0035). A version
    that raises an autonomy level is admitted as the module says, against the history in the
    `ledger`, where the raise or its refusal is recorded."""

    def __init__(
        self,
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
        processes: Repository[Process] | None = None,
        *,
        ledger: Ledger,
        administration: Administration | None = None,
    ) -> None:
        self._versions = versions
        self._work = work
        self._processes = processes
        self._ledger = ledger
        self._administration = administration or Administration()

    async def execute(self, command: RegisterProcessVersion) -> ProcessVersion:
        version = parse_bundle(command.bundle)
        tenant = command.tenant
        refusals = [
            r
            for step_id, names in credentials_named(version).items()
            if (r := self._administration.refusal(step_id, names)) is not None
        ]
        if refusals:
            async with self._work.transaction(tenant):
                await self._record(
                    tenant, version, "process.refused", "administers", command, actor=command.by
                )
            raise InvalidProcess(tuple(refusals))
        refused: autonomy.RaiseVerdict | None = None
        async with self._work.transaction(tenant):
            replaced = await self._replaced(tenant, version)
            raised = [
                r for old in replaced for r in autonomy.raises(old.autonomy, version.autonomy)
            ]
            if raised:
                verdict = await self._verdict(tenant, version, replaced, raised, command)
                if verdict.admitted:
                    await self._record(tenant, version, "autonomy.raised", "raised", command)
                else:
                    # The refusal is recorded and committed; the version is not stored.
                    refused = verdict
                    outcome = verdict.refusal or "refused"
                    await self._record(tenant, version, "autonomy.refused", outcome, command)
            if refused is None:
                await self._versions.put(tenant, version)
                if self._processes is not None:
                    await self._processes.put(
                        tenant,
                        Process(
                            id=version.process_id,
                            name=version.name,
                            active_version=version.version,
                            activated_by=command.by,
                        ),
                    )
        if refused is not None:
            raise RaiseRefused(version.ref, refused.findings)
        return version

    async def _replaced(self, tenant: Tenant, version: ProcessVersion) -> list[ProcessVersion]:
        """The version the new one replaces: the process's active version where it is known;
        otherwise every stored version of the process, so that a raise over any is one."""
        if self._processes is not None:
            process = await self._processes.get(tenant, version.process_id)
            if process is not None and process.active_version is not None:
                ref = f"{version.process_id}@{process.active_version}"
                active = await self._versions.get(tenant, ref)
                if active is not None:
                    return [active]
        return [v for v in await self._versions.list(tenant) if v.process_id == version.process_id]

    async def _verdict(
        self,
        tenant: Tenant,
        version: ProcessVersion,
        replaced: list[ProcessVersion],
        raised: list[str],
        command: RegisterProcessVersion,
    ) -> autonomy.RaiseVerdict:
        named = [old.autonomy.history for old in replaced if old.autonomy.history is not None]
        required = max(named) if len(named) == len(replaced) else None
        entries = await self._ledger.entries(tenant)
        quality = autonomy.history(entries, version.process_id)
        return autonomy.verdict(
            list(dict.fromkeys(raised)),
            approved_by=command.approved_by,
            required=required,
            quality=quality,
        )

    async def _record(
        self,
        tenant: Tenant,
        version: ProcessVersion,
        kind: str,
        outcome: str,
        command: RegisterProcessVersion,
        *,
        actor: str | None = None,
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(
                    tenant=tenant,
                    process_version=version.ref,
                    actor=actor if actor is not None else command.approved_by,
                ),
                outcome=outcome,
            ),
        )


def credentials_named(version: ProcessVersion) -> dict[str, list[str]]:
    """Per step, the credentials its work names literally: under `credentials`, wherever the
    work carries it — a connector call, a wait on one, a worker's assignment. A name given by a
    reference is not known before a run resolves it, and is left to admission."""
    named: dict[str, list[str]] = {}
    for step_id, work in version.work.items():
        names = _names(work)
        if names:
            named[str(step_id)] = names
    return named


def _names(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "credentials" and isinstance(value, list):
                found.extend(
                    item["name"]
                    for item in value
                    if isinstance(item, Mapping) and isinstance(item.get("name"), str)
                )
            else:
                found.extend(_names(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_names(item))
    return found


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
            autonomy=_autonomy(bundle.get("autonomy")),
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


def _autonomy(raw: Any) -> Autonomy:
    """`autonomy` names the level, the reason and what is missing to go higher (ADR-0026). A
    bare level is refused with the shape it lacks, so that no process runs without its reason."""
    if raw is None or isinstance(raw, int | str):
        raise InvalidProcess(
            (
                "`autonomy` names the level, its reason and what is missing to go higher — "
                "`autonomy: { level: 3, reason: ..., toward_next: ... }` (ADR-0026); "
                f"found {raw!r}",
            )
        )
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`autonomy` is not a mapping",))
    try:
        return Autonomy.model_validate(raw)
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("autonomy", error))) from error


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
