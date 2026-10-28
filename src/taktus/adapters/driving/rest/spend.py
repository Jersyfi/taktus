"""Where a process spends, per step, and two runs side by side, on the HTTP surface (#449,
ADR-0148).

- `GET /runs/{run_id}/spend` — one run by step: each step's tokens by price kind, turns, what a
  compression saved, compute seconds, money at the run's own price table, Takte at its own
  weighting table, its outcome and the digest of its result. With `against`, a second run of
  the same task beside it: both by step, and per step the difference and whether both produced
  the same result.
- `GET /processes/{process_id}/spend` — the process per step over the last `days` days, every
  run's money summed per currency.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A run the reader
may not see, or one that does not exist, is answered `404` alike, by the one predicate every
representation asks (ADR-0055 §5). No figure here names a person (principle 14): a run, a step
and a process are what is measured.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.accounting.application.service import (
    CompareRuns,
    SpendOfProcess,
    SpendOfRun,
)
from taktus.components.reporting.domain.model import ProcessRef, Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
DAYS_DEFAULT = 30
DAYS_MAXIMUM = 366


def _reader(who: Resolution) -> Reader:
    return Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["spend"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No such run or process that you may see.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    async def visible(who: Resolution, run_id: str) -> bool:
        async with services.work.transaction(who.tenant):
            run = await services.runs.get(who.tenant, run_id)
        if run is None:
            return False
        ref = RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        return visibility.may_see(_reader(who), ref)

    @routes.get(
        "/runs/{run_id}/spend",
        summary="Where one run spent, step by step",
        description="Each step's tokens by price kind (plain input, cache writes, cache reads, "
        "output), turns, the input before and after a compression, compute seconds, money at "
        "the run's own price table and Takte at its own weighting table, its outcome and the "
        "digest of its result. What cannot be priced is named, never counted as free. With "
        "`against`, another run of the same task beside it: both by step, per step the "
        "difference right less left and whether both produced the same result; where the runs "
        "are of different processes or priced at different tables, the answer says so "
        "(ADR-0148).",
        responses={
            200: {"description": "The run's spend, or the two runs side by side."},
            **common,
        },
    )
    async def of_run(
        run_id: str,
        against: str | None = Query(
            default=None, min_length=1, description="A second run to set beside this one."
        ),
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        for wanted in (run_id, *(() if against is None else (against,))):
            if not await visible(who, wanted):
                return problem(404, f"no run {wanted!r} that you may see")
        if against is None:
            spend = await services.spend.of_run(SpendOfRun(run_id, who.tenant))
            return JSONResponse(spend.document())
        compared = await services.spend.compare(CompareRuns(run_id, against, who.tenant))
        return JSONResponse(compared.document())

    @routes.get(
        "/processes/{process_id}/spend",
        summary="Where a process spent over a window, step by step",
        description="Every run of the process whose steps finished in the last `days` days, "
        "per step: what it used, how often it finished, and its money summed per currency at "
        "each run's own table (ADR-0148).",
        responses={200: {"description": "The process's spend per step."}, **common},
    )
    async def of_process(
        process_id: str,
        days: int = Query(
            default=DAYS_DEFAULT,
            ge=1,
            le=DAYS_MAXIMUM,
            description=f"How many days back from now; {DAYS_DEFAULT} unless given.",
        ),
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if not visibility.may_see_process(
            _reader(who), ProcessRef(id=process_id, tenant=who.tenant)
        ):
            return problem(404, f"no process {process_id!r} that you may see")
        until = services.clock.now()
        spend = await services.spend.of_process(
            SpendOfProcess(process_id, who.tenant, since=until - timedelta(days=days), until=until)
        )
        return JSONResponse(spend.document())

    return routes
