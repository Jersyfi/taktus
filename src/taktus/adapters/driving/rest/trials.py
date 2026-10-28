"""A model tried on fixed cases before it is introduced, proposed or changed, on the HTTP
surface (#448, ADR-0149).

- `GET /trials` — the tenant's trials, newest first, and the trials offered now.
- `GET /trials/offers` — the trials offered now: a purpose whose model has answered no step
  yet, a model Taktus proposed, a model whose version changed.
- `POST /trials` — a trial started: every evaluation case of the processes that ask for the
  purpose, once per candidate, as a rehearsal with the purpose bound to the candidate.
- `GET /trials/{trial_id}` — one trial with its report: per candidate the cases passed, money,
  tokens in and out, wall time, and each case's results beside the others'.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A trial of
another tenant, or one that does not exist, is answered `404` alike. Until rights per role exist
(UC-7.3), an identity the tenant knows may start a trial, as it may rehearse a proposal. Starting
one binds no model: the choice stays the person's act (M3.12, M3.14).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.accounting.application.service import OCCASIONS, TrialError
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(
        pattern=r"^[a-z][a-z0-9_-]*$", description="The purpose the candidates are tried for."
    )
    candidates: list[str] = Field(
        min_length=1,
        max_length=8,
        description="The models to try, each a model of this instance's configuration, as "
        "`model.<member>`.",
    )
    occasion: str = Field(
        default="asked",
        description=f"Why the trial runs: one of {', '.join(OCCASIONS)}; `asked` unless it "
        "answers an offer.",
    )


def _refused(error: TrialError) -> JSONResponse:
    status = {"unknown": 404, "empty": 409}.get(error.kind, 422)
    return problem(status, str(error), kind=error.kind)


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["trials"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.get(
        "/trials",
        summary="The model trials of your tenant, and those offered",
        description="Every trial, newest first, and the trials offered now (ADR-0149 §3).",
        responses={200: {"description": "The trials and the offers."}, **common},
    )
    async def trials(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.trials.of_tenant(who.tenant)
        offered = await services.trials.offers(who.tenant)
        return JSONResponse(
            {
                "trials": [t.document() for t in found],
                "offers": [o.document() for o in offered],
            }
        )

    @routes.get(
        "/trials/offers",
        summary="The model trials offered now",
        description="A trial is offered when a purpose's model has answered no step yet and no "
        "trial included it, when Taktus proposed another model for a purpose, and when the "
        "model a member answers as changed its version since the purpose's last trial. An offer "
        "is never started on its own (ADR-0149 §3).",
        responses={200: {"description": "The offers."}, **common},
    )
    async def offers(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        offered = await services.trials.offers(who.tenant)
        return JSONResponse({"offers": [o.document() for o in offered]})

    @routes.post(
        "/trials",
        summary="Start a model trial",
        description="Every evaluation case of the processes whose active version asks for the "
        "purpose runs once per candidate, as a rehearsal: nothing outside is acted on, and the "
        "purpose is bound to the candidate for that run alone. Each run is held to its "
        "version's limits. The ledger records `trial.started` with you as its actor "
        "(ADR-0149).",
        status_code=201,
        responses={
            201: {"description": "The trial, its runs submitted."},
            409: {"description": "No process asks for the purpose with cases.", **PROBLEM},
            **common,
        },
    )
    async def start(body: StartBody, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            trial = await services.trials.start(
                who.tenant, body.purpose, body.candidates, who.identity, body.occasion
            )
        except TrialError as error:
            return _refused(error)
        return JSONResponse(trial.document(), status_code=201)

    @routes.get(
        "/trials/{trial_id}",
        summary="One model trial, with its report",
        description="Per candidate the cases passed, money at each run's own price table, "
        "tokens in and out, wall time, and each case's result digests beside the other "
        "candidates'; the cases whose results differ are named. `settled` says whether every "
        "run has gone as far as it can. The report decides nothing (ADR-0149 §2, §4).",
        responses={
            200: {"description": "The trial and its report."},
            404: {"description": "No such trial of your tenant.", **PROBLEM},
            **common,
        },
    )
    async def read(trial_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            found = await services.trials.read(who.tenant, trial_id)
        except TrialError as error:
            return _refused(error)
        return JSONResponse(found.document())

    return routes
