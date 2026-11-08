"""The processes Taktus proposes, on the HTTP surface (UC-4.4, ADR-0270).

- `GET /process-proposals` — what the reader is shown: the proposals that concern no person,
  and those drawn from runs the reader started; most often recurring first, each with the order's
  reason.
- `POST /process-proposals/{proposal}/accept` — the proposal's words handed to the request path
  that builds a proposal of a version (ADR-0251 §1); nothing runs for real before a person
  commissions it.
- `POST /process-proposals/{proposal}/decline` — declined; it costs nothing and changes nothing.

Each needs a person's account key in `Authorization: Bearer`, or the web app's session. An
agent's key proves nothing here: the MCP surface offers no such tool, because a proposal drawn
from a person's own work is that person's alone (principle 14). Nothing is stored to make the
list.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import (
    NoRequestPath,
    ProcessProposalRefused,
    RestServices,
)
from taktus.components.process.domain.service.proposing import ProcessProposal
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


def shown(proposal: ProcessProposal) -> dict[str, Any]:
    """What a proposal says, and nothing else: never whom it is drawn from (ADR-0270 §2)."""
    return {
        "id": proposal.id,
        "kind": proposal.kind,
        "process_id": proposal.process_id,
        "takes_over": proposal.takes_over,
        "cost": proposal.cost,
        "why_now": proposal.why_now,
        "order": proposal.order,
        "yours": proposal.reader is not None,
    }


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["process proposals"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }
    decided: dict[int | str, dict[str, Any]] = {
        404: {
            "description": "No open proposal of that identifier is shown to you: it is decided "
            "already, or it is not yours.",
            **PROBLEM,
        },
        **common,
    }

    @routes.get(
        "/process-proposals",
        summary="The processes Taktus proposes to you",
        description="Work that recurs, found by rule in the ledger: a process you start by hand "
        "at a regular cadence, shown to you alone, and a failure healed again and again, shown "
        "to everyone of the tenant. Each says the work it would take over, its cost and why "
        "now; the list is ordered by how often the work recurs per 30 days, and each says so "
        "(ADR-0270).",
        responses={200: {"description": "The proposals, most often recurring first."}, **common},
    )
    async def listed(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.process_proposals.listed(who.tenant, who.identity)
        return JSONResponse(
            {
                "order": "how often the work recurs per 30 days",
                "proposals": [shown(p) for p in found],
            }
        )

    @routes.post(
        "/process-proposals/{proposal_id}/accept",
        summary="Accept a proposal",
        description="Its words go to the request path that builds a proposal of a version, as "
        "you; the answer names the run that builds it. Nothing runs for real before a person "
        "commissions the version (UC-4.1, ADR-0251). Recorded `proposal.accepted`.",
        responses={
            200: {"description": "The proposal, and the run that builds it."},
            400: {"description": "This instance has no request path that builds one.", **PROBLEM},
            **decided,
        },
    )
    async def accept(proposal_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            done = await services.process_proposals.accept(who.tenant, proposal_id, who.identity)
        except NoRequestPath as refused:
            return problem(400, str(refused))
        except ProcessProposalRefused as refused:
            return problem(404, str(refused))
        return JSONResponse({"proposal": shown(done.proposal), "run_id": done.run.id})

    @routes.post(
        "/process-proposals/{proposal_id}/decline",
        summary="Decline a proposal",
        description="It is not listed again; declining costs nothing and changes nothing. "
        "Recorded `proposal.declined`.",
        responses={200: {"description": "The proposal declined."}, **decided},
    )
    async def decline(proposal_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            done = await services.process_proposals.decline(who.tenant, proposal_id, who.identity)
        except ProcessProposalRefused as refused:
            return problem(404, str(refused))
        return JSONResponse({"proposal": shown(done)})

    return routes
