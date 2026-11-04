"""A result defect found, assessed, remedied and delivered by itself (#92, ADR-0184, ADR-0179,
UC-4.10, UC-4.11, UC-4.12, UC-6.8).

- **Found.** A correction (`step.corrected`, run component), a sample a person judged wrong
  (`check.sampled` whose request was answered *wrong*, ADR-0152), and a result a check marked
  suspect when it was applied again (`check.suspect`, ADR-0179 §1). `RecheckWatch` applies the
  checks that read a source again, once a day, to the results of the runs that finished in the
  last thirty days.
- **Assessed.** `DefectWatch` raises each through the governance component's `ResultDefects`:
  the window, the impact over the provenance chain, the tenant's rule and the plan, the same as
  by hand. A result without a provenance record is logged and looked at again, never raised
  blind.
- **Remedied.** `Remedies` starts the plan's run on the engine (ADR-0179 §3): the corrected step
  carried with the value a person gave, or run again where a source changed underneath it;
  every step it is not built on carried as the wrong run left it; everything built on it run
  again at the process's level; every step that acts outward waits for the correction anchor's
  person. The ledger records `remediation.started`, naming the incident and the new run.
- **Delivered.** `IncidentDelivery` writes the incident into the organisation's tracking system
  through the connector that serves `repository.issues`, as an issue with its situation
  package and its plan, and every later change — the remediation started, the incident closed
  — as a comment on the same issue (ADR-0179 §4). Each delivery is `egress.delivery`, naming the
  incident.

The incident is the tenant's; nothing here corrects anything outside without a person. This is
wiring, because the correction, the sample and the run are the run component's records, the
verdict the decision component's, and the incident the governance component's.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol

import structlog

from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.governance.application.service import ResultDefects
from taktus.components.governance.application.service.result_defects import ReportDefect
from taktus.components.governance.domain.model.defects import Found
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.governance.domain.service import defects as defect_rule
from taktus.components.governance.domain.service.defects import NotRecorded
from taktus.components.process.domain.service.autonomy import is_result_defect
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Remedy, Run, RunExists, StepRun
from taktus.components.run.domain.service.anchoring import WRONG
from taktus.components.run.ports import ConnectorPool
from taktus.components.run.ports.anchors import Verdict
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.connector import CallContext
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Command, Intent, LedgerEntry, LedgerRefs, ReplyTo

log = structlog.get_logger("taktusd")

CORRECTED = "step.corrected"
SAMPLED = "check.sampled"
SUSPECT = "check.suspect"
RAISED = "incident.raised"
CLOSED = "incident.closed"
REMEDIATION = "remediation.started"
DELIVERY = "egress.delivery"
FINISHED = "run.finished"
TRACKING = "repository.issues"
"""The capability an organisation's tracking system is reached through: its issues."""
CREATE = "repository.issues.create"
COMMENT = "repository.comments.create"
TAKTUS = "taktus"
"""The identity Taktus acts as on its own behalf (ADR-0033)."""
CHANNEL = "channel.schedule"
INTERVAL_SECONDS = 300
"""How often the scheduler looks for defects nobody assessed, and incidents not delivered."""
RECHECK_INTERVAL_SECONDS = 86_400
"""How often the checks that read a source are applied again: once a day."""
RECHECK_HORIZON = timedelta(days=30)
"""How far back a run's results are checked again: the runs that finished in the last thirty
days."""


class Verdicts(Protocol):
    """Where a decision request stands, as the run's port reads it."""

    async def verdict(self, tenant: Tenant, request_id: str) -> Verdict | None: ...


class RemedyRefused(Exception):
    """A remediation run cannot be started: what is missing, in words a person acts on."""


