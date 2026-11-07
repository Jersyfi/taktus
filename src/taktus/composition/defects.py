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
  package and its plan — or, where none does, through one that serves `tasks.items` and
  declares `tasks.items.create`, as a work item (ADR-0227 §4) — and every later change — the
  remediation started, the incident closed — as a comment on the same object (ADR-0179 §4).
  Each delivery is `egress.delivery`, naming the incident.

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
from taktus.components.decision.domain.model import Request
from taktus.components.governance.application.service import ResultDefects
from taktus.components.governance.application.service.result_defects import ReportDefect
from taktus.components.governance.domain.model.defects import Found
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    IncidentState,
)
from taktus.components.governance.domain.service import defects as defect_rule
from taktus.components.governance.domain.service.defects import NotRecorded
from taktus.components.process.domain.service.autonomy import is_result_defect
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Remedy, Run, RunExists, RunState, StepRun
from taktus.components.run.domain.service.anchoring import WRONG
from taktus.components.run.ports import ConnectorPool, ModelPool
from taktus.components.run.ports.anchors import Verdict
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.connector import CallContext, ResolvedConnector
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.model import ModelError, Prompt
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Command, DecisionClass, Intent, LedgerEntry, LedgerRefs, ReplyTo

log = structlog.get_logger("taktusd")

CORRECTED = "step.corrected"
SAMPLED = "check.sampled"
SUSPECT = "check.suspect"
RAISED = "incident.raised"
CLOSED = "incident.closed"
REMEDIATION = "remediation.started"
DELIVERY = "egress.delivery"
RESIDENCY_EGRESS = "residency.egress"
"""Beside every delivery: where the connector it went through is (ADR-0281 §5)."""
FINISHED = "run.finished"
BY_HAND = "incident.by_hand"
REPORTED = "incident.reported"
REMEDY_PREFIX = "run_remedy_"
TRACKING = "repository.issues"
"""The capability an organisation's tracking system is reached through: its issues."""
CREATE = "repository.issues.create"
COMMENT = "repository.comments.create"
TASKS = "tasks.items"
"""The second capability a tracking system is reached through: its work items, where no
repository's issues serve (ADR-0227 §4)."""
TASK_CREATE = "tasks.items.create"
TASK_COMMENT = "tasks.items.remind"
"""A comment on a work item: the operation the task trackers' connectors declare, `marked` by
the key on its last line (ADR-0209)."""
REPORT_PURPOSE = "incident.report"
"""The model purpose the narrative of an incident is written for (UC-6.8, ADR-0227 §5)."""
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
        *,
        defects: ResultDefects | None = None,
    ) -> None:
        self._defects = defects
        """The analysis that names the runs built on a wrong result (ADR-0227 §1). None: only
        the wrong run itself is remedied."""
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
        carried = _carried(wrong, {step}, corrected[-1] if corrected else None)
        return await self._submit(
            tenant,
            incident_id,
            wrong,
            step,
            carried,
            remedy_id(tenant, incident_id),
            "carried" if corrected else "again",
        )

    async def follow(self, tenant: Tenant) -> list[Run]:
        """The runs built on a wrong result in another run or process, produced again once the
        wrong run's own remediation finished (ADR-0227 §1): in each, the steps that read the
        wrong result's closure run again with everything built on them, every other done step
        is carried, and every outward step waits for the correction anchor's person. Each is
        started once; the remediation runs started now."""
        if self._defects is None:
            return []
        async with self._work.transaction(tenant):
            incidents = [
                i
                for i in await self._incidents.list(tenant)
                if i.kind is IncidentKind.RESULT_DEFECT and i.state is IncidentState.OPEN
            ]
            started = {
                e.refs.run_id
                for e in await self._ledger.of_kinds(tenant, (REMEDIATION,))
                if e.refs.run_id
            }
        begun: list[Run] = []
        for incident in incidents:
            first = remedy_id(tenant, incident.id)
            step = str(incident.facts.get("step") or "")
            if first not in started or incident.run_id is None or not step:
                continue
            async with self._work.transaction(tenant):
                primary = await self._runs.get(tenant, first)
            if primary is None or primary.state is not RunState.FINISHED:
                continue  # the derived runs read what the wrong run's remediation corrects
            found = Found(str(incident.facts.get("found") or Found.CORRECTED.value))
            try:
                assessed = await self._defects.assess(
                    ReportDefect(tenant=tenant, run_id=incident.run_id, step_id=step, found=found)
                )
            except NotRecorded:
                continue
            steps: dict[str, set[str]] = {}
            for affected in assessed.analysis.affected:
                ref = affected.result
                if ref.run_id != incident.run_id and not ref.run_id.startswith(REMEDY_PREFIX):
                    steps.setdefault(ref.run_id, set()).add(ref.step_id)
            for run_id, again in steps.items():
                derived_id = remedy_id(tenant, incident.id, run_id)
                if derived_id in started:
                    continue
                async with self._work.transaction(tenant):
                    derived = await self._runs.get(tenant, run_id)
                if derived is None or derived.remedy is not None:
                    continue
                ordered = [s.id for s in derived.steps if s.id in again]
                if not ordered:
                    continue
                begun.append(
                    await self._submit(
                        tenant,
                        incident.id,
                        derived,
                        ordered[0],
                        _carried(derived, set(ordered), None),
                        derived_id,
                        "derived",
                    )
                )
        return begun

    async def _submit(
        self,
        tenant: Tenant,
        incident_id: str,
        wrong: Run,
        step: str,
        carried: tuple[StepRun, ...],
        run_id: str,
        outcome: str,
    ) -> Run:
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
                    outcome=outcome,
                ),
            )
        return run


