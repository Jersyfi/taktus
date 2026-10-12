"""A person's proposals for a changed process, on the HTTP surface (UC-4.15, ADR-0091 §6).

- `POST /processes/{process_id}/proposals` — a changed bundle becomes a proposal, never a version.
- `GET /processes/{process_id}/proposals` — the process's proposals, newest first.
- `GET /processes/{process_id}/proposals/{proposal_id}` — one proposal, with its difference.
- `POST /processes/{process_id}/proposals/{proposal_id}/discard` — an open proposal, discarded.

Each needs an account key in `Authorization: Bearer`. A process of another tenant, or one that
does not exist, is answered `404` alike. Until rights per role exist (UC-7.3), an identity the
tenant knows may propose, as it may register a version by hand. Nothing here registers anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.process.application.service.proposals import ProposalError, Propose
from taktus.components.process.domain.model import InvalidProcess, Proposal
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class ProposeBody(BaseModel):
    bundle: dict[str, Any] = Field(description="The changed process bundle, as a document.")
    request: str | None = Field(
        default=None, min_length=1, description="The words the change was asked for in."
    )


def _view(proposal: Proposal) -> dict[str, Any]:
    return proposal.document()


def _refused(error: ProposalError) -> JSONResponse:
    return problem(404 if error.kind == "unknown" else 409, str(error))


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["proposals"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No such process or proposal you may see.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.post(
        "/processes/{process_id}/proposals",
        summary="Propose a changed process",
        description="The changed bundle becomes a proposal, made against the active version, with "
        "its difference step by step. Nothing is registered: the active version, its triggers and "
        "its runs are unchanged. A bundle that would not register is answered with the findings "
        "registration would give, and nothing is kept (ADR-0091 §1).",
        responses={
            201: {"description": "The proposal."},
            400: {"description": "The bundle would not register; every finding.", **PROBLEM},
            **common,
        },
    )
    async def propose(
        process_id: str, body: ProposeBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            made = await services.proposals.propose(
                Propose(
                    tenant=who.tenant,
                    process_id=process_id,
                    bundle=body.bundle,
                    by=who.identity,
                    request=body.request,
                )
            )
        except ProposalError as error:
            return _refused(error)
        except InvalidProcess as error:
            return problem(400, "the bundle would not register", findings=list(error.findings))
        return JSONResponse(_view(made), status_code=201)

    @routes.get(
        "/processes/{process_id}/proposals",
        summary="The proposals for a process",
        responses={200: {"description": "The proposals, newest first."}, **common},
    )
    async def proposals(
        process_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.proposals.of_process(who.tenant, process_id)
        return JSONResponse({"proposals": [_view(p) for p in found]})

    @routes.get(
        "/processes/{process_id}/proposals/{proposal_id}",
        summary="One proposal, with its difference",
        responses={200: {"description": "The proposal."}, **common},
    )
    async def one(
        process_id: str, proposal_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            found = await services.proposals.get(who.tenant, process_id, proposal_id)
        except ProposalError as error:
            return _refused(error)
        return JSONResponse(_view(found))

    @routes.post(
        "/processes/{process_id}/proposals/{proposal_id}/discard",
        summary="Discard a proposal",
        description="An open proposal is discarded; nothing else changes.",
        responses={
            200: {"description": "The proposal, discarded."},
            409: {"description": "The proposal is no longer open.", **PROBLEM},
            **common,
        },
    )
    async def discard(
        process_id: str, proposal_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            discarded = await services.proposals.discard(who.tenant, process_id, proposal_id)
        except ProposalError as error:
            return _refused(error)
        return JSONResponse(_view(discarded))

    return routes
