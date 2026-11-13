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

Registering is where a stage of the tenant's introduction caps a level: a version above the
ceiling of its process — level 2 while no open stage names it, otherwise the level the open
stages grant — is refused with `RaiseRefused`, recorded as `autonomy.refused` with outcome
`stage_not_open`, naming the stage and what it lacks to open (ADR-0137 §2). The ceiling lifts
nothing: a version up to it still needs the approval and the history above.

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

Registering is where a figure a query computed must go where it may: a query a model or a
worker wrote feeds no step of class `exact` or `sourced`, and an exact step is fed only by a
query fixed in the version (UC-5.6, ADR-0262 §4, `domain.service.queries`).

Registering is where a declared evaluation must hold: its scorers score steps that produce a
result, each by a rule or by a judge that says why no rule can and names its fallback, and its
cases give the inputs the version requires (UC-4.18, ADR-0134 §1).

Registering is where a version must carry its takeover instructions: a bundle without
`takeover`, with an entry for a step it does not have or none for one it has, with a credential
a step names and its entry does not, or naming an identifier a person could not look up without
Taktus, is refused (UC-6.3, ADR-0180 §2).

Registering is where the three rights of a process hold, once a role of the tenant holds one of
them: the first version of a process is registered only by an identity holding
`process.create`; every version only by one holding `process.approve`, since registering
approves it for operation; and a first version, or one that raises a level, only with an
identity holding `autonomy.set` — the approving person, or whoever registers where none
approves. A version an identity lacks a right for is refused, and `process.refused` records it
with the right it lacked as its outcome (UC-7.3, ADR-0257).

Registering is where a domain without an owner holds its processes' levels: a version that
raises a level of a process whose domain has no owner now is refused with `RaiseRefused`, and
`autonomy.refused` records it with outcome `no_owner` (UC-15.5, ADR-0259 §2).

Registering is where a person's step must name its role once the tenant has a structure: a
`human` step, or a fallback to a person, without a role, or naming a role no identity of the
tenant holds, is refused (UC-4.20, ADR-0146). While no identity holds a role, nothing is
required.

Registering is where the tenant's residency rule holds a version: one whose step handling data
the rule restricts would be bound to a model, a worker, a connector or a host outside the
permitted location is refused, each finding naming the step, the data class and the adapter
(UC-11.1, ADR-0281 §4).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from taktus.components.process.domain.model import (
    ChangeRecord,
    Control,
    DataContract,
    DeadlineDeclaration,
    Escalation,
    EvaluationSpec,
    Expect,
    Frame,
    InputDeclaration,
    InvalidProcess,
    OpenWorkCap,
    Process,
    ProcessVersion,
    RaiseRefused,
    Slo,
    TakeoverInstructions,
    Trigger,
)
from taktus.components.process.domain.model.exactness import (
    ExactnessStatement,
    InvalidStatement,
)
from taktus.components.process.domain.model.process import FRAME_KINDS
from taktus.components.process.domain.service import (
    autonomy,
    evaluation,
    exactness,
    frame,
    partners,
    queries,
)
from taktus.components.process.domain.service import takeover as instructed
from taktus.components.process.domain.service.quality import QUALITY
from taktus.components.process.ports import (
    DomainOwners,
    FreeSources,
    LoweredLevels,
    LoweredVersions,
    ProcessRights,
    ResidencyBindings,
    RoleStructure,
    StageCeilings,
)
from taktus.components.process.ports.rights import (
    APPROVE,
    CREATE,
    OF_A_PROCESS,
    SET_AUTONOMY,
)
from taktus.ports.administration import Administration
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Autonomy, LedgerRefs, Method, Step

type Document = Mapping[str, Any]