class Remedies:
    """The remediation plan of a result defect executed by the engine (ADR-0179 §3)."""

    def __init__(
        self,
        engine: RunEngine,
        runs: Repository[Run],
        incidents: Repository[Incident],
        commission: CommissionPlanHandler,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._engine = engine
        self._runs = runs
        self._incidents = incidents
        self._commission = commission
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids

    async def start(self, tenant: Tenant, incident_id: str) -> Run:
        """The remediation run of the incident: the one started now, or the one started
        before. `RemedyRefused` where nothing says what the result should have been."""
        async with self._work.transaction(tenant):
            incident = await self._incidents.get(tenant, incident_id)
            wrong = (
                None
                if incident is None or incident.run_id is None
                else await self._runs.get(tenant, incident.run_id)
            )
            corrections = await self._ledger.of_kinds(tenant, (CORRECTED,))
        if incident is None or incident.kind is not IncidentKind.RESULT_DEFECT:
            raise RemedyRefused(f"no result defect {incident_id!r}")
        if wrong is None:
            raise RemedyRefused(f"the run of {incident_id} is not stored")
        step = str(incident.facts.get("step") or "")
        found = str(incident.facts.get("found") or "")
        corrected = [
            e.content_digest
            for e in corrections
            if (e.refs.run_id, e.refs.step_id) == (wrong.id, step)
            and e.content_digest is not None
            and not e.rehearsal
        ]
        if not corrected and found != Found.RECHECKED.value:
            raise RemedyRefused(
                f"nothing says what step {step} of run {wrong.id} should have been: a person "
                "records it first (`taktusctl maturation correct`), and the remediation reads it"
            )
        carried = _carried(wrong, step, corrected[-1] if corrected else None)
        digest = hashlib.sha256(f"{tenant}:{incident_id}".encode()).hexdigest()[:20]
        run_id = f"run_remedy_{digest}"
        goal = f"remedy {incident_id}: step {step} of run {wrong.id} and what is built on it"
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=wrong.identity,
            org_path=(tenant,),
            intent=Intent(raw=goal, recognised="defect.remedy"),
            context={"incident": incident_id, "remedies": wrong.id},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=goal,
                autonomy_level=wrong.autonomy_level,
                steps=wrong.steps,
            )
        )
        try:
            run = await self._engine.submit(
                StartRun(
                    plan=plan,
                    work={k: dict(v) for k, v in wrong.work.items()},
                    budget=wrong.budget,
                    process_version=wrong.process_version,
                    actor=TAKTUS,
                    tenant=tenant,
                    inputs=dict(wrong.inputs),
                    run_id=run_id,
                    actions=dict(wrong.actions),
                    org_unit=wrong.org_unit,
                    remedy=Remedy(incident_id=incident_id, run_id=wrong.id, step_id=step),
                    carried=carried,
                )
            )
        except RunExists:
            async with self._work.transaction(tenant):
                existing = await self._runs.get(tenant, run_id)
            if existing is None:
                raise
            return existing
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=REMEDIATION,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=wrong.process_version,
                        incident_id=incident_id,
                        run_id=run.id,
                    ),
                    outcome="carried" if corrected else "again",
                ),
            )
        return run


def _carried(wrong: Run, step: str, corrected: str | None) -> tuple[StepRun, ...]:
    """The step runs a remediation starts from: the corrected step with the value a person
    gave, and every done step the wrong result is not built on, as the wrong run left it. The
    wrong step without a correction, and everything built on it, run again."""
    built_on = {step}
    for each in wrong.steps:
        if any(d in built_on for d in each.dependencies):
            built_on.add(each.id)
    carried: list[StepRun] = []
    for step_run in wrong.step_runs:
        if step_run.step_id == step:
            checkpoint = step_run.checkpoint
            if corrected is not None and checkpoint is not None:
                again = checkpoint.model_copy(update={"result_digest": corrected})
                carried.append(step_run.model_copy(update={"checkpoint": again, "block": None}))
        elif step_run.step_id not in built_on and step_run.done:
            carried.append(step_run.model_copy(update={"block": None}))
    return tuple(carried)


