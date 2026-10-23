"""Use case: a process bundle becomes a validated process version and is stored.

The bundle arrives as data — the parsed document, whatever the file format was — and leaves as
a `ProcessVersion` or as `InvalidProcess` naming every finding. Field by field, the shape is the
one docs/architecture/control-plane.md §4 describes and `examples/processes/README.md` shows.

Registering is where an autonomy level can rise, because the levels live in the version's
statement (ADR-0026). A version that raises a level over the one it replaces is stored only with
a person's approval and the quality history the replaced version names, read from the ledger;
otherwise it is refused with `RaiseRefused`, and the refusal is a ledger entry,
`autonomy.refused`. An admitted raise is `autonomy.raised`, with the approving person as its
actor (ADR-0039, `domain.service.autonomy`). The replaced version is measured as it runs now:
a level the governance component lowered by rule counts as its level, so that a level that
fell rises again only this way (ADR-0110). This is the one code path that stores a version.

Registering is where a cap on open work changes, and only a person changes it: a version whose
caps differ from the version it replaces is stored only with a person's approval
(`approved_by`), recorded as `open_work.changed`. Without one the attempt is recorded as
`open_work.refused` and the version is refused (ADR-0132 §3).

Registering is also where a version that would hand the instance its own platform is refused:
a step naming a credential declared to administer the platform the instance runs on, or one
declared about nothing, once the instance names its platform (ADR-0025, ADR-0052, DEC-0133).
The refusal is a ledger entry, `process.refused`, and the version is not stored. A credential
named by a reference — `{ $input: ... }` — is known only when a run resolves it; admission
checks it then.

Registering is where an `exact` step must say how it becomes exact: one that declares no check
from the catalogue is refused, with the catalogue in the finding, and so is a version whose
exactness statement could not be complete (UC-4.13, UC-6.9, ADR-0082). Versions stored before
are read as they are.

Registering is where a step on a trained model must carry its model's evaluation on held-out
cases, of the very file it pins: a version without it, or with one that failed, is refused
(UC-8.4 §2, ADR-0114, `domain.service.evaluation`).

Registering is where a step's frame must hold: a scope names its subject from the run's
inputs, and an analytic step reaches its source only, which the tenant declares free of
personal fields (UC-7.7, ADR-0130, `domain.service.frame`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from taktus.components.process.domain.model import (
    Expect,
    InputDeclaration,
    InvalidProcess,
    OpenWorkCap,
    Process,
    ProcessVersion,
    RaiseRefused,
    Slo,
    Trigger,
)
from taktus.components.process.domain.model.exactness import (
    ExactnessStatement,
    InvalidStatement,
)
from taktus.components.process.domain.service import autonomy, evaluation, exactness, frame
from taktus.components.process.domain.service.quality import QUALITY
from taktus.components.process.ports import FreeSources, LoweredLevels, LoweredVersions
from taktus.ports.administration import Administration
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Autonomy, LedgerRefs, Step

type Document = Mapping[str, Any]

CAP_CHANGED = "open_work.changed"
"""A version changed a cap on open work with a person's approval (ADR-0132 §3)."""
CAP_REFUSED = "open_work.refused"
"""A version that changes a cap on open work was refused for want of a person's approval."""

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
    """The person who approves a raise of an autonomy level this version makes, or a change of
    its caps on open work (ADR-0132). A version that does neither needs no approval. Who holds
    the right to approve is a right per role (UC-7.3); until it exists, any identity the tenant
    knows may."""