CAP_CHANGED = "open_work.changed"
"""A version changed a cap on open work with a person's approval (ADR-0132 §3)."""
CAP_REFUSED = "open_work.refused"
"""A version that changes a cap on open work was refused for want of a person's approval."""
STAGE_NOT_OPEN = "stage_not_open"
"""The outcome of `autonomy.refused` for a version above what the tenant's stages allow."""

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
    its caps on open work (ADR-0132). A version that does neither needs no approval. Once the
    tenant grants the rights of a process, the person holds `autonomy.set` (ADR-0257)."""


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
        stages: StageCeilings | None = None,
        structure: RoleStructure | None = None,
        rights: ProcessRights | None = None,
        domains: DomainOwners | None = None,
        residency: ResidencyBindings | None = None,
    ) -> None:
        self._residency = residency
        """Which steps would be bound outside the tenant's residency rule (ADR-0281 §4). None:
        the run alone holds a step to the rule."""
        self._domains = domains
        """Which processes belong to a domain without an owner (ADR-0259). None: no domain
        holds a level."""
        self._rights = rights
        """Who holds the rights of a process (ADR-0257). None: no right is asked for."""
        self._structure = structure
        """Which roles the tenant's identities hold (ADR-0146). None: no role is required."""
        self._stages = stages
        """How high a process may run under the tenant's stages (ADR-0137). None: no stage
        caps a level."""
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
        unroled = await self._unroled(tenant, version)
        if unroled:
            raise InvalidProcess(tuple(unroled))
        outside = [] if self._residency is None else await self._residency.outside(tenant, version)
        if outside:
            raise InvalidProcess(tuple(outside))
        above = await self._above_ceiling(tenant, version)
        if above is not None:
            async with self._work.transaction(tenant):
                await self._record(
                    tenant,
                    version,
                    "autonomy.refused",
                    STAGE_NOT_OPEN,
                    command,
                    actor=command.approved_by or command.by,
                )
            raise RaiseRefused(version.ref, (above,))
        refused: autonomy.RaiseVerdict | None = None
        capped: str | None = None
        lowerings = await self._lowerings(tenant, version)
        lacking = await self._lacking(tenant, version, lowerings, command)
        ownerless = (
            None
            if self._domains is None
            else await self._domains.ownerless(tenant, version.process_id)
        )
        if lacking:
            async with self._work.transaction(tenant):
                for right, _, actor in lacking:
                    outcome = "lacks_" + right.replace(".", "_")
                    await self._record(
                        tenant, version, "process.refused", outcome, command, actor=actor
                    )
            raise InvalidProcess(tuple(finding for _, finding, _ in lacking))
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
            if raised and ownerless is not None:
                refused = autonomy.RaiseVerdict(
                    admitted=False,
                    findings=(
                        f"{version.process_id} belongs to the domain {ownerless!r}, which has "
                        "no owner now: nothing in it is raised in autonomy until a person is "
                        "named its owner (UC-15.5, ADR-0259)",
                    ),
                    refusal="no_owner",
                )
                await self._record(tenant, version, "autonomy.refused", "no_owner", command)
            elif raised:
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

    async def _above_ceiling(self, tenant: Tenant, version: ProcessVersion) -> str | None:
        """Why the version runs above what the tenant's stages allow; None where it does not
        (ADR-0137 §2)."""
        if self._stages is None:
            return None
        ceiling = await self._stages.ceiling(tenant, version.process_id)
        if ceiling is None or version.autonomy.level <= ceiling.level:
            return None
        if ceiling.stage is None:
            return (
                f"{version.ref} runs at level {version.autonomy.level}, and the open stages of "
                f"{tenant} allow {version.process_id} at most level {ceiling.level} (ADR-0137)"
            )
        lacks = "; ".join(ceiling.missing) or "nothing but its opening"
        return (
            f"{version.ref} runs at level {version.autonomy.level}, and {version.process_id} "
            f"belongs to the stage {ceiling.stage!r}, which is not open: until it opens the "
            f"process runs at most at level {ceiling.level}. The stage lacks: {lacks} "
            "(ADR-0137)"
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

    async def _unroled(self, tenant: Tenant, version: ProcessVersion) -> list[str]:
        """Every step where a person acts without a role the tenant's structure holds, once
        the tenant has a structure (ADR-0146 §2)."""
        if self._structure is None:
            return []
        held = await self._structure.roles(tenant)
        if not held:
            return []
        return [f for step in version.steps if (f := unroled(step, held)) is not None]

    async def _lacking(
        self,
        tenant: Tenant,
        version: ProcessVersion,
        lowerings: Mapping[str, LoweredLevels],
        command: RegisterProcessVersion,
    ) -> list[tuple[str, str, str | None]]:
        """Every right of a process the act needs and its identity lacks, each with its
        finding and the identity that lacked it (ADR-0257). Nothing while no role of the
        tenant holds one of the rights."""
        if self._rights is None or not await self._rights.granting(tenant, OF_A_PROCESS):
            return []
        async with self._work.transaction(tenant):
            replaced = [r for r in await self._replaced(tenant, version) if r.ref != version.ref]
            first = not replaced and await self._versions.get(tenant, version.ref) is None
        raised = any(
            autonomy.raises(self._running(old, lowerings), version.autonomy) for old in replaced
        )
        needed: list[tuple[str, str | None, str]] = []
        if first:
            needed.append((CREATE, command.by, f"create the process {version.process_id}"))
        needed.append((APPROVE, command.by, f"approve {version.ref} for operation"))
        if first or raised:
            what = "set" if first else "raise"
            needed.append(
                (
                    SET_AUTONOMY,
                    command.approved_by or command.by,
                    f"{what} the autonomy level of {version.process_id} to "
                    f"{version.autonomy.level}",
                )
            )
        lacking: list[tuple[str, str, str | None]] = []
        for right, who, act in needed:
            if who is not None and await self._rights.holds(tenant, who, right):
                continue
            named = "an act naming no identity" if who is None else f"{who!r}"
            lacking.append(
                (
                    right,
                    f"{named} may not {act}: it lacks the right {right}, which a role of the "
                    "tenant holds and grants to those who hold the role (UC-7.3, ADR-0257)",
                    who,
                )
            )
        return lacking

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
        return autonomy.lowered_to(
            version.autonomy, lowered.level, lowered.actions, lowered.classes
        )

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


def unroled(step: Step, held: frozenset[str]) -> str | None:
    """Why the step's person has no role of the structure `held`; None where it has one, or
    where no person acts at it (ADR-0146 §2)."""
    if step.method is Method.HUMAN:
        where, role = "a human step", step.role
    elif step.fallback is not None and step.fallback.to is Method.HUMAN:
        where, role = "its fallback to a person", step.fallback.role
    else:
        return None
    roles = ", ".join(sorted(held))
    if role is None:
        return (
            f"step {step.id!r}: {where} names the role that performs it once the tenant has a "
            f"structure; the tenant's roles are {roles} (ADR-0146)"
        )
    if role not in held:
        return (
            f"step {step.id!r}: {where} names the role {role!r}, which no identity of the tenant "
            f"holds; the tenant's roles are {roles} (ADR-0146)"
        )
    return None


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
    version, refused = read_bundle(bundle)
    if refused:
        raise InvalidProcess(tuple(refused))
    return version


def read_bundle(bundle: Document) -> tuple[ProcessVersion, list[str]]:
    """The bundle as a process version, and every finding of the rules a version is held to
    beyond its shape — exactness, takeover instructions, evaluation, the frame of its steps —
    which `parse_bundle` refuses it for. InvalidProcess where its shape cannot be read at all.
    A change Taktus made keeps the findings on its proposal (ADR-0255 §3)."""
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
            deadlines=_deadlines(bundle.get("deadlines")),
            evaluation=_evaluation(bundle.get("evaluation")),
            tolerances=_tolerances(bundle.get("tolerances")),
            case=bundle.get("case"),
            takeover=_takeover(bundle.get("takeover")),
            escalation=_escalation(bundle.get("escalation")),
            heal_limit=bundle.get("heal_limit", 3),
            frame=_frame(bundle.get("frame")),
            change=_change(bundle.get("change")),
            control=_control(bundle.get("control")),
            contracts=_contracts(bundle.get("contracts")),
            author=bundle.get("author"),
            reason=bundle.get("reason"),
        )
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("bundle", error))) from error
    refused = exactness.findings(version.steps)
    if version.takeover is not None:
        refused.extend(
            instructed.findings(version.takeover, version.steps, credentials_named(version))
        )
    refused.extend(evaluation.findings(version.steps, version.work))
    refused.extend(
        f"the {version.step(step_id).method} step {step_id!r} varies and declares no tolerance: "
        "what counts as an equivalent result, under `tolerances` or `evaluation.tolerances`, "
        "within its class's ceiling (UC-8.4, ADR-0300 §1)"
        for step_id in version.undeclared_tolerances()
    )
    refused.extend(frame.findings(version.steps, version.work, version.inputs))
    refused.extend(partners.findings(version))
    refused.extend(queries.findings(version.steps, version.work))
    try:
        exactness.statement(version.ref, version.name, version.steps)
    except InvalidStatement as error:
        refused.append(str(error))
    return version, refused


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


