"""What a person may ask Taktus for, and a start of it, on the HTTP surface (UC-1.13,
ADR-0159 §1 and §2).

- `GET /catalogue` — the processes the reader may start: each with what it needs, the level it
  runs at, the roles a person acts in, the one start command and how to start it on each
  channel.
- `POST /catalogue/{process_id}/start` — the process started as the person, from the web app:
  the one start command on `channel.web`. The answer is the run; its own view tracks it.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A process the
reader may not see, or one without an active version, is answered `404` alike. No ticket, no
queue and no promised time: a start is a run (principle 1).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices, StartRefused
from taktus.components.identity.domain.model import Right
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
WEB = "channel.web"
"""The channel a start from the web app's list arrives on."""


class StartBody(BaseModel):
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="The process's inputs by name, as its catalogue entry lists them.",
    )


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["catalogue"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.get(
        "/catalogue",
        summary="What you may ask Taktus for: the processes you may start",
        description="Every process with an active version you may see, in plain words: what "
        "it is for, the inputs it needs from you, the level it runs at, the roles a person acts "
        "in along it, the one start command — `run <process>@<version>`, recognised as "
        "`process.run` — and how to start it in the web app, the chat and your own agent. "
        "Each way issues that command (UC-1.13). A projection of the registered versions: it "
        "keeps no request.",
        responses={200: {"description": "The catalogue."}, **common},
    )
    async def listed(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        rights = await services.identities.rights(who)
        found = await services.agent.catalogue(who, agent_may_start=Right.START in rights)
        return JSONResponse(found.document())

    @routes.post(
        "/catalogue/{process_id}/start",
        status_code=201,
        summary="Start a process you may start, as yourself",
        description="The process's active version starts with the inputs given, through the "
        "one path every channel takes: the start command `run <process>@<version>` on "
        "`channel.web`, a commissioned plan, a run on the queue. The run acts as you; its "
        "view tracks it. An input the version requires and the body does not give refuses "
        "the start, naming each.",
        responses={
            201: {"description": "The run, as it was created."},
            404: {
                "description": "No such process, or one you may not see, or one without an "
                "active version: the three are answered alike.",
                **PROBLEM,
            },
            409: {"description": "The start was refused; the detail says why.", **PROBLEM},
            **common,
        },
    )
    async def start(
        process_id: str, body: StartBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        listed = await services.agent.catalogue(who, agent_may_start=False)
        if all(e.process != process_id for e in listed.entries):
            return problem(404, f"no process {process_id!r} with an active version you may see")
        try:
            run = await services.agent.start(who, process_id, body.inputs, channel=WEB)
        except StartRefused as error:
            return problem(409, str(error))
        return JSONResponse(
            {"run_id": run.id, "process_version": run.process_version, "state": run.state},
            status_code=201,
        )

    return routes
