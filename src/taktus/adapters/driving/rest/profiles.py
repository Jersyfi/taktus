"""A role's profile, on the HTTP surface (UC-15.7, ADR-0167 §3 to §5).

- `GET /roles?days=` — every role the structure holds or the processes name, each with how
  many steps it performs, takes over, decides and supervises, and its open requests.
- `GET /roles/{role}?days=` — one role's profile: what the processes need of it.
- `GET /roles/{role}/description` — the profile as a draft position description, in Markdown.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A process the
reader may not see contributes nothing (ADR-0055 §5). The profile is derived from the records on
each request and stored nowhere (ADR-0029). No figure names a person, and a figure that persons'
work produced is withheld where fewer than two identities hold the role. The profile is not
reviewed: it is not to be used before the labour-law review DEC-0029 names.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse, Response

from taktus.adapters.driving.rest.acting import visible
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.reporting.domain.service.profiles import description
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
DAYS = Query(default=30, ge=1, le=366, description="The window of runs and waits, in days.")
MARKDOWN = "text/markdown; charset=utf-8"


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["roles"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }
    unknown: dict[int | str, dict[str, Any]] = {404: {"description": "No such role.", **PROBLEM}}

    @routes.get(
        "/roles",
        summary="The roles of the tenant, and what the processes need of each",
        description="Every role the tenant's structure holds, or its processes, value streams "
        "and anchors name. Each with the number of steps it performs, takes over, decides and "
        "supervises, and its open decision requests. Not reviewed: see `review`.",
        responses={200: {"description": "The roles."}, **common},
    )
    async def listed(
        days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.profiles.index(
            who.tenant, who.identity, frozenset(who.roles), await visible(services, who), days
        )
        return JSONResponse(found.document())

    @routes.get(
        "/roles/{role}",
        summary="A role's profile, derived from the processes it takes part in",
        description="The value streams the role is responsible for and serves; the steps it "
        "performs and those it must be able to take over, with the expertise they need; what it "
        "decides and supervises; its load now and if Taktus stopped; what waits at it; the "
        "decision requests open for it. A figure that persons' work produced is withheld where "
        "fewer than two identities hold the role; a reader who holds it sees their own waits "
        "beside it. No field says whether a person is needed. Not reviewed: see `review`.",
        responses={200: {"description": "The profile."}, **unknown, **common},
    )
    async def one(
        role: str, days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.profiles.profile(
            who.tenant,
            role,
            who.identity,
            frozenset(who.roles),
            await visible(services, who),
            days,
        )
        if found is None:
            return problem(404, f"no role {role!r} in the structure or the processes")
        return JSONResponse(found.document())

    @routes.get(
        "/roles/{role}/description",
        summary="A role's profile as a draft position description",
        description="Markdown. It says that it is a draft, not to be used before the labour-law "
        "review DEC-0029 names. It carries no time figure, nothing of the reader's own and no "
        "person: a role's description, never a person's file.",
        responses={
            200: {"description": "The draft.", "content": {MARKDOWN: {}}},
            **unknown,
            **common,
        },
        response_class=Response,
    )
    async def drafted(role: str, authorization: str | None = Header(default=None)) -> Response:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.profiles.profile(
            who.tenant, role, who.identity, frozenset(), await visible(services, who), 30
        )
        if found is None:
            return problem(404, f"no role {role!r} in the structure or the processes")
        return Response(content=description(found), media_type=MARKDOWN)

    return routes