def _deadlines(raw: Any) -> dict[str, DeadlineDeclaration]:
    """`deadlines`: per name, the moment it starts `from`, its `limit`, an optional `lead`, how
    it `counts`, the step it is met `until`, and the action `at_lead` and `at_limit`
    (ADR-0133 §1). A deadline without an action at its limit does not register."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`deadlines` is not a mapping of name to deadline",))
    declared: dict[str, DeadlineDeclaration] = {}
    findings: list[str] = []
    for name, given in raw.items():
        where = f"deadlines.{name}"
        if not isinstance(given, Mapping):
            findings.append(f"`{where}` is not a mapping")
            continue
        fields = dict(given)
        unknown = sorted(set(fields) - DEADLINE_FIELDS)
        if unknown:
            findings.append(f"`{where}` names {', '.join(unknown)}, which a deadline has not")
            continue
        if fields.get("at_limit") is None:
            findings.append(
                f"`{where}` names no `at_limit`; a deadline without an action does not register"
            )
            continue
        try:
            document: dict[str, Any] = {
                **_starting(fields.get("from"), where),
                "limit": _duration(fields.get("limit")),
                "lead": _duration(fields.get("lead")),
                "working": _counts(fields.get("counts", "calendar"), where),
                "until": _until(fields.get("until"), where),
                "at_lead": _action(fields.get("at_lead"), f"{where}.at_lead"),
                "at_limit": _action(fields.get("at_limit"), f"{where}.at_limit"),
            }
            if document["limit"] is None:
                raise InvalidProcess((f"`{where}` names no `limit`",))
            declared[str(name)] = DeadlineDeclaration.model_validate(document)
        except InvalidProcess as error:
            findings.extend(error.findings)
        except ValidationError as error:
            findings.extend(_describe(where, error))
    if findings:
        raise InvalidProcess(tuple(findings))
    return declared


DEADLINE_FIELDS = frozenset({"from", "limit", "lead", "counts", "until", "at_lead", "at_limit"})
ACTIONS = ("remind", "escalate", "start")


def _starting(raw: Any, where: str) -> dict[str, Any]:
    if raw == "run":
        return {"start": "run"}
    if isinstance(raw, Mapping) and len(raw) == 1:
        ((key, value),) = raw.items()
        if key == "after" and isinstance(value, str):
            return {"start": "after", "after": value}
        if key == "date" and isinstance(value, str):
            return {"start": "date", "date_input": value}
    raise InvalidProcess(
        (f"`{where}.from` is `run`, `{{after: <step>}}` or `{{date: <input>}}`, not {raw!r}",)
    )


def _counts(raw: Any, where: str) -> bool:
    if raw not in ("calendar", "working"):
        raise InvalidProcess((f"`{where}.counts` is `calendar` or `working`, not {raw!r}",))
    return bool(raw == "working")


def _until(raw: Any, where: str) -> str:
    if isinstance(raw, Mapping) and set(raw) == {"step"} and isinstance(raw["step"], str):
        return str(raw["step"])
    raise InvalidProcess((f"`{where}.until` names the step that meets it: `{{step: <step>}}`",))


def _action(raw: Any, where: str) -> dict[str, Any] | None:
    """`{remind: <role>}`, `{escalate: <role>}` or `{start: {process, inputs}}`."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or len(raw) != 1 or next(iter(raw)) not in ACTIONS:
        raise InvalidProcess(
            (
                f"`{where}` is exactly one of `{{remind: <role>}}`, `{{escalate: <role>}}` or "
                "`{start: {process: <process>}}`",
            )
        )
    ((kind, target),) = raw.items()
    if kind == "start":
        if not isinstance(target, Mapping):
            raise InvalidProcess((f"`{where}.start` names `process` and may give `inputs`",))
        return {
            "kind": kind,
            "process": target.get("process"),
            "inputs": target.get("inputs") or {},
        }
    if not isinstance(target, str):
        raise InvalidProcess((f"`{where}.{kind}` names a role, never a person",))
    return {"kind": kind, "role": target}