def remedy_id(tenant: Tenant, incident_id: str, run_id: str | None = None) -> str:
    """The remediation run of an incident, derived from it so that it starts once: of the
    wrong run itself, or of a run built on its result (`run_id`)."""
    key = f"{tenant}:{incident_id}" if run_id is None else f"{tenant}:{incident_id}:{run_id}"
    return f"{REMEDY_PREFIX}{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def _carried(wrong: Run, steps: set[str], corrected: str | None) -> tuple[StepRun, ...]:
    """The step runs a remediation starts from: the corrected step with the value a person
    gave, and every done step the wrong result is not built on, as the wrong run left it. The
    wrong steps without a correction, and everything built on them, run again."""
    built_on = set(steps)
    for each in wrong.steps:
        if any(d in built_on for d in each.dependencies):
            built_on.add(each.id)
    carried: list[StepRun] = []
    for step_run in wrong.step_runs:
        if step_run.step_id in steps:
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
        if self._remedies is not None:
            for run in await self._remedies.follow(tenant):
                log.info(
                    "a run built on a wrong result is produced again",
                    run=run.id,
                    remedies=None if run.remedy is None else run.remedy.run_id,
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
        *,
        reports: IncidentReports | None = None,
    ) -> None:
        self._reports = reports
        """The report a model writes of each incident, delivered as a change (ADR-0227 §5)."""
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
        if self._reports is not None:
            await self._reports.write(tenant)
        resolved = await self._connectors.resolve(TRACKING)
        create, comment = CREATE, COMMENT
        if resolved is None:
            resolved = await self._connectors.resolve(TASKS)
            create, comment = TASK_CREATE, TASK_COMMENT
            if resolved is not None and not any(
                op.name == TASK_CREATE for op in resolved.declaration.operations
            ):
                resolved = None  # a tracker that creates no item cannot take an incident
        if resolved is None:
            return []
        async with self._work.transaction(tenant):
            incidents = [
                i
                for i in await self._incidents.list(tenant)
                if i.kind is IncidentKind.RESULT_DEFECT
            ]
            entries = await self._ledger.of_kinds(
                tenant, (DELIVERY, REMEDIATION, CLOSED, BY_HAND, REPORTED)
            )
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
                if e.kind in (REMEDIATION, CLOSED, BY_HAND, REPORTED)
                and e.refs.incident_id == incident.id
            ]
            if incident.id not in delivered:
                body = await self._body(tenant, incident, changes)
                if body is None:
                    continue
                created = await resolved.connector.call(
                    create,
                    _context(tenant, incident.id, 0, credentials),
                    {"title": _title(incident), "body": body, "labels": []}
                    if create == CREATE
                    else {"title": _title(incident), "description": body},
                )
                reference = str(created.output.get("number") or created.output["id"])
                # The first text already says every change so far; a report follows it.
                covers = (0, *(c.seq for c in changes if c.kind != REPORTED))
                await self._record(tenant, incident, resolved, reference, covers, body)
                touched.append(incident.id)
                continue
            reference = delivered[incident.id]
            for change in changes:
                if change.seq in about.get(incident.id, set()):
                    continue
                text = await self._update(change, incident)
                await resolved.connector.call(
                    comment,
                    _context(tenant, incident.id, change.seq, credentials),
                    {"number": int(reference), "body": text}
                    if comment == COMMENT
                    else {"id": reference, "text": text},
                )
                await self._record(tenant, incident, resolved, reference, (change.seq,), text)
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
        said = [f"A remediation run was started: {c.refs.run_id}." for c in started]
        said += [_by_hand(h) for h in incident.done_by_hand]
        tried = " ".join(said) or None
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

    async def _update(self, change: LedgerEntry, incident: Incident) -> str:
        """The comment a later change is delivered as."""
        if change.kind == BY_HAND:
            done = [h for h in incident.done_by_hand if h.at <= change.ts]
            return _by_hand(done[-1]) if done else "A step was carried out by hand."
        if change.kind == REPORTED and change.content_digest is not None:
            content = await self._objects.get(change.content_digest)
            if content is not None:
                return content.decode("utf-8")
        return _canonical_update(change)

    async def _record(
        self,
        tenant: Tenant,
        incident: Incident,
        resolved: ResolvedConnector,
        reference: str,
        covers: Sequence[int],
        text: str,
    ) -> None:
        """The delivery as `egress.delivery`, naming the incident, with the external object's
        reference, what it delivered and the changes it covers by digest: 0 for the raise, the
        sequence number of each later entry about the incident. Beside it, `residency.egress`
        names where the connector it went through is (ADR-0281 §5)."""
        document = {"reference": reference, "covers": list(covers), "text": text}
        digest = await self._objects.put(_canonical(document))
        refs = LedgerRefs(
            tenant=tenant,
            process_version=incident.process_version,
            incident_id=incident.id,
        )
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=DELIVERY,
                    refs=refs,
                    adapter=resolved.adapter,
                    outcome="delivered" if 0 in covers else "updated",
                    content_digest=digest,
                ),
            )
            await self._ledger.record(
                tenant,
                Fact(
                    kind=RESIDENCY_EGRESS,
                    refs=refs,
                    adapter=resolved.adapter,
                    outcome=resolved.location,
                    content_digest=digest,
                ),
            )


