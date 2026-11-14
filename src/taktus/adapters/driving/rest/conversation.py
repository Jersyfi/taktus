"""A person's conversation with Taktus on the HTTP surface (ADR-0325, UC-1.14).

- `GET /conversation` — the reader's own conversation: its turns, the acts read back in it and
  their state, the run still forming an answer, and whether a conversation is had here at all.
- `POST /conversation` — what the reader says. It is kept, and a run forms the answer as the
  reader; `202` names the run. The answer appears in `GET /conversation` once the run kept it.
- `POST /conversation/acts/{act}` — the reader's yes or no to an act Taktus read back. A yes
  does it, through the same services as every other page; a no records that nothing was done.

Each needs an account key in `Authorization: Bearer`, or the web app's session. Nobody reads
another person's conversation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import BuildRefused, RestServices
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class SayBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000, description="What you say to Taktus.")


class ConfirmBody(BaseModel):
    yes: bool = Field(description="True: do the act as it was read back. False: do nothing.")


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["conversation"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.get(
        "/conversation",
        summary="Your conversation with Taktus",
        description="Its turns, the acts read back in it with their state, and the run still "
        "forming an answer (ADR-0325).",
        responses={200: {"description": "The conversation."}, **common},
    )
    async def view(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        return JSONResponse(await services.talking.view(who))

    @routes.post(
        "/conversation",
        summary="Say something to Taktus",
        description="Kept as your turn; a run forms the answer as you, under its own budget, "
        "and keeps it in the conversation. An act it proposes is read back and waits for your "
        "yes (ADR-0325, ADR-0008).",
        status_code=202,
        responses={
            202: {"description": "Kept; the run forming the answer."},
            400: {"description": "No answer can be formed here; the detail says why.", **PROBLEM},
            **common,
        },
    )
    async def say(body: SayBody, authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            started = await services.talking.say(who, body.text)
        except BuildRefused as error:
            return problem(400, str(error))
        return JSONResponse(started, status_code=202)

    @routes.post(
        "/conversation/acts/{act_id}",
        summary="Say yes or no to an act Taktus read back",
        description="A yes does the act as you, through the same services and checks as every "
        "other page; a no does nothing. Either is recorded, and said as Taktus's next turn.",
        responses={
            200: {"description": "The act, settled."},
            400: {"description": "No such act of yours, or settled already.", **PROBLEM},
            **common,
        },
    )
    async def confirm(
        act_id: str, body: ConfirmBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            settled = await services.talking.confirm(who, act_id, body.yes)
        except BuildRefused as error:
            return problem(400, str(error))
        return JSONResponse(settled.document())

    return routes