class RegisterProcessVersionHandler:
    """Stores the version. With `processes`, the version registered last becomes the process's
    active version: the one whose schedule triggers the scheduler fires (ADR-0035). A version
    that raises an autonomy level is admitted as the module says, against the history in the
    `ledger`, where the raise or its refusal is recorded. With `clock`, the process records when
    its version became active: an event received before it starts nothing (ADR-0048 §6)."""

    def __init__(
        self,
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
        processes: Repository[Process] | None = None,
        *,
        ledger: Ledger,
        administration: Administration | None = None,
        clock: Clock | None = None,
        lowered: LoweredVersions | None = None,
        sources: FreeSources | None = None,
    ) -> None:
        self._sources = sources
        """Which sources the tenant declares free of personal fields (ADR-0130). None: the run
        alone asks, at every call of an analytic step."""
        self._lowered = lowered
        """The levels a version was lowered to by rule (ADR-0110): a version above them raises
        a level. None: no level was lowered."""
        self._versions = versions
        self._work = work
        self._processes = processes
        self._ledger = ledger
        self._administration = administration or Administration()
        self._clock = clock

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
        undeclared = await self._undeclared(tenant, version)
        if undeclared:
            raise InvalidProcess(tuple(undeclared))
        refused: autonomy.RaiseVerdict | None = None
        capped: str | None = None
        lowerings = await self._lowerings(tenant, version)
        async with self._work.transaction(tenant):
            stored = await self._versions.get(tenant, version.ref)
            # A registered version never changes: the runs that name it, their ledger and their
            # provenance, describe what it was. The same content again is the stored version,
            # and registering it switches the process on again (ADR-0066 §5); another content
            # needs a version of its own (#377).
            same = stored is not None and _content(stored) == _content(version)
            if stored is not None and not same:
                raise InvalidProcess(
                    (
                        f"{version.ref} is registered with another content, and a registered "
                        "version never changes: give the bundle a new version",
                    )
                )
            replaced = await self._replaced(tenant, version)
            raised = [
                r
                for old in replaced
                for r in autonomy.raises(self._running(old, lowerings), version.autonomy)
                if old.ref != version.ref
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
                capped = await self._caps_changed(tenant, version, replaced, command)
            if refused is None and capped is None:
                if not same:
                    await self._versions.put(tenant, version)
                if self._processes is not None:
                    await self._processes.put(
                        tenant,
                        Process(
                            id=version.process_id,
                            name=version.name,
                            active_version=version.version,
                            activated_by=command.by,
                            activated_at=None if self._clock is None else self._clock.now(),
                        ),
                    )
        if refused is not None:
            raise RaiseRefused(version.ref, refused.findings)
        if capped is not None:
            raise InvalidProcess((capped,))
        return stored if same and stored is not None else version

    async def _caps_changed(
        self,
        tenant: Tenant,
        version: ProcessVersion,
        replaced: list[ProcessVersion],
        command: RegisterProcessVersion,
    ) -> str | None:
        """Only a person changes a cap on open work (ADR-0132 §3). A version whose caps differ
        from the version it replaces is stored only with a person's approval, recorded as
        `open_work.changed` with the person as actor. Without one the attempt is recorded as
        `open_work.refused`, with whoever registered as actor, and the finding is returned:
        the version is not stored."""
        changed = [
            old.ref
            for old in replaced
            if old.ref != version.ref and dict(old.open_work) != dict(version.open_work)
        ]
        if not changed:
            return None
        if command.approved_by is not None:
            await self._record(tenant, version, CAP_CHANGED, "changed", command)
            return None
        await self._record(tenant, version, CAP_REFUSED, "no_approval", command, actor=command.by)
        return (
            f"{version.ref} changes the cap on open work of {', '.join(changed)}; only a person "
            "changes a cap, and the version is registered only with that person's approval "
            "(ADR-0132)"
        )

    async def _undeclared(self, tenant: Tenant, version: ProcessVersion) -> list[str]:
        """Every analytic step whose source the tenant does not declare free of personal
        fields (UC-7.7 §2)."""
        if self._sources is None:
            return []
        return [
            f"step {step_id!r}: an analytic step reads a source the tenant declares free of "
            f"personal fields, and the tenant does not declare {source} so "
            "(taktusctl sources declare --free)"
            for step_id, source in frame.sources(version.work).items()
            if not await self._sources.free_of_personal_fields(tenant, source)
        ]

    async def _lowerings(self, tenant: Tenant, version: ProcessVersion) -> dict[str, LoweredLevels]:
        """The lowered levels of every version the new one would replace, read before the
        registration's own transaction: units of work do not nest."""
        if self._lowered is None:
            return {}
        async with self._work.transaction(tenant):
            replaced = await self._replaced(tenant, version)
        return {old.ref: await self._lowered.lowered(tenant, old.ref) for old in replaced}

    @staticmethod
    def _running(version: ProcessVersion, lowerings: Mapping[str, LoweredLevels]) -> Autonomy:
        """The statement of a version as it runs now: lowered where a level fell by rule."""
        lowered = lowerings.get(version.ref)
        if lowered is None:
            return version.autonomy
        return autonomy.lowered_to(version.autonomy, lowered.level, lowered.actions)

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
        quality = (await self._ledger.project(tenant, QUALITY)).history(version.process_id)
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
        version = ProcessVersion(
            process_id=bundle.get("id", ""),
            version=str(bundle.get("version", "")),
            name=bundle.get("name", ""),
            autonomy=_autonomy(bundle.get("autonomy")),
            steps=tuple(steps),
            triggers=tuple(Trigger.model_validate(t) for t in bundle.get("triggers", ())),
            slo=_slo(bundle.get("slo")),
            expect=_expect(bundle.get("expect")),
            work=work,
            limits=bundle.get("limits"),
            inputs=_inputs(bundle.get("inputs")),
            open_work=_open_work(bundle.get("open_work")),
            author=bundle.get("author"),
            reason=bundle.get("reason"),
        )
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("bundle", error))) from error
    refused = exactness.findings(version.steps)
    refused.extend(evaluation.findings(version.steps, version.work))
    refused.extend(frame.findings(version.steps, version.work, version.inputs))
    try:
        exactness.statement(version.ref, version.name, version.steps)
    except InvalidStatement as error:
        refused.append(str(error))
    if refused:
        raise InvalidProcess(tuple(refused))
    return version


