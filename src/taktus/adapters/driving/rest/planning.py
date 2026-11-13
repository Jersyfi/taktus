"""The plan dialogue and the automation coach on the HTTP surface (ADR-0279; UC-1.2, UC-13.1,
UC-10.3, UC-13.3).

- `GET /plans` — the reader's own plan drafts; `POST /plans` opens one for what they said.
- `GET /plans/{draft}?mode=guided|expert` — the draft as the mode shows it: its parts, what it
  lacks, every estimate, every setting with its value and why, and in the guided mode the
  question asked next.
- `POST /plans/{draft}/answers` — one answer of the guided mode; `PATCH /plans/{draft}` — the
  expert mode's fields at once. Each is a new version of the draft.
- `POST /plans/{draft}/commission` — the current version commissioned by the reader; refused,
  naming what is missing or which step cannot be estimated.
- `GET /plans/templates` — the process versions a guided answer may choose from.
- `GET /coach`, `PUT /coach`, `POST /coach/hints/{hint}/dismiss|accept` — the reader's own coach:
  their hints, their settings, their own share. Nobody reads another person's.

Each needs an account key in `Authorization: Bearer`, or the web app's session. The mode is a
preference passed with the read; it grants nothing (ADR-0238 §4).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.command.application.service import (
    PlanIncomplete,
    PlanningError,
    Unestimable,
)
from taktus.components.command.application.service.coach import CoachError
from taktus.components.command.domain.service.guided import Mode
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class OpenBody(BaseModel):
    said: str = Field(default="", max_length=2000, description="What should be achieved.")
    agent: bool = Field(
        default=False,
        description="The draft works out an agent, whose role is what was said (ADR-0292).",
    )
    describes: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="The process what was said describes: commissioning the draft hands it to "
        "the describe process, whose run proposes the process's version (ADR-0290).",
    )
    act: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z-]*\.[a-z][a-z-]*$",
        description="An administrative act the draft carries out once commissioned, named as "
        "the inventory of administrative acts names it; its steps come with it (ADR-0296).",
    )
    arguments: dict[str, str] = Field(
        default_factory=dict, description="The act's arguments known so far, by name."
    )


class AnswerBody(BaseModel):
    field: str = Field(min_length=1, description="The field the guided question asked for.")
    value: Any = Field(description="The answer.")
    step_id: str | None = Field(default=None, description="For an estimate: its step.")


class FieldsBody(BaseModel):
    fields: dict[str, Any] = Field(description="The fields of the draft, set at once.")


class CoachBody(BaseModel):
    on: bool
    hints_per_week: int | None = Field(default=None, ge=0, le=7)


class AcceptBody(BaseModel):
    process_version: str = Field(min_length=1)


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["planning"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }
    refused: dict[int | str, dict[str, Any]] = {
        400: {"description": "Refused; the detail says why.", **PROBLEM},
        404: {"description": "No such draft of yours.", **PROBLEM},
        **common,
    }

    def refusal(error: Exception) -> JSONResponse:
        if isinstance(error, PlanIncomplete):
            return problem(400, str(error), missing=list(error.missing))
        if isinstance(error, Unestimable):
            return problem(400, str(error), unestimable=list(error.steps))
        if "no plan draft" in str(error):
            return problem(404, str(error))
        findings = getattr(error, "findings", None)
        if findings is not None:
            return problem(400, str(error), reason=getattr(error, "reason", None), found=findings)
        return problem(400, str(error))

    @routes.get(
        "/plans",
        summary="Your plan drafts",
        description="The drafts of your own commands, the newest change first, each as the "
        "expert mode shows it (ADR-0237).",
        responses={200: {"description": "The drafts."}, **common},
    )
    async def mine(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        drafts = await services.planning.mine(who.tenant, who.identity)
        return JSONResponse({"plans": [services.planning.view(d, Mode.EXPERT) for d in drafts]})

    @routes.get(
        "/plans/templates",
        summary="What a guided answer may choose",
        description="The tenant's process versions, by name, with the level each runs at and "
        "its steps (ADR-0238 §2).",
        responses={200: {"description": "The templates."}, **common},
    )
    async def templates(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        return JSONResponse({"templates": await services.planning.templates(who.tenant)})

    @routes.post(
        "/plans",
        summary="Open a plan draft",
        description="A new draft for what you said; nothing runs until a version of it is "
        "commissioned (ADR-0237).",
        status_code=201,
        responses={201: {"description": "The draft, in the guided mode."}, **common},
    )
    async def open_draft(
        body: OpenBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            draft = await services.planning.open(
                who.tenant,
                who.identity,
                who.org_path,
                body.said,
                agent=body.agent,
                describes=body.describes,
                act=body.act,
                arguments=body.arguments,
            )
        except PlanningError as error:
            return problem(400, str(error))
        return JSONResponse(services.planning.view(draft, Mode.GUIDED), status_code=201)

    @routes.get(
        "/plans/{draft_id}",
        summary="A plan draft, as a mode shows it",
        description="Its parts, what it lacks, every estimate as a person reads it, every "
        "setting with its value and why; in the guided mode, the question asked next.",
        responses={200: {"description": "The draft."}, **refused},
    )
    async def one(
        draft_id: str,
        mode: Annotated[Mode, Query()] = Mode.GUIDED,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            draft = await services.planning.get(who.tenant, who.identity, draft_id)
        except PlanningError as error:
            return refusal(error)
        return JSONResponse(services.planning.view(draft, mode))

    @routes.post(
        "/plans/{draft_id}/answers",
        summary="Answer the guided question",
        description="The answer becomes a new version of the draft. The guided mode offers "
        "autonomy level 1 or 2 only (ADR-0026).",
        responses={200: {"description": "The draft, in the guided mode."}, **refused},
    )
    async def answer(
        draft_id: str, body: AnswerBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            draft = await services.planning.answer(
                who.tenant, who.identity, draft_id, body.field, body.value, step_id=body.step_id
            )
        except (PlanningError, ValueError, ValidationError) as error:
            return refusal(error)
        return JSONResponse(services.planning.view(draft, Mode.GUIDED))

    @routes.patch(
        "/plans/{draft_id}",
        summary="Set fields of a draft (the expert mode)",
        description="Every field given, as one new version of the draft.",
        responses={200: {"description": "The draft, in the expert mode."}, **refused},
    )
    async def set_fields(
        draft_id: str, body: FieldsBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            draft = await services.planning.set(who.tenant, who.identity, draft_id, body.fields)
        except (PlanningError, ValueError, ValidationError) as error:
            return refusal(error)
        return JSONResponse(services.planning.view(draft, Mode.EXPERT))

    @routes.post(
        "/plans/{draft_id}/commission",
        summary="Commission the current version",
        description="Commissioning is an act of its own, recorded `plan.commissioned` with the "
        "version and your identity. Refused, writing nothing, when a part is missing or a step "
        "cannot be estimated before it starts (ADR-0237, ADR-0005). An agent draft's agent is "
        "registered in the catalogue by the same act, and named in the answer (ADR-0292). A draft "
        "that describes a process hands its goal to the describe process, and the answer names "
        "that run (ADR-0290). A draft that carries an administrative act carries it out by the "
        "same act, with your identity as its actor, and is refused with 403 when your roles do "
        "not hold the right the act needs by hand (ADR-0296).",
        responses={
            200: {"description": "The commissioned plan."},
            403: {"description": "Your roles do not hold the act's right.", **PROBLEM},
            **refused,
        },
    )
    async def commission(
        draft_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            plan, run = await services.planning.commission_and_start(
                who.tenant, who.identity, draft_id
            )
            draft = await services.planning.get(who.tenant, who.identity, draft_id)
        except PlanningError as error:
            if getattr(error, "reason", None) == "right":
                return problem(403, str(error))
            return refusal(error)
        if run is not None:
            return JSONResponse({**plan.document(), "run": run.id})
        if draft.agent is not None and draft.agent.name is not None:
            return JSONResponse(
                {**plan.document(), "agent": f"{draft.agent.name}@{draft.agent.version}"}
            )
        return JSONResponse(plan.document())

    # --- the coach -----------------------------------------------------------------------

    async def coach_view(tenant: str, identity: str) -> dict[str, Any]:
        settings = await services.coach.settings(tenant, identity)
        hints = await services.coach.hints(tenant, identity)
        lasted, checked = await services.coach.own_share(tenant, identity)
        return {
            "settings": {
                "on": settings.on,
                "hints_per_week": settings.hints_per_week,
                "default_hints_per_week": 1,
            },
            "hints": [
                {"id": h.id, "says": h.says, "procedure": h.procedure, "offered_at": h.offered_at}
                for h in hints
            ],
            "share": {"lasted": lasted, "checked": checked},
        }

    @routes.get(
        "/coach",
        summary="Your automation coach",
        description="Your hints, drawn from your own requests and shown to you only; your "
        "settings, with the default stated; and how many of your accepted hints lasted "
        "(ADR-0240).",
        responses={200: {"description": "Your coach."}, **common},
    )
    async def coach(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        return JSONResponse(_jsonable(await coach_view(who.tenant, who.identity)))

    @routes.put(
        "/coach",
        summary="Set your coach",
        description="On or off — off stops reading your requests — and how many hints a week, "
        "none to seven.",
        responses={200: {"description": "Your coach."}, **common},
    )
    async def set_coach(
        body: CoachBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        await services.coach.set(
            who.tenant, who.identity, on=body.on, hints_per_week=body.hints_per_week
        )
        return JSONResponse(_jsonable(await coach_view(who.tenant, who.identity)))

    @routes.post(
        "/coach/hints/{hint_id}/dismiss",
        summary="Dismiss a hint",
        description="The pattern is never offered to you again.",
        responses={200: {"description": "Your coach."}, **refused},
    )
    async def dismiss(hint_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            await services.coach.dismiss(who.tenant, who.identity, hint_id)
        except CoachError as error:
            return problem(404, str(error))
        return JSONResponse(_jsonable(await coach_view(who.tenant, who.identity)))

    @routes.post(
        "/coach/hints/{hint_id}/accept",
        summary="Accept a hint",
        description="The automation it led to is the process version named; whether it still "
        "runs after the tenant's period is checked and shown to you.",
        responses={200: {"description": "Your coach."}, **refused},
    )
    async def accept(
        hint_id: str, body: AcceptBody, authorization: str | None = Header(default=None)
    ) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            await services.coach.accept(who.tenant, who.identity, hint_id, body.process_version)
        except CoachError as error:
            return problem(404, str(error))
        return JSONResponse(_jsonable(await coach_view(who.tenant, who.identity)))

    return routes


def _jsonable(document: dict[str, Any]) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder

    found: dict[str, Any] = jsonable_encoder(document)
    return found
