"""A person takes over a running step and hands the result back, on the HTTP surface
(ADR-0128, issue #404).

- `POST /runs/{run_id}/steps/{step_id}/takeover` — asks to take over a running worker step.
- `GET /runs/{run_id}/takeovers/{takeover_id}` — the state the step was taken over in.
- `POST /runs/{run_id}/takeovers/{takeover_id}/hand-back` — the result, handed back.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A run of another
tenant, one the reader may not see, or one that does not exist, is answered `404` alike. Until
rights per role exist (UC-7.3), an identity that may see the run may take its step over and hand
it back. The person is named as the actor of the ask and of the hand-back, for the audit only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.reporting.domain.model import Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.components.run.application.service import HandBack, TakeOver
from taktus.components.run.domain.model import (
    RunError,
    TakeoverRefused,
    UnknownRun,
    UnknownTakeover,
)
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class HandBackBody(BaseModel):
    result: Any = Field(
        description="The step's result, as one JSON value. It is kept as the step's artifact "
        "`<takeover>.result`, and the steps after it read it as they would the worker's."
    )


def _refused(error: RunError) -> JSONResponse:
    if isinstance(error, UnknownRun | UnknownTakeover):
        return problem(404, str(error))
    if isinstance(error, TakeoverRefused):
        return problem(409, str(error))
    return problem(422, str(error))


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["takeover"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No such run or take-over that you may see.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    async def visible(who: Resolution, run_id: str) -> bool:
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        async with services.work.transaction(who.tenant):
            run = await services.runs.get(who.tenant, run_id)
        if run is None:
            return False
        ref = RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        return visibility.may_see(reader, ref)

    @routes.post(
        "/runs/{run_id}/steps/{step_id}/takeover",
        summary="Take over a running step",
        description="Asks that you take over a running worker step. The runner that holds the "
        "run stops the step at its worker's next boundary, and passes the run to you with the "
        "state the step reached. Only the first ask of a run is taken. Read the state at the "
        "take-over's own address once it is served; until then that address answers `404` "
        "(ADR-0128).",
        responses={
            202: {"description": "Asked: the take-over's identifier, and where to read it."},
            409: {
                "description": "Not a running worker step, no runner holds the run, or a "
                "take-over of it is asked or held already.",
                **PROBLEM,
            },
            **common,
        },
    )
    async def take_over(
        run_id: str, step_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if not await visible(who, run_id):
            return problem(404, f"no run {run_id!r} that you may see")
        try:
            takeover = await services.takeovers.take_over(
                TakeOver(run_id=run_id, step_id=step_id, actor=who.identity, tenant=who.tenant)
            )
        except RunError as error:
            return _refused(error)
        return JSONResponse(
            {
                "takeover": takeover,
                "run_id": run_id,
                "step_id": step_id,
                "state": "asked",
                "read": f"runs/{run_id}/takeovers/{takeover}",
            },
            status_code=202,
        )

    @routes.get(
        "/runs/{run_id}/takeovers/{takeover_id}",
        summary="The state a step was taken over in",
        description="The step's goal, acceptance criteria and inputs, the worker's checkpoint, "
        "what the worker produced so far by identifier and digest, and until when you hold "
        "it. Answered `404` while the take-over is asked and not yet served, and once it was "
        "handed back or its lease lapsed (ADR-0128 §3).",
        responses={200: {"description": "The take-over's state."}, **common},
    )
    async def state(
        run_id: str, takeover_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if not await visible(who, run_id):
            return problem(404, f"no run {run_id!r} that you may see")
        try:
            document = await services.takeovers.takeover_state(who.tenant, run_id, takeover_id)
        except RunError as error:
            return _refused(error)
        return JSONResponse(document)

    @routes.post(
        "/runs/{run_id}/takeovers/{takeover_id}/hand-back",
        summary="Hand back the result of a step you took over",
        description="The result becomes the step's, produced by a person: the step succeeds "
        "with method `human`, its provenance names what it read and you as its origin, and the "
        "run continues on the next runner (ADR-0128 §5).",
        responses={
            200: {"description": "The run, with the step handed back."},
            409: {
                "description": "The take-over's lease lapsed and the step went back to its "
                "worker; nothing was handed back.",
                **PROBLEM,
            },
            **common,
        },
    )
    async def hand_back(
        run_id: str,
        takeover_id: str,
        body: HandBackBody,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if not await visible(who, run_id):
            return problem(404, f"no run {run_id!r} that you may see")
        try:
            run = await services.takeovers.hand_back(
                HandBack(
                    run_id=run_id,
                    takeover=takeover_id,
                    result=body.result,
                    actor=who.identity,
                    tenant=who.tenant,
                )
            )
        except RunError as error:
            return _refused(error)
        return JSONResponse(run.document())

    return routes
