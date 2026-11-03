"""The organisation seen as value streams, on the HTTP surface (UC-15.6, ADR-0159 §4 to §6).

- `GET /streams?days=` — the map: every value stream in three tiers, management, core and
  support, each with its autonomy and method mix, flow efficiency, blocked share and the
  department boundaries it crosses, and the processes no stream names.
- `GET /streams/{stream}?days=` — one stream as role swimlanes, with the structure overlaid.
- `PUT /streams/{stream}` — the stream declared: its kind, trigger, outcome, responsible role and
  processes. Only a person who holds the role `owner` declares one. A changed declaration is a
  new revision, and the one before is kept.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A process the
reader may not see is left out of every figure (ADR-0055 §5). The views are drawn from the
records of the processes on each request and stored nowhere (ADR-0029). No figure names a person.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.acting import visible
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.process.application.service.streams import DeclareStream
from taktus.components.process.domain.model import InvalidProcess, StreamKind
from taktus.components.process.domain.model.process import ROLE
from taktus.components.process.domain.model.stream import STREAM
from taktus.components.reporting.domain.model.trace import OWNER
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
DAYS = Query(default=30, ge=1, le=366, description="The window of finished runs, in days.")


class StreamBody(BaseModel):
    name: str = Field(min_length=1, description="The stream's name, as people call it.")
    kind: StreamKind = Field(
        description="`core` from the customer's need to their outcome; `management` or "
        "`support` beside the core streams."
    )
    trigger: str = Field(min_length=1, description="The need it starts from.")
    outcome: str = Field(min_length=1, description="The outcome it ends in.")
    role: str = Field(pattern=ROLE, description="The one role responsible. Never a person.")
    processes: list[str] = Field(
        min_length=1, description="Its processes, in the order they hand over to each other."
    )


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["streams"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.get(
        "/streams",
        summary="The organisation as value streams: management, core and support",
        description="Every value stream of the tenant, in three tiers. Each shows the share of "
        "its steps at each autonomy level and of each method kind, its flow efficiency and "
        "blocked share over the runs of its processes that finished in the window, the cause "
        "that held up most, and the department boundaries it crosses — handovers between "
        "persons' steps whose roles sit in no common unit of the structure. `outside` lists "
        "the processes no stream names. Read from the records on each request; stored nowhere.",
        responses={200: {"description": "The map."}, **common},
    )
    async def listed(
        days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.streams.map(who.tenant, await visible(services, who), days)
        return JSONResponse(found.document())

    @routes.get(
        "/streams/{stream}",
        summary="One value stream as role swimlanes",
        description="A column per process in the order of the stream; a lane for Taktus's "
        "reproducible methods, one for its variable methods, and one per role a person acts in, "
        "each with the units of the structure its holders sit in (`org_path`, overlaid). Each "
        "step is a chip in its column and lane; a fallback to a person names that role's lane. "
        "A role's waiting is shown only where at least two identities hold it.",
        responses={
            200: {"description": "The swimlanes."},
            404: {"description": "No such stream.", **PROBLEM},
            **common,
        },
    )
    async def one(
        stream: str, days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.streams.lanes(who.tenant, stream, await visible(services, who), days)
        if found is None:
            return problem(404, f"no value stream {stream!r}")
        return JSONResponse(found.document())

    @routes.put(
        "/streams/{stream}",
        summary="Declare a value stream",
        description="The stream's kind, trigger, outcome, responsible role and processes. A "
        "declaration that says what the current revision says keeps nothing new; any other is "
        "the next revision, and the one before is kept. Every process it names exists in the "
        "tenant. Only a person who holds the role `owner` declares one.",
        responses={
            200: {"description": "The stream as it is now."},
            403: {"description": "You do not hold the role `owner`.", **PROBLEM},
            **common,
        },
    )
    async def declare(
        stream: str, body: StreamBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if OWNER not in who.roles:
            return problem(403, f"only the role {OWNER!r} declares a value stream")
        if not _named(stream):
            return problem(422, f"a value stream is named like a process: {STREAM}")
        try:
            declared = await services.streams.declare(
                DeclareStream(
                    tenant=who.tenant,
                    stream=stream,
                    name=body.name,
                    kind=body.kind,
                    trigger=body.trigger,
                    outcome=body.outcome,
                    role=body.role,
                    processes=tuple(body.processes),
                    by=who.identity,
                )
            )
        except InvalidProcess as error:
            return problem(422, str(error))
        return JSONResponse(declared.document())

    return routes


def _named(stream: str) -> bool:
    return re.fullmatch(STREAM, stream) is not None
