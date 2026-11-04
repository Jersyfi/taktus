"""A process's takeover instructions and the trials of them, on the HTTP surface (ADR-0180,
UC-6.3).

- `GET /processes/{process_id}/takeover` — the active version's instructions, each step with
  its skills at their version in production, its trials, and whether it is untried.
- `POST /processes/{process_id}/takeover/trials` — a trial a person ran by hand: the role that
  ran it, whether they could, and what was missing.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A process the
reader may not see is answered `404`, as one that does not exist. A trial names a role, never a
person; the person who records it is the ledger entry's actor, for the audit only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.acting import visible
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.process.application.service.takeover import RecordTrial
from taktus.components.process.domain.model import InvalidProcess
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class TrialBody(BaseModel):
    role: str = Field(
        pattern=r"^[a-z][a-z0-9-]*$",
        description="The role that ran the process by hand: a role, never a person.",
    )
    passed: bool = Field(
        description="Whether the process could be run from the instructions alone."
    )
    missing: list[str] = Field(
        default_factory=list, description="What the instructions lacked, one point per entry."
    )


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["takeover"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No such process that you may see.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    async def who_sees(authorization: str | None, process_id: str) -> Resolution | JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if process_id not in await visible(services, who):
            return problem(404, f"no process {process_id!r} that you may see")
        return who

    @routes.get(
        "/processes/{process_id}/takeover",
        summary="How a person runs the process without Taktus, and the trials of it",
        description="The active version's takeover instructions: the sequence, and for every "
        "step the system to act in, what to do, the expertise, each credential by its "
        "parameter and where to find it, how to tell it is done, and the skills it uses at "
        "their version in production. With them the trials recorded and whether the version "
        "is untried: level 3 or 4 without a passed trial on it (ADR-0180).",
        responses={200: {"description": "The instructions and the trials."}, **common},
    )
    async def instructions(
        process_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await who_sees(authorization, process_id)
        if isinstance(who, JSONResponse):
            return who
        read = await services.takeover_instructions.read(who.tenant, process_id)
        if read is None:
            return problem(404, f"no process {process_id!r} with an active version")
        return JSONResponse(read)

    @routes.post(
        "/processes/{process_id}/takeover/trials",
        summary="Record a trial of the takeover instructions",
        description="A person ran the process by hand from the active version's instructions. "
        "The trial names the version, the role that ran it, whether it passed and what was "
        "missing; it is the ledger entry `takeover.trial`, with you as its actor (ADR-0180 §3).",
        status_code=201,
        responses={201: {"description": "The trial, as recorded."}, **common},
    )
    async def trial(
        process_id: str, body: TrialBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await who_sees(authorization, process_id)
        if isinstance(who, JSONResponse):
            return who
        try:
            recorded = await services.takeover_instructions.record(
                RecordTrial(
                    tenant=who.tenant,
                    process_id=process_id,
                    role=body.role,
                    passed=body.passed,
                    missing=tuple(body.missing),
                    by=who.identity,
                )
            )
        except InvalidProcess as error:
            return problem(422, "; ".join(error.findings))
        return JSONResponse(recorded.document(), status_code=201)

    return routes
