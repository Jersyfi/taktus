"""A process's evaluations on its cases, and the cases proposed from corrections, on the HTTP
surface (UC-4.18, ADR-0134 §9).

- `GET /processes/{process_id}/evaluations` — the process's evaluations, newest first.
- `GET /processes/{process_id}/evaluations/{evaluation_id}` — one, with its scores per case.
- `GET /processes/{process_id}/evaluation-cases` — the cases proposed from corrections.
- `POST /processes/{process_id}/evaluation-cases/{case_id}/confirm` — a proposed case enters
  the set, with its target or the one given.
- `POST /processes/{process_id}/evaluation-cases/{case_id}/reject` — it never does.

Each needs an account key in `Authorization: Bearer`. A process, an evaluation or a case of
another tenant, or one that does not exist, is answered `404` alike. Until rights per role exist
(UC-7.3), an identity the tenant knows may confirm a case, as it may change the process.
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
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class ConfirmBody(BaseModel):
    target: Any = Field(
        default=None,
        description="The result the step should have produced, where it is not the corrected "
        "value the case was proposed with.",
    )


def _refused(error: ProposalError) -> JSONResponse:
    return problem(404 if error.kind == "unknown" else 409, str(error), kind=error.kind)


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["evaluations"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No such process, evaluation or case you may see.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.get(
        "/processes/{process_id}/evaluations",
        summary="The evaluations of a process on its cases",
        description="Every evaluation of the process: a proposal held to the active version, or "
        "the active version run again with no change. Newest first (ADR-0134).",
        responses={200: {"description": "The evaluations."}, **common},
    )
    async def evaluations(
        process_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.evaluations.of_process(who.tenant, process_id)
        return JSONResponse({"evaluations": [e.document() for e in found]})

    @routes.get(
        "/processes/{process_id}/evaluations/{evaluation_id}",
        summary="One evaluation, with its scores per case",
        description="The case runs, every scorer's score and how it was reached, the model that "
        "answered each step, the scores of each side, the tolerance and the verdict (ADR-0134).",
        responses={200: {"description": "The evaluation."}, **common},
    )
    async def evaluation(
        process_id: str, evaluation_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            found = await services.evaluations.get(who.tenant, process_id, evaluation_id)
        except ProposalError as error:
            return _refused(error)
        return JSONResponse(found.document())

    @routes.get(
        "/processes/{process_id}/evaluation-cases",
        summary="The cases proposed from corrections",
        description="A case proposed from a person's correction of a step's result, newest "
        "first: proposed, confirmed, rejected, or withheld because it would keep personal data "
        "the tenant does not allow (ADR-0134 §7).",
        responses={200: {"description": "The cases."}, **common},
    )
    async def cases(
        process_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.evaluations.cases_of(who.tenant, process_id)
        return JSONResponse({"cases": [c.document() for c in found]})

    @routes.post(
        "/processes/{process_id}/evaluation-cases/{case_id}/confirm",
        summary="Confirm a proposed case",
        description="The case enters the process's evaluation set, with the target it was "
        "proposed with or the one you give. The ledger records `evaluation.case_confirmed` with "
        "you as its actor.",
        responses={
            200: {"description": "The case, confirmed."},
            409: {"description": "The case is no longer proposed.", **PROBLEM},
            **common,
        },
    )
    async def confirm(
        process_id: str,
        case_id: str,
        body: ConfirmBody,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            confirmed = await services.evaluations.confirm(
                who.tenant, process_id, case_id, who.identity, body.target
            )
        except ProposalError as error:
            return _refused(error)
        return JSONResponse(confirmed.document())

    @routes.post(
        "/processes/{process_id}/evaluation-cases/{case_id}/reject",
        summary="Reject a proposed case",
        description="The case never enters the set. The ledger records "
        "`evaluation.case_rejected` with you as its actor.",
        responses={
            200: {"description": "The case, rejected."},
            409: {"description": "The case is no longer proposed.", **PROBLEM},
            **common,
        },
    )
    async def reject(
        process_id: str, case_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            rejected = await services.evaluations.reject(
                who.tenant, process_id, case_id, who.identity
            )
        except ProposalError as error:
            return _refused(error)
        return JSONResponse(rejected.document())

    return routes