def _takeover(raw: Any) -> TakeoverInstructions:
    """`takeover`: the sequence, and per step how a person does it by hand (ADR-0180 §1). A
    bundle without it does not register (UC-6.3 §2)."""
    if raw is None:
        raise InvalidProcess((instructed.MISSING,))
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`takeover` is not a mapping of `sequence` and `steps`",))
    try:
        return TakeoverInstructions.model_validate(raw)
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("takeover", error))) from error


def _evaluation(raw: Any) -> EvaluationSpec | None:
    """`evaluation`: the cases, the scorers and the schedule (ADR-0134 §1)."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`evaluation` is not a mapping",))
    try:
        return EvaluationSpec.model_validate(raw)
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("evaluation", error))) from error


def _tolerances(raw: Any) -> dict[str, float]:
    """`tolerances`: per variable step, what counts as an equivalent result, before any case
    exists (ADR-0300 §1)."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or not all(
        isinstance(share, int | float) and not isinstance(share, bool) for share in raw.values()
    ):
        raise InvalidProcess(("`tolerances` maps a step to a share from 0 to 1",))
    return {str(step): float(share) for step, share in raw.items()}


def _slo(raw: Any) -> Slo | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`slo` is not a mapping",))
    try:
        return Slo(
            freshness=_duration(raw.get("freshness")),
            latency=_duration(raw.get("latency")),
            completion=raw.get("completion"),
        )
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("slo", error))) from error