class CorrectionRequests:
    """Governance's port `OpenCorrections` (ADR-0227 §3): the open decision requests of class
    `correction` that the incident's remediation runs raised, read from the ledger's
    `remediation.started` and the decision component's requests."""

    def __init__(self, ledger: Ledger, requests: Repository[Request], work: UnitOfWork) -> None:
        self._ledger = ledger
        self._requests = requests
        self._work = work

    async def waiting(self, tenant: Tenant, incident_id: str) -> Sequence[str]:
        async with self._work.transaction(tenant):
            runs = {
                e.refs.run_id
                for e in await self._ledger.of_kinds(tenant, (REMEDIATION,))
                if e.refs.incident_id == incident_id and e.refs.run_id
            }
            requests = list(await self._requests.list(tenant)) if runs else []
        return sorted(
            r.id
            for r in requests
            if r.open
            and r.request.class_ is DecisionClass.CORRECTION
            and r.request.raised_by.run in runs
        )


class IncidentReports:
    """The incident report a language model may write (UC-6.8, ADR-0023 §4, ADR-0227 §5): the
    narrative a person reads, from the situation package and the plan, an artifact of class
    `free`. It never replaces the structured incident, and it names the package it narrates by
    digest in a line Taktus writes after the model's text."""

    def __init__(
        self,
        models: ModelPool,
        incidents: Repository[Incident],
        defects: ResultDefects,
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
    ) -> None:
        self._models = models
        self._incidents = incidents
        self._defects = defects
        self._ledger = ledger
        self._objects = objects
        self._work = work

    async def write(self, tenant: Tenant) -> list[str]:
        """A report for every open result defect that has none yet; the incidents written for.
        Nothing where no model serves the purpose `incident.report`: the structured incident
        and its package are the record, and a person reads them."""
        resolved = await self._models.resolve(REPORT_PURPOSE)
        if resolved is None:
            return []
        async with self._work.transaction(tenant):
            incidents = [
                i
                for i in await self._incidents.list(tenant)
                if i.kind is IncidentKind.RESULT_DEFECT and i.state is IncidentState.OPEN
            ]
            reported = {
                e.refs.incident_id for e in await self._ledger.of_kinds(tenant, (REPORTED,))
            }
        written: list[str] = []
        for incident in incidents:
            step = str(incident.facts.get("step") or "")
            if incident.id in reported or incident.run_id is None or not step:
                continue
            found = Found(str(incident.facts.get("found") or Found.CORRECTED.value))
            try:
                assessed = await self._defects.assess(
                    ReportDefect(tenant=tenant, run_id=incident.run_id, step_id=step, found=found)
                )
            except NotRecorded:
                continue
            package = defect_rule.render_package(
                defect_rule.package(assessed.analysis, assessed.decision, assessed.plan)
            )
            source = f"{package}\n\n{defect_rule.render(assessed.plan)}"
            try:
                completion = await resolved.model.complete(
                    Prompt(
                        system=REPORT_SYSTEM,
                        user=f"Incident {incident.id}, rule {incident.rule}.\n\n{source}",
                    )
                )
            except ModelError as error:
                log.info("no incident report was written", incident=incident.id, reason=str(error))
                continue
            text = narrated(completion.text, incident.id, source)
            digest = await self._objects.put(text.encode("utf-8"))
            async with self._work.transaction(tenant):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=REPORTED,
                        refs=LedgerRefs(
                            tenant=tenant,
                            process_version=incident.process_version,
                            incident_id=incident.id,
                        ),
                        adapter=resolved.adapter,
                        outcome="free",
                        content_digest=digest,
                    ),
                )
            written.append(incident.id)
        return written


