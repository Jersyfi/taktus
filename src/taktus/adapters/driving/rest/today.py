"""`GET /levels/today`: the start page and the frame in one request (ADR-0318).

The overview, how many things stand where, what waits for the reader as one short list, and the
marks the navigation shows — read from counts, from the open records and from the last day of
the ledger, never from a tenant's whole history of runs. Every part is asked through the same
predicate as the request that reads it on its own: what the reader may not see is absent, not
counted. The answer carries an `ETag`; a reader that names it in `If-None-Match` receives `304`
and no body where nothing changed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import Response

from taktus.adapters.driving.rest.autonomy import autonomy_processes
from taktus.adapters.driving.rest.operation import newest_daily, summary
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.governance.domain.model import IncidentState
from taktus.components.reporting.domain.model import (
    CountedRuns,
    ProcessRef,
    Reader,
    Report,
    ReportKind,
    ReportState,
    RunRef,
)
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.domain.service.today import Waiting, WaitKind, one_line, waits
from taktus.components.run.domain.model import RunState
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
FAILED = "run.escalated"
"""The ledger kind a run's failure is recorded under: it escalated."""
FAILED_WITHIN = timedelta(hours=24)
"""How far back a failure counts on the start page."""


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["levels"])

    @routes.get(
        "/levels/today",
        summary="The start page in one request: the overview, the counts, what waits for you",
        description="One answer for the start page and the frame. `overview` is "
        "`GET /levels/overview`. `counts`: what waits for you, how many runs work now, how "
        "many wait on a person, how many failed in the last 24 hours, the open incidents and "
        "the alerts in effect (null where you do not read alerts). `waits`: at most five "
        "things that wait for you — decision requests, needs, reports, failures, alerts — the "
        "most urgent first, then the newest, each with its kind, a one-line title, the route "
        "in the web app and since when. `marks`: what the navigation marks — the decision "
        "requests, the needs, the levels and corrections, the findings in review, and "
        "`GET /operation`'s summary. Read from counts, the open records and the last day of "
        "the ledger, never from every run. `ETag` with `If-None-Match` answers `304` when "
        "nothing changed (ADR-0318).",
        responses={
            200: {"description": "The start page."},
            304: {"description": "Nothing changed since the `ETag` named."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def today(
        authorization: str | None = Header(default=None),
        if_none_match: str | None = Header(default=None),
    ) -> Response:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(
            tenant=who.tenant, identity=who.identity, roles=who.roles, unseen=who.unseen
        )
        document = await _today(services, reader)
        body = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        tag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'
        headers = {"ETag": tag, "Cache-Control": "private, no-cache"}
        if if_none_match is not None and tag in {t.strip() for t in if_none_match.split(",")}:
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)

    return routes


async def _today(services: RestServices, reader: Reader) -> dict[str, Any]:
    tenant = reader.tenant
    overview = await services.levels.overview(reader)
    addressed = await services.decision_queries.addressed_to(tenant, reader.identity)
    owner = await services.owner_reports.may_read(tenant, reader.identity)
    reports: Sequence[Report] = await services.owner_reports.reports(tenant) if owner else ()
    incidents = [
        i
        for i in await services.operation.incidents(tenant)
        if visibility.may_see_process(reader, ProcessRef(id=i.process_id, tenant=i.tenant))
    ]
    judged = [
        j
        for c, j in await services.operation.signals(tenant)
        if visibility.may_see_process(reader, ProcessRef(id=c.process, tenant=c.tenant))
    ]
    alerted = await services.operation.alerts(tenant) if owner else None
    operation = summary(
        tenant,
        incidents,
        judged,
        None
        if alerted is None
        else (alerted, await services.operation.backup(tenant), newest_daily(reports)),
    )
    failures = await _failures(services, reader)
    autonomy = await autonomy_processes(services, reader, overview)

    open_reports = [r for r in reports if r.state is not ReportState.FILED]
    needs = [r for r in open_reports if r.kind is ReportKind.NEED]
    in_effect = [a for a in alerted or () if a.alert.in_effect and not a.closed]
    # A decision request is listed as one, and an alert's report as the alert: never twice.
    alerts = {a.alert.id for a in alerted or ()}
    asked = [
        r
        for r in open_reports
        if r.kind not in (ReportKind.NEED, ReportKind.DECISION) and r.id not in alerts
    ]
    today = services.clock.now().date()
    found: list[Waiting] = [
        Waiting(
            kind=WaitKind.DECISION,
            title=one_line(a.request.request.question),
            link=f"#/requests/{a.request.id}",
            since=a.request.raised_at,
            urgent=a.overdue,
        )
        for a in addressed
    ]
    found += [
        Waiting(
            kind=WaitKind.NEED if r.kind is ReportKind.NEED else WaitKind.REPORT,
            title=one_line(r.title),
            link=f"#/reports/{r.id}",
            since=r.raised_at,
            urgent=r.due < today,
        )
        for r in (*needs, *asked)
    ]
    found += [
        Waiting(
            kind=WaitKind.ALERT,
            title=one_line(a.alert.title),
            link="#/alerts",
            since=a.alert.since,
            urgent=True,
        )
        for a in in_effect
    ]
    found += failures
    counted = await _counted(services, reader)
    running_now = sum(area.working for area in overview.areas)
    return {
        "overview": overview.document(),
        "counts": {
            "waiting_for_you": len(addressed) + len(needs) + len(asked) + len(in_effect),
            "running_now": running_now,
            "waiting_on_a_person": counted.get(str(RunState.WAITING_HUMAN), 0),
            "failed_last_24h": len(failures),
            "open_incidents": sum(1 for i in incidents if i.state is IncidentState.OPEN),
            "open_alerts": None if alerted is None else len(in_effect),
        },
        "waits": [w.document() for w in waits(found)],
        "marks": {
            "requests": {
                "waiting": len(addressed),
                "overdue": sum(1 for a in addressed if a.overdue),
            },
            "needs": {"readable": owner, "open": len(needs) if owner else None},
            "autonomy": {
                "below": sum(1 for p in autonomy if p["in_force"] < p["stated"]["level"]),
                "raises": sum(len(p["raises_proposed"]) for p in autonomy),
            },
            "findings": await _findings(services, reader, owner),
            "operation": operation,
        },
    }


async def _counted(services: RestServices, reader: Reader) -> dict[str, int]:
    """The runs the reader may count, by state: one count where the runs are stored."""
    async with services.work.transaction(reader.tenant):
        counted = await services.runs.count(reader.tenant, ("process_version", "state"))
    by_state: dict[str, int] = {}
    for (version, state), n in counted.items():
        process = str(version).rpartition("@")[0]
        if not visibility.may_see_process(
            reader, ProcessRef(id=process, tenant=reader.tenant)
        ) or not visibility.may_count(
            reader, CountedRuns(tenant=reader.tenant, process_version=str(version))
        ):
            continue
        by_state[str(state)] = by_state.get(str(state), 0) + n
    return by_state


async def _failures(services: RestServices, reader: Reader) -> list[Waiting]:
    """Each run that escalated in the last day and the reader may see, once, at its newest
    escalation; a rehearsal's left out. Read from the ledger's last day alone."""
    since = services.clock.now() - FAILED_WITHIN
    async with services.work.transaction(reader.tenant):
        entries = await services.ledger.of_kinds(reader.tenant, {FAILED}, since=since)
    newest: dict[str, Waiting] = {}
    for entry in entries:
        run_id, version = entry.refs.run_id, entry.refs.process_version
        if run_id is None or version is None or entry.rehearsal:
            continue
        ref = RunRef(id=run_id, tenant=reader.tenant, process_version=version)
        if not visibility.may_see(reader, ref):
            continue
        newest[run_id] = Waiting(
            kind=WaitKind.FAILURE,
            title=one_line(f"Run {run_id} of {version} failed"),
            link=f"#/runs/{run_id}",
            since=entry.ts,
        )
    return list(newest.values())


async def _findings(services: RestServices, reader: Reader, owner: bool) -> dict[str, Any]:
    """The findings' level, and how many wait for a review. Counted only where a person
    reviews them, at the level `review`; at another level none waits, and nothing is read."""
    found = services.findings
    if not owner or found is None:
        return {"readable": False}
    if found.level != "review":
        return {"readable": True, "level": found.level, "in_review": 0}
    return {
        "readable": True,
        "level": found.level,
        "in_review": len(await found.pending(reader.tenant)),
    }
