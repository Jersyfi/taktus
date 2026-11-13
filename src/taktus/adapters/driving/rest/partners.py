"""A mapping of a partner's messages proposed from sample data, on the HTTP surface (UC-15.3,
ADR-0315).

- `POST /contracts/mapping-drafts` — a data contract and the partner's sample messages in; the
  mapping Taktus proposes by rule out, with what it could not match and the question it asks
  back. It is stored nowhere and applied to nothing: the person confirms or corrects it by
  registering a version whose contract carries the `mapping`.

It needs an account key in `Authorization: Bearer`, or the web app's session.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.process.domain.model import DataContract
from taktus.components.process.domain.service import partners
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}


class DraftBody(BaseModel):
    contract: dict[str, Any] = Field(
        description="The data contract as a bundle states it under `contracts.<name>`."
    )
    samples: list[dict[str, Any]] = Field(
        min_length=1, max_length=50, description="The partner's sample messages, as objects."
    )


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["partners"])

    @routes.post(
        "/contracts/mapping-drafts",
        summary="Propose a mapping of a partner's messages from sample data",
        description="Each field of the contract takes the one path every sample carries whose "
        "name matches it, letter for letter or once case and separators are set aside. A field "
        "two paths match, or none, is asked back, never guessed. The draft is stored nowhere "
        "and applied to nothing: the person confirms it by registering a version whose "
        "contract carries `mapping`.",
        responses={
            200: {"description": "The draft and the question it asks back."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            422: {"description": "The contract or the samples do not validate.", **PROBLEM},
        },
    )
    async def draft(
        body: DraftBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        given = {k: v for k, v in body.contract.items() if k != "frequency"}
        try:
            contract = DataContract.model_validate(given)
        except ValidationError as error:
            return problem(
                422,
                "; ".join(
                    f"contract.{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in error.errors()
                ),
            )
        return JSONResponse(partners.propose_mapping(contract, body.samples).document())

    return routes