def statement_of(bundle: Document) -> ExactnessStatement:
    """The exactness statement of the version a bundle registers as, or InvalidProcess with
    every finding that refuses the bundle (UC-6.9)."""
    version = parse_bundle(bundle)
    return exactness.statement(version.ref, version.name, version.steps)


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


def _open_work(raw: Any) -> dict[str, OpenWorkCap]:
    """`open_work`: per kind of open outcome, its `cap`, how it is counted, and how often a
    waiting run counts again (ADR-0132 §1)."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`open_work` is not a mapping of kind to cap",))
    caps: dict[str, OpenWorkCap] = {}
    for kind, declared in raw.items():
        if not isinstance(declared, Mapping):
            raise InvalidProcess((f"`open_work.{kind}` is not a mapping",))
        fields = dict(declared)
        if "check_every" in fields:
            fields["check_every"] = _duration(fields["check_every"])
        try:
            caps[str(kind)] = OpenWorkCap.model_validate(fields)
        except ValidationError as error:
            raise InvalidProcess(tuple(_describe(f"open_work.{kind}", error))) from error
    return caps


def _slo(raw: Any) -> Slo | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`slo` is not a mapping",))
    return Slo(
        freshness=_duration(raw.get("freshness")),
        latency=_duration(raw.get("latency")),
    )


def _expect(raw: Any) -> Expect | None:
    """`expect`: a `schedule` or a `gap`, and a `bound` (ADR-0107)."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`expect` is not a mapping",))
    unknown = sorted(set(raw) - {"schedule", "gap", "bound"})
    if unknown:
        raise InvalidProcess(
            (f"`expect` names {', '.join(map(str, unknown))}; it takes schedule, gap and bound",)
        )
    try:
        return Expect(
            schedule=None if raw.get("schedule") is None else str(raw["schedule"]),
            gap=_duration(raw.get("gap")),
            bound=_duration(raw.get("bound")),
        )
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("expect", error))) from error


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


def _content(version: ProcessVersion) -> dict[str, Any]:
    """What a version is, without who registered it and why: the same bundle registered again
    by someone else is the same version."""
    return version.model_dump(mode="json", exclude={"author", "reason"})
