"""A person sends a message to a running step, on the HTTP surface (ADR-0156 §7, issue #624).

- `POST /runs/{run_id}/steps/{step_id}/messages` — a message to a running worker step.

It needs an account key in `Authorization: Bearer`, or the web app's session. A run of another
tenant, one the reader may not see, or one that does not exist, is answered `404` alike. Until
rights per role exist (UC-7.3), an identity that may see the run may send its running step a
message, as it may take the step over (ADR-0128). The person is named as the actor of the ask,
for the audit only; the text is kept as an object the ledger names by digest.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.takeover import NEEDS_KEY, Authenticated, visible_to
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.run.application.service import SteerStep
from taktus.components.run.domain.model import MessageRefused, RunError, UnknownRun

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}


class MessageBody(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=8000,
        description="What the step's worker should take into account from its next boundary "
        "on. It is an input of the steps after that boundary; it never widens what the step "
        "may do, nor what it may consume.",
    )


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["steering"])

    @routes.post(
        "/runs/{run_id}/steps/{step_id}/messages",
        summary="Send a message to a running step",
        description="Hands a message to a running worker step whose worker declares steering. "
        "The runner that holds the run gives it to the worker, which receives it at its next "
        "boundary; the steps after that boundary have it as an input, and the step's "
        "provenance names it (ADR-0156).",
        responses={
            202: {"description": "Asked: the message's identifier."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            404: {"description": "No such run or step that you may see.", **PROBLEM},
            409: {
                "description": "The step is not a running worker step, no runner holds the "
                "run, a person holds it, or its worker declares no steering; the problem says "
                "which.",
                **PROBLEM,
            },
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def send(
        run_id: str,
        step_id: str,
        body: MessageBody,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if not await visible_to(services, who, run_id):
            return problem(404, f"no run {run_id!r} that you may see")
        try:
            message = await services.takeovers.steer(
                SteerStep(
                    run_id=run_id,
                    step_id=step_id,
                    text=body.text,
                    actor=who.identity,
                    tenant=who.tenant,
                )
            )
        except UnknownRun as error:
            return problem(404, str(error))
        except MessageRefused as error:
            return problem(409, str(error))
        except RunError as error:
            return problem(422, str(error))
        return JSONResponse(
            {"message": message, "run_id": run_id, "step_id": step_id, "state": "asked"},
            status_code=202,
        )

    return routes