class DefectWatch:
    def __init__(
        self,
        ledger: Ledger,
        defects: ResultDefects,
        work: UnitOfWork,
        *,
        verdicts: Verdicts | None = None,
        remedies: Remedies | None = None,
    ) -> None:
        self._ledger = ledger
        self._defects = defects
        self._work = work
        self._verdicts = verdicts
        self._remedies = remedies

    async def sweep(self, tenant: Tenant) -> list[str]:
        """Every correction, every sample judged wrong and every result marked suspect that no
        result-defect incident answers yet, assessed and raised: the incidents raised now. A
        rehearsal's is none: a rehearsal's result never counted. Each raised defect's plan is
        started on the engine where a remediation is wired and something says what the result
        should have been."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (CORRECTED, SAMPLED, SUSPECT, RAISED))
        answered = {(e.refs.run_id, e.refs.step_id) for e in entries if is_result_defect(e)}
        pending: dict[tuple[str, str], Found] = {}
        for entry in entries:
            if entry.kind == RAISED or entry.rehearsal:
                continue
            run_id, step_id = entry.refs.run_id, entry.refs.step_id
            if run_id is None or step_id is None or (run_id, step_id) in answered:
                continue
            if (run_id, step_id) in pending:
                continue
            found = await self._found(tenant, entry)
            if found is not None:
                pending[(run_id, step_id)] = found
        raised: list[str] = []
        for (run_id, step_id), found in pending.items():
            command = ReportDefect(tenant=tenant, run_id=run_id, step_id=step_id, found=found)
            try:
                incident, _ = await self._defects.raise_incident(command)
            except NotRecorded as missing:
                log.warning(
                    "a result found wrong has no provenance record; it is not assessed",
                    tenant=tenant,
                    run=run_id,
                    step=step_id,
                    reason=str(missing),
                )
                continue
            raised.append(incident.id)
            if self._remedies is not None:
                try:
                    await self._remedies.start(tenant, incident.id)
                except RemedyRefused as why:
                    log.info(
                        "a result defect waits for its correction",
                        incident=incident.id,
                        reason=str(why),
                    )
        return raised

    async def _found(self, tenant: Tenant, entry: LedgerEntry) -> Found | None:
        if entry.kind == CORRECTED:
            return Found.CORRECTED
        if entry.kind == SUSPECT:
            return Found.RECHECKED
        request = entry.refs.decision_request_id
        if self._verdicts is None or request is None:
            return None
        verdict = await self._verdicts.verdict(tenant, request)
        if verdict is None or not verdict.applied or verdict.option != WRONG:
            return None
        return Found.SAMPLED


class Rechecks(Protocol):
    async def recheck(self, tenant: Tenant, run_id: str) -> Sequence[Any]: ...


class RecheckWatch:
    """The checks that read a source, applied again to the results of the runs that finished
    within the horizon (ADR-0179 §1)."""

    def __init__(
        self,
        engine: Rechecks,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        *,
        horizon: timedelta = RECHECK_HORIZON,
    ) -> None:
        self._engine = engine
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._horizon = horizon

    async def sweep(self, tenant: Tenant) -> int:
        """How many results were marked suspect now."""
        since = self._clock.now() - self._horizon
        async with self._work.transaction(tenant):
            finished = await self._ledger.of_kinds(tenant, (FINISHED,), since=since)
        runs = list(dict.fromkeys(e.refs.run_id for e in finished if e.refs.run_id))
        marked = 0
        for run_id in runs:
            marked += len(await self._engine.recheck(tenant, run_id))
        return marked


class IncidentDelivery:
    """A result defect delivered into the organisation's tracking system, and every later
    change to the same object (ADR-0179 §4, UC-6.8)."""

    def __init__(
        self,
        connectors: ConnectorPool,
        incidents: Repository[Incident],
        defects: ResultDefects,
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
    ) -> None:
        self._connectors = connectors
        self._incidents = incidents
        self._defects = defects
        self._ledger = ledger
        self._objects = objects
        self._work = work

    async def deliver(self, tenant: Tenant) -> list[str]:
        """Every result defect not yet delivered, delivered; every change to a delivered one
        added to it. The incidents delivered to or added to now. Nothing where no connector
        serves the tracking capability: the incident stays in Taktus, where a person reads it."""
        resolved = await self._connectors.resolve(TRACKING)
        if resolved is None:
            return []
        async with self._work.transaction(tenant):
            incidents = [
                i
                for i in await self._incidents.list(tenant)
                if i.kind is IncidentKind.RESULT_DEFECT
            ]
            entries = await self._ledger.of_kinds(tenant, (DELIVERY, REMEDIATION, CLOSED))
        delivered: dict[str, str] = {}
        about: dict[str, set[int]] = {}
        for entry in entries:
            iid = entry.refs.incident_id
            if entry.kind != DELIVERY or iid is None or entry.content_digest is None:
                continue
            content = await self._objects.get(entry.content_digest)
            if content is None:
                continue
            said = json.loads(content)
            delivered.setdefault(iid, str(said["reference"]))
            about.setdefault(iid, set()).update(int(n) for n in said.get("covers", []))
        credentials = tuple(
            CredentialReference(name=need.name, injected_as="env")
            for need in resolved.declaration.credentials
            if need.purpose == "actions"
        )
        touched: list[str] = []
        for incident in sorted(incidents, key=lambda i: i.raised_at):
            changes = [
                e
                for e in entries
                if e.kind in (REMEDIATION, CLOSED) and e.refs.incident_id == incident.id
            ]
            if incident.id not in delivered:
                body = await self._body(tenant, incident, changes)
                if body is None:
                    continue
                created = await resolved.connector.call(
                    CREATE,
                    _context(tenant, incident.id, 0, credentials),
                    {"title": _title(incident), "body": body, "labels": []},
                )
                reference = str(created.output["number"])
                # The first text already says every change so far.
                covers = (0, *(c.seq for c in changes))
                await self._record(tenant, incident, resolved.adapter, reference, covers, body)
                touched.append(incident.id)
                continue
            reference = delivered[incident.id]
            for change in changes:
                if change.seq in about.get(incident.id, set()):
                    continue
                text = _update(change)
                await resolved.connector.call(
                    COMMENT,
                    _context(tenant, incident.id, change.seq, credentials),
                    {"number": int(reference), "body": text},
                )
                await self._record(
                    tenant, incident, resolved.adapter, reference, (change.seq,), text
                )
                if incident.id not in touched:
                    touched.append(incident.id)
        return touched

    async def _body(
        self, tenant: Tenant, incident: Incident, changes: Sequence[LedgerEntry]
    ) -> str | None:
        """The issue's text: the situation package and the plan, assessed again now; None
        where the result can no longer be assessed."""
        step = str(incident.facts.get("step") or "")
        found = Found(str(incident.facts.get("found") or Found.CORRECTED.value))
        if incident.run_id is None or not step:
            return None
        try:
            assessed = await self._defects.assess(
                ReportDefect(tenant=tenant, run_id=incident.run_id, step_id=step, found=found)
            )
        except NotRecorded:
            return None
        started = [c for c in changes if c.kind == REMEDIATION]
        tried = f"A remediation run was started: {started[-1].refs.run_id}." if started else None
        package = defect_rule.package(
            assessed.analysis, assessed.decision, assessed.plan, tried=tried
        )
        return "\n\n".join(
            (
                f"Incident {incident.id} ({incident.kind.value}), raised by rule "
                f"{incident.rule}. Its severity is the verdict {incident.facts.get('verdict')}.",
                defect_rule.render_package(package),
                defect_rule.render(assessed.plan),
                f"<!-- taktus incident {incident.id} -->",
            )
        )

    async def _record(
        self,
        tenant: Tenant,
        incident: Incident,
        adapter: str,
        reference: str,
        covers: Sequence[int],
        text: str,
    ) -> None:
        """The delivery as `egress.delivery`, naming the incident, with the external object's
        reference, what it delivered and the changes it covers by digest: 0 for the raise, the
        sequence number of each later entry about the incident."""
        document = {"reference": reference, "covers": list(covers), "text": text}
        digest = await self._objects.put(_canonical(document))
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=DELIVERY,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=incident.process_version,
                        incident_id=incident.id,
                    ),
                    adapter=adapter,
                    outcome="delivered" if 0 in covers else "updated",
                    content_digest=digest,
                ),
            )


def _context(
    tenant: Tenant, incident_id: str, about: int, credentials: tuple[CredentialReference, ...]
) -> CallContext:
    """A delivery's call: Taktus acting as itself, with a key derived from the incident and the
    change, so that a delivery repeated after a crash makes no second object."""
    mark = hashlib.sha256(f"{tenant}:{incident_id}:{about}".encode()).hexdigest()[:40]
    return CallContext(
        tenant=tenant,
        identity=TAKTUS,
        run_id="incident",
        step_id="deliver",
        attempt=1,
        idempotency_key=f"taktus:incident:{mark}",
        credentials=credentials,
    )


def _title(incident: Incident) -> str:
    return (
        f"Result defect in {incident.process_id}: step {incident.facts.get('step')} of run "
        f"{incident.run_id} ({incident.facts.get('verdict')})"
    )


def _update(change: LedgerEntry) -> str:
    if change.kind == REMEDIATION:
        return (
            f"A remediation run was started: {change.refs.run_id}. Its inside steps run at the "
            "process's level; every outward step waits for the person of the correction anchor."
        )
    return "The incident was closed in Taktus."


def _canonical(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()


def defects_tick(
    watch: DefectWatch,
    tenants: ServedTenants,
    clock: Clock,
    *,
    delivery: IncidentDelivery | None = None,
    rechecks: RecheckWatch | None = None,
    interval_seconds: int = INTERVAL_SECONDS,
    recheck_seconds: int = RECHECK_INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: once the interval has passed, every tenant's
    results found wrong are assessed and its incidents delivered; once a day, its checks that
    read a source are applied again first. A sweep that fails is logged and made again at the
    next interval: it never stops the scheduler."""
    last: list[datetime] = []
    rechecked: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        again = rechecks is not None and (
            not rechecked or now - rechecked[0] >= timedelta(seconds=recheck_seconds)
        )
        if again:
            rechecked[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                if again and rechecks is not None:
                    await rechecks.sweep(tenant)
                raised = await watch.sweep(tenant)
                delivered = [] if delivery is None else await delivery.deliver(tenant)
            except Exception as error:  # a sweep must never take the scheduler down
                log.error(
                    "results found wrong not assessed; the next sweep tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for incident in raised:
                log.info("a result found wrong was raised as a result defect", incident=incident)
            for incident in delivered:
                log.info("a result defect was delivered to the tracking system", incident=incident)

    return tick


__all__ = [
    "DefectWatch",
    "IncidentDelivery",
    "RecheckWatch",
    "Remedies",
    "RemedyRefused",
    "defects_tick",
]
