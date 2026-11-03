"""A tenant's introduction in stages, on the HTTP surface (ADR-0137, ADR-0191, UC-9.6).

- `GET /stages` — every stage of the tenant's plan: its state, its condition in words, the
  figures the rule read from the ledger, what is missing, and each process it adds with its
  version, its level and what it did within the window. Computed at the moment of the request.
- `POST /stages/{stage_id}/open` — a person opens a stage, on the rule's figures. Taktus never
  opens one by itself.

Both need an account key in `Authorization: Bearer`, or the web app's session, of an identity
that holds the plan's responsible role: the role a proposal to open a stage and a stage that
stopped holding are reported to. The person who opens is the actor of `stage.opened`, for the
audit only. No figure names a person (principle 14): the view names stages, processes and roles.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.governance.application.service import StagesRefused
from taktus.components.governance.domain.model import StageState, StageView
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
STATES = {
    StageState.CLOSED: "not open",
    StageState.OPEN: "open, and its condition has not held yet",
    StageState.HOLDING: "open, and holding",
    StageState.NOT_HOLDING: "open, and no longer holding: it grants nothing until it holds again",
}


def stage_document(view: StageView) -> dict[str, Any]:
    """A stage as its reader reads it: the condition in words beside the figures, and one
    sentence that says where it stands."""
    document = view.document()
    document["condition"] = view.stage.condition.described()
    sentence = f"Stage {view.position} — {view.stage.name}: {STATES[view.state]}."
    if view.missing:
        sentence += " Missing: " + "; ".join(view.missing) + "."
    document["text"] = sentence
    return document


def summary(views: list[StageView]) -> str:
    if not views:
        return "No stages are declared for this tenant (`taktusctl stage declare`)."
    opened = [v for v in views if v.state is not StageState.CLOSED]
    if not opened:
        return f"{len(views)} stages declared; none is open yet."
    current = opened[-1]
    return (
        f"{len(views)} stages declared; the furthest open is stage {current.position}, "
        f"{current.stage.name}, {STATES[current.state]}."
    )


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["stages"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        403: {"description": "You do not hold the plan's responsible role.", **PROBLEM},
        404: {"description": "The tenant declared no stages, or no such stage.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    async def responsible(authorization: str | None) -> Resolution | JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        plan = await services.stages.plan(who.tenant)
        if plan is None:
            return problem(404, "this tenant declared no stages (`taktusctl stage declare`)")
        if plan.responsible not in who.roles:
            return problem(
                403,
                f"the stages are read and opened by the role {plan.responsible!r}, which you "
                "do not hold",
            )
        return who

    @routes.get(
        "/stages",
        summary="The tenant's introduction in stages, with the evidence of each",
        description="Every stage of the tenant's plan, in the order they open: its state, its "
        "condition in words, the figures the rule read from the ledger, what is missing, and "
        "each process it adds with its active version, its level and what it did within the "
        "window (ADR-0137, ADR-0191). Computed at the moment of the request, never entered. "
        "For the holders of the plan's responsible role. No figure names a person.",
        responses={200: {"description": "The stages."}, **common},
    )
    async def stages(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await responsible(authorization)
        if isinstance(who, JSONResponse):
            return who
        views = await services.stages.view(who.tenant)
        return JSONResponse(
            {"summary": summary(views), "stages": [stage_document(v) for v in views]}
        )

    @routes.post(
        "/stages/{stage_id}/open",
        summary="Open a stage",
        description="Opens the stage for you, once every stage before it is open, the one "
        "before it holds by its rule, and every process it adds runs for the tenant with "
        "current takeover instructions (ADR-0137 §3, ADR-0191 §1). Taktus never opens a stage "
        "by itself. A refusal is recorded with its reason.",
        responses={
            200: {"description": "The stage, opened."},
            409: {"description": "The stage may not open now; the reason is given.", **PROBLEM},
            **common,
        },
    )
    async def open_stage(
        stage_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await responsible(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            view = await services.stages.open(who.tenant, stage_id, by=who.identity)
        except StagesRefused as error:
            status = 404 if error.reason == "unknown" and "no stage" in str(error) else 409
            return problem(status, f"refused ({error.reason}): {error}")
        return JSONResponse(stage_document(view))

    return routes