def _escalation(raw: Any) -> Escalation | None:
    """`escalation`: the `role` a failure reaches, the time to react `react_within`, and the
    `path` (ADR-0252 §2)."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`escalation` is not a mapping",))
    unknown = sorted(set(raw) - {"role", "react_within", "path"})
    if unknown:
        raise InvalidProcess(
            (
                f"`escalation` names {', '.join(map(str, unknown))}; it takes role, react_within "
                "and path",
            )
        )
    try:
        return Escalation.model_validate(
            {
                "role": raw.get("role"),
                "react_within": _duration(raw.get("react_within")),
                "path": raw.get("path", "channel"),
            }
        )
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("escalation", error))) from error


def _frame(raw: Any) -> Frame | None:
    """`frame`: the `changes` Taktus may make on its own (ADR-0255 §1)."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or set(raw) - {"changes"}:
        raise InvalidProcess(("`frame` is a mapping that takes `changes` only",))
    try:
        return Frame.model_validate(dict(raw))
    except ValidationError as error:
        raise InvalidProcess(
            (*_describe("frame", error), f"`frame.changes` names any of {', '.join(FRAME_KINDS)}")
        ) from error


def _contracts(raw: Any) -> dict[str, DataContract]:
    """`contracts`: the data contract of every exchange with a partner, by name (ADR-0273)."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise InvalidProcess(("`contracts` maps a name to a data contract",))
    found: dict[str, DataContract] = {}
    for name, given in raw.items():
        if not isinstance(given, Mapping):
            raise InvalidProcess((f"`contracts.{name}` is not a mapping",))
        document = dict(given)
        document["frequency"] = _duration(document.get("frequency"))
        try:
            found[str(name)] = DataContract.model_validate(document)
        except ValidationError as error:
            raise InvalidProcess(tuple(_describe(f"contracts.{name}", error))) from error
    return found


def _control(raw: Any) -> Control:
    """`control`: `coupled`, or `{mode: decoupled, task: {...}}` (ADR-0272)."""
    if raw is None or raw == "coupled":
        return Control()
    try:
        return Control.model_validate(raw)
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("control", error))) from error


def _change(raw: Any) -> ChangeRecord | None:
    """`change`: what led Taktus to the version (ADR-0255 §3)."""
    if raw is None:
        return None
    try:
        return ChangeRecord.model_validate(raw)
    except ValidationError as error:
        raise InvalidProcess(tuple(_describe("change", error))) from error


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
    return version.model_dump(mode="json", exclude={"author", "reason", "change"})
