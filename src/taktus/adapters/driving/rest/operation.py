"""What keeps the operation running, on the HTTP surface (ADR-0121, DEC-0218).

- `GET /operation` — one line per kind for the start page: how many incidents are open, how
  many alerts are in effect, how the backup stands, how many signals are red, yellow or not
  measured, and the newest daily report.
- `GET /incidents` — every incident, open and closed, newest first (ADR-0107).
- `GET /alerts` — every alert with what became of its report (ADR-0106).
- `GET /backup` — the backup's last outcome and by when the next is due (ADR-0106).
- `GET /signals` — every signal in force, judged against its corridor (ADR-0109).
- `GET /signals/daily-report` — the newest daily report of what deviates (ADR-0109 §5).

Every route reads the account key from `Authorization: Bearer` and nowhere else. An incident
and a signal are about a process, and a reader sees them where the one predicate lets them see
the process. An alert, the backup and the daily report are reports to the owner: the owner and
the people the owner named read them, as they read every report (ADR-0045). Nothing here names
a person (principle 14): every record names a run, a step, a process, a role or a department.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.governance.domain.model import Incident, IncidentState
from taktus.components.reporting.application.query import view as report_view
from taktus.components.reporting.application.service import Alerted, BackupWatched
from taktus.components.reporting.domain.model import (
    Corridor,
    Judged,
    Level,
    ProcessRef,
    Reader,
    Report,
    ReportKind,
)
from taktus.components.reporting.domain.service import visibility
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
NOT_A_READER = "only the owner, and the people the owner named, read the reports"
UNAUTHENTICATED: dict[int | str, dict[str, Any]] = {
    401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
    422: {"description": "A parameter does not validate.", **PROBLEM},
}
OWNERS: dict[int | str, dict[str, Any]] = {
    **UNAUTHENTICATED,
    403: {"description": "You are not the owner, nor someone the owner named.", **PROBLEM},
}


def _at(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def _sees(reader: Reader, tenant: str, process_id: str) -> bool:
    """Whether the reader may see a record about this process: the one predicate, through its
    module (ADR-0055 §5)."""
    return visibility.may_see_process(reader, ProcessRef(id=process_id, tenant=tenant))


def incident_view(incident: Incident) -> dict[str, Any]:
    """An incident as a reader sees it: what was expected, what happened, and the run, the
    process and the version it is about. It names no person: who closed it is the actor of
    its ledger entry, and not shown here."""
    document: dict[str, Any] = {
        "id": incident.id,
        "kind": incident.kind.value,
        "state": incident.state.value,
        "process_id": incident.process_id,
        "process_version": incident.process_version,
        "rule": incident.rule,
        "raised_at": incident.raised_at.isoformat(),
        "expected_at": _at(incident.expected_at),
        "closed_at": _at(incident.closed_at),
        "run_id": incident.run_id,
        "last_run": None
        if incident.last_run is None
        else {
            "at": incident.last_run.at.isoformat(),
            "run_id": incident.last_run.run_id,
            "kind": incident.last_run.kind,
        },
        "facts": dict(incident.facts),
        "timeline": [
            {
                "at": h.at.isoformat(),
                "what": h.what,
                "expected_at": _at(h.expected_at),
                "deadline": _at(h.deadline),
                "run_id": None if h.run is None else h.run.run_id,
            }
            for h in incident.timeline
        ],
    }
    step = incident.facts.get("step")
    document["step_id"] = step if isinstance(step, str) else None
    return document


def alert_view(alerted: Alerted) -> dict[str, Any]:
    """An alert with what became of its report. Its identifier is its report's."""
    alert = alerted.alert
    return {
        "id": alert.id,
        "kind": alert.kind,
        "since": alert.since.isoformat(),
        "in_effect": alert.in_effect,
        "closed": alerted.closed,
        "delivered": alerted.delivered,
        "reason": alerted.reason,
        "state": alerted.state,
        "title": alert.title,
        "summary": alert.summary,
        "needed": list(alert.needed),
        "steps": list(alert.steps),
        "standing_still": list(alert.standing_still),
        "about": [r.model_dump(mode="json", exclude_none=True) for r in alert.about],
        "report": alerted.report is not None,
    }


def backup_standing(watched: BackupWatched) -> str:
    """`failing` where the newest runs failed, `missing` where none succeeded within the
    expected interval, `ok` where the last success is recent enough, `not_recorded` where no
    backup was recorded and none is watched."""
    if watched.state.failed_count > 0:
        return "failing"
    if watched.alert is not None:
        return "missing"
    return "ok" if watched.state.last_ok is not None else "not_recorded"


