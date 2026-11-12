"""Writing on a connection, granted and withdrawn by a person (ADR-0262 §2, UC-5.6).

A connection of a capability that reads until granted — the warehouse's — reads only until a
person with the right grants writing on it:

- `GET /connections/{capability}/grant` — whether writing is granted on the connection, and
  since when it was granted or withdrawn.
- `PUT /connections/{capability}/grant` — writing granted by the caller.
- `DELETE /connections/{capability}/grant` — the grant withdrawn by the caller: the connection
  reads again.

Each needs an account key in `Authorization: Bearer`, or the web app's session. The caller acts
as their own identity, which the ledger names. Only an identity holding the role `owner` holds
the right; anyone else is refused with `403`, and the refusal is recorded.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.governance.application.service import (
    Granter,
    GrantRefused,
    NotGrantable,
)
from taktus.components.governance.domain.model import ConnectionGrant
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


def shown(capability: str, grant: ConnectionGrant | None) -> dict[str, Any]:
    return {
        "capability": capability,
        "granted": grant is not None and grant.in_force,
        "changed_at": None if grant is None else grant.created_at.isoformat(),
    }


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["connections"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No connection of that capability reads until granted.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }
    acting: dict[int | str, dict[str, Any]] = {
        403: {"description": "You do not hold the right to grant writing.", **PROBLEM},
        **common,
    }

    @routes.get(
        "/connections/{capability}/grant",
        summary="Whether writing is granted on a connection",
        description="A new connection reads only: `granted` is false until a person with the "
        "right grants writing on it (ADR-0262 §2).",
        responses={200: {"description": "The grant."}, **common},
    )
    async def read(capability: str, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        grants = services.connection_grants
        return JSONResponse(shown(capability, await grants.grant(who.tenant, capability)))

    async def change(capability: str, authorization: str | None, *, give: bool) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        grants = services.connection_grants
        try:
            act = grants.give if give else grants.withdraw
            grant = await act(who.tenant, capability, by=Granter(who.identity))
        except NotGrantable as error:
            return problem(404, str(error))
        except GrantRefused as error:
            return problem(403, str(error))
        return JSONResponse(shown(capability, grant))

    @routes.put(
        "/connections/{capability}/grant",
        summary="Grant writing on a connection",
        description="From now on a step may write through the connection; the warehouse's own "
        "rights still decide what. The ledger records `connection.granted` with you as its "
        "actor (ADR-0262 §2).",
        responses={200: {"description": "The grant, in force."}, **acting},
    )
    async def grant(capability: str, authorization: str | None = Header(default=None)) -> Any:
        return await change(capability, authorization, give=True)

    @routes.delete(
        "/connections/{capability}/grant",
        summary="Withdraw the grant of writing on a connection",
        description="The connection reads only again: a write is refused before it is sent. The "
        "ledger records `connection.withdrawn` with you as its actor (ADR-0262 §2).",
        responses={200: {"description": "The grant, withdrawn."}, **acting},
    )
    async def withdraw(capability: str, authorization: str | None = Header(default=None)) -> Any:
        return await change(capability, authorization, give=False)

    return routes
