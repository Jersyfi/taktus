"""The gallery a person chooses a first process from, on the HTTP surface (UC-10.4, ADR-0136 §5).

- `GET /gallery` — every gallery blueprint, each with its processes: name, reason, autonomy
  level, steps and choices, or why one is not offered.
- `POST /gallery/{blueprint}/{process}/proposals` — the process, with the person's choices, as a
  proposal; it is rehearsed and commissioned as any proposal is (ADR-0091).

Each needs an account key in `Authorization: Bearer`, or the web app's session. Nothing here
registers anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.process.application.service.proposals import ProposalError
from taktus.components.process.domain.model import InvalidProcess
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class ChooseBody(BaseModel):
    choices: dict[str, Any] = Field(
        default_factory=dict,
        description="The value of each choice the process offers, by its name; a choice left "
        "out keeps the value the gallery shows.",
    )


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["gallery"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.get(
        "/gallery",
        summary="The gallery of first processes",
        description="Every gallery blueprint the instance's gallery directory holds, each with "
        "its processes as the gallery offers them, or why one is not offered (ADR-0136 §2). "
        "An instance with no gallery answers an empty list.",
        responses={200: {"description": "The gallery."}, **common},
    )
    async def listed(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        return JSONResponse({"blueprints": services.gallery.listed()})

    @routes.post(
        "/gallery/{blueprint_id}/{process_id}/proposals",
        summary="Propose a process from the gallery",
        description="The process, with your choices written into its schedule triggers, becomes "
        "a proposal: against its active version where the tenant has one, against none "
        "otherwise (ADR-0136 §3, §4). Rehearse it and commission it as any proposal.",
        responses={
            201: {"description": "The proposal."},
            400: {"description": "Not offered, or refused; every finding.", **PROBLEM},
            404: {"description": "No such blueprint or process in the gallery.", **PROBLEM},
            409: {"description": "The proposal cannot be made in the process's state.", **PROBLEM},
            **common,
        },
    )
    async def propose(
        blueprint_id: str,
        process_id: str,
        body: ChooseBody,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            made = await services.gallery.propose(
                who.tenant, blueprint_id, process_id, body.choices, who.identity
            )
        except ProposalError as error:
            return problem(404 if error.kind == "unknown" else 409, str(error))
        except InvalidProcess as error:
            return problem(400, "the process cannot be proposed", findings=list(error.findings))
        return JSONResponse(made.document(), status_code=201)

    return routes