def backup_view(watched: BackupWatched) -> dict[str, Any]:
    state = watched.state
    newest = state.failed[0] if state.failed else None
    return {
        "standing": backup_standing(watched),
        "watched": state.expected_hours is not None,
        "expected_hours": state.expected_hours,
        "next_due": _at(watched.next_due),
        "last_ok": None
        if state.last_ok is None
        else {"name": state.last_ok.name, "at": state.last_ok.at.isoformat()},
        "failed_count": state.failed_count,
        "newest_failed": None
        if newest is None
        else {"name": newest.name, "at": newest.at.isoformat(), "reason": newest.reason},
        "alert": None
        if watched.alert is None
        else {
            "id": watched.alert.id,
            "title": watched.alert.title,
            "summary": watched.alert.summary,
            "needed": list(watched.alert.needed),
            "steps": list(watched.alert.steps),
        },
    }


def signal_view(corridor: Corridor, judged: Judged) -> dict[str, Any]:
    """A signal judged now, beside the corridor in force. The corridor names what it is about —
    the operation, a role or a department — and never a person."""
    return {
        "signal": corridor.signal,
        "corridor": corridor.id,
        "version": corridor.version,
        "process": corridor.process,
        "step": corridor.step,
        "select": corridor.select,
        "about": corridor.about.model_dump(mode="json"),
        "bounds": corridor.bounds,
        "direction": corridor.direction,
        "yellow": corridor.yellow,
        "red": corridor.red,
        "window_seconds": corridor.window.total_seconds(),
        "minimum": corridor.minimum,
        "fresh_seconds": corridor.fresh.total_seconds(),
        "role": corridor.role,
        "case": corridor.case,
        "interventions": list(corridor.interventions),
        "changed_at": corridor.changed_at.isoformat(),
        "level": judged.level.value,
        "reason": judged.reason,
        "value": judged.value,
        "median": judged.median,
        "yellow_at": judged.yellow_at,
        "red_at": judged.red_at,
        "run_id": judged.run_id,
        "step_id": judged.step_id,
        "process_version": judged.process_version,
        "at": _at(judged.at),
    }


def newest_daily(reports: Sequence[Report]) -> Report | None:
    """The newest daily report: its identifier carries its date (ADR-0109 §5)."""
    daily = [r for r in reports if r.kind is ReportKind.SIGNALS]
    return max(daily, key=lambda r: (r.raised_at, r.id), default=None)


type Owned = tuple[Sequence[Alerted], BackupWatched, Report | None]
"""What only the owner and the people the owner named read: the alerts, the backup, the newest
daily report."""