REPORT_SYSTEM = (
    "You write the incident report a person reads. State which check fired, on which facts, "
    "with which thresholds; the window; what is affected and what has left the system; the plan "
    "and where it waits for a person. Use only the facts given. Name no person."
)


def narrated(text: str, incident_id: str, source: str) -> str:
    """The model's report with the line that names what it narrates (ADR-0227 §5)."""
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return (
        f"{text.rstrip()}\n\nThis report of {incident_id} was written by a model (class free) "
        f"from its situation package and plan, sha256:{digest[:16]}; the incident in Taktus is "
        "the record."
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


def _by_hand(done: Any) -> str:
    return (
        f"Step {done.step} was carried out by hand in the role {done.role} at {done.at}: "
        f"{done.done}"
    )


def _canonical_update(change: LedgerEntry) -> str:
    if change.kind == REMEDIATION:
        derived = (
            " It produces again a result built on the wrong one."
            if (change.outcome == "derived")
            else ""
        )
        return (
            f"A remediation run was started: {change.refs.run_id}.{derived} Its inside steps run "
            "at the process's level; every outward step waits for the person of the correction "
            "anchor."
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
    "CorrectionRequests",
    "DefectWatch",
    "IncidentDelivery",
    "IncidentReports",
    "RecheckWatch",
    "Remedies",
    "RemedyRefused",
    "defects_tick",
]