def summary(
    tenant: str, incidents: Sequence[Incident], judged: Sequence[Judged], owned: Owned | None
) -> dict[str, Any]:
    """One entry per kind, as the start page shows it. `owned` is None for a reader who may not
    read the reports: those kinds say so, and carry no figure."""
    document: dict[str, Any] = {
        "tenant": tenant,
        "incidents": {
            "readable": True,
            "open": sum(1 for i in incidents if i.state is IncidentState.OPEN),
            "total": len(incidents),
        },
        "signals": {
            "readable": True,
            "red": sum(1 for j in judged if j.level is Level.RED),
            "yellow": sum(1 for j in judged if j.level is Level.YELLOW),
            "unmeasured": sum(1 for j in judged if j.level is Level.UNMEASURED),
            "total": len(judged),
        },
    }
    if owned is None:
        for kind in ("alerts", "backup", "daily_report"):
            document[kind] = {"readable": False}
        return document
    alerted, watched, daily = owned
    document["alerts"] = {
        "readable": True,
        "in_effect": sum(1 for a in alerted if a.alert.in_effect and not a.closed),
        "total": len(alerted),
    }
    document["backup"] = {
        "readable": True,
        "standing": backup_standing(watched),
        "next_due": _at(watched.next_due),
    }
    document["daily_report"] = {
        "readable": True,
        "id": None if daily is None else daily.id,
        "title": None if daily is None else daily.title,
    }
    return document


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["operation"])

    async def reader_of(authorization: str | None) -> Reader | None:
        who = await authenticated(services, authorization)
        if who is None:
            return None
        return Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)

    async def owners(reader: Reader) -> bool:
        return await services.owner_reports.may_read(reader.tenant, reader.identity)

    async def incidents(reader: Reader) -> list[Incident]:
        found = await services.operation.incidents(reader.tenant)
        return [i for i in found if _sees(reader, i.tenant, i.process_id)]

    async def signals(reader: Reader) -> list[tuple[Corridor, Judged]]:
        found = await services.operation.signals(reader.tenant)
        return [(c, j) for c, j in found if _sees(reader, c.tenant, c.process)]

    @routes.get(
        "/operation",
        summary="What keeps the operation running, one line per kind",
        description="For the start page: how many incidents are open, how many signals are "
        "red, yellow or not measured, and — for the owner and the people the owner named — "
        "how many alerts are in effect, how the backup stands and the newest daily report. "
        "A kind the reader may not read says so, with `readable: false` and no figure "
        "(ADR-0121).",
        responses={200: {"description": "One entry per kind."}, **UNAUTHENTICATED},
    )
    async def operation(authorization: str | None = Header(default=None)) -> JSONResponse:
        reader = await reader_of(authorization)
        if reader is None:
            return problem(401, NEEDS_KEY)
        found = await incidents(reader)
        judged = [j for _, j in await signals(reader)]
        if not await owners(reader):
            return JSONResponse(summary(reader.tenant, found, judged, None))
        owned = (
            await services.operation.alerts(reader.tenant),
            await services.operation.backup(reader.tenant),
            newest_daily(await services.owner_reports.reports(reader.tenant)),
        )
        return JSONResponse(summary(reader.tenant, found, judged, owned))

    @routes.get(
        "/incidents",
        summary="The incidents, newest first",
        description="Every incident of your tenant whose process you may see, open and "
        "closed, newest first: what was expected, what happened since, the rule that fired "
        "and the facts it read, and the run, the process version and the step it is about "
        "(ADR-0107, ADR-0109 §4, ADR-0110). An incident names no person.",
        responses={200: {"description": "The incidents."}, **UNAUTHENTICATED},
    )
    async def list_incidents(authorization: str | None = Header(default=None)) -> JSONResponse:
        reader = await reader_of(authorization)
        if reader is None:
            return problem(401, NEEDS_KEY)
        found = await incidents(reader)
        return JSONResponse({"incidents": [incident_view(i) for i in found]})

    @routes.get(
        "/alerts",
        summary="What needs a person's action, with what became of each report",
        description="Every alert of your tenant — a capacity crossing, a lost claim, a failed "
        "or missing backup, a level lowered or a raise proposed by rule, a local lack — in "
        "effect, cleared or closed, each with whether its report reached the owner's channel "
        "and the runs, steps and process versions it is about (ADR-0106). Read by the owner "
        "and the people the owner named.",
        responses={200: {"description": "The alerts."}, **OWNERS},
    )
    async def list_alerts(authorization: str | None = Header(default=None)) -> JSONResponse:
        reader = await reader_of(authorization)
        if reader is None:
            return problem(401, NEEDS_KEY)
        if not await owners(reader):
            return problem(403, NOT_A_READER)
        found = await services.operation.alerts(reader.tenant)
        return JSONResponse({"alerts": [alert_view(a) for a in found]})

    @routes.get(
        "/backup",
        summary="The backup's last outcome and by when the next is due",
        description="The last successful backup the backup program recorded, the failed runs "
        "since, by when the next success is due under `TAKTUS_BACKUP_EXPECTED_HOURS`, and the "
        "alert in effect if there is one (ADR-0106 §3, §5). Read by the owner and the people "
        "the owner named.",
        responses={200: {"description": "The backup's standing."}, **OWNERS},
    )
    async def backup(authorization: str | None = Header(default=None)) -> JSONResponse:
        reader = await reader_of(authorization)
        if reader is None:
            return problem(401, NEEDS_KEY)
        if not await owners(reader):
            return problem(403, NOT_A_READER)
        return JSONResponse(backup_view(await services.operation.backup(reader.tenant)))

    @routes.get(
        "/signals",
        summary="The signals, judged against their corridors",
        description="Every signal in force whose process you may see, judged now: normal, "
        "yellow, red, or not measured with the reason, beside its corridor — the thresholds, "
        "the role a red value reaches, where a deviation is worked — and the run and the step "
        "that measured the newest value (ADR-0109). A corridor names the operation, a role or "
        "a department, never a person.",
        responses={200: {"description": "The signals."}, **UNAUTHENTICATED},
    )
    async def list_signals(authorization: str | None = Header(default=None)) -> JSONResponse:
        reader = await reader_of(authorization)
        if reader is None:
            return problem(401, NEEDS_KEY)
        found = await signals(reader)
        return JSONResponse({"signals": [signal_view(c, j) for c, j in found]})

    @routes.get(
        "/signals/daily-report",
        summary="The newest daily report of what deviates",
        description="The newest report of kind `signals` as its view: every signal that is "
        "red or yellow or not measured, each line with its run and its case (ADR-0109 §5). "
        "Read by the owner and the people the owner named.",
        responses={
            200: {"description": "The report's view."},
            404: {"description": "No daily report was raised yet.", **PROBLEM},
            **OWNERS,
        },
    )
    async def daily_report(authorization: str | None = Header(default=None)) -> JSONResponse:
        reader = await reader_of(authorization)
        if reader is None:
            return problem(401, NEEDS_KEY)
        if not await owners(reader):
            return problem(403, NOT_A_READER)
        found = newest_daily(await services.owner_reports.reports(reader.tenant))
        if found is None:
            return problem(404, "no daily report was raised yet")
        return JSONResponse(report_view(found, reader.identity))

    return routes
