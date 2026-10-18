"""The administration of the instance's tenants on the HTTP surface (ADR-0104).

An administrator lists the tenants, creates one with a display name, and renames one. Taktus
generates the identifier; a request never names one it wants. The surface admits the holder of
the instance's administration key, `Authorization: Bearer`, compared in constant time. An
account key of an identity is not admitted: an identity belongs to one tenant, and
administering the instance from inside a tenant would reach past that tenant's boundary.
Without the key configured, the routes answer 404 and say how to enable them.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from taktus.adapters.driving.rest.problems import problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.identity.application.service import BadName, NoSuchTenant
from taktus.ports.persistence import TenantEntry

PROBLEM: dict[str, Any] = {"content": {"application/problem+json": {}}}
NOT_ENABLED = (
    "the administration of tenants on the HTTP surface is not enabled on this instance: its "
    "operator sets TAKTUS_ADMINISTRATION_KEY_FILE; `taktusctl tenant` works without it"
)
NEEDS_KEY = "the instance's administration key is needed: Authorization: Bearer <key>"


class TenantName(BaseModel):
    """A field the surface does not know — an identifier among them — is refused."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=200,
        description="The tenant's display name: what a person reads. It may change later.",
    )
    by: str | None = Field(
        default=None,
        min_length=1,
        description="The administrator who acts, as the ledger names them. Optional.",
    )


def _document(entry: TenantEntry) -> dict[str, Any]:
    return {"id": entry.id, "name": entry.name, "created_at": entry.created_at.isoformat()}


def router(services: RestServices) -> APIRouter:
    routes = APIRouter(tags=["administration"])
    refused: dict[int | str, dict[str, Any]] = {
        401: {"description": "No administration key, or another one.", **PROBLEM},
        404: {"description": "The administration on HTTP is not enabled.", **PROBLEM},
    }

    def admitted(authorization: str | None) -> JSONResponse | None:
        """None when the request holds the administration key; otherwise the answer."""
        key = services.administration_key
        if key is None:
            return problem(404, NOT_ENABLED)
        scheme, _, given = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            given.strip().encode("utf-8"), key.reveal().encode("utf-8")
        ):
            return problem(401, NEEDS_KEY)
        return None

    @routes.get(
        "/administration/tenants",
        summary="The instance's tenants",
        description="Every tenant this instance serves, oldest first, with its identifier, its "
        "display name and when it was created.",
        responses={
            200: {"description": "The tenants."},
            **refused,
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def listed(authorization: str | None = Header(default=None)) -> JSONResponse:
        if (refusal := admitted(authorization)) is not None:
            return refusal
        return JSONResponse({"tenants": [_document(e) for e in await services.tenants.every()]})

    @routes.post(
        "/administration/tenants",
        summary="Create a tenant",
        description="A new tenant with the display name given. Taktus generates its identifier "
        "and returns it; a request never chooses one. Every role serves the tenant from its "
        "next round on, without a restart. The creation is the first entry of the new tenant's "
        "ledger, `tenant.created`.",
        status_code=201,
        responses={
            201: {"description": "The tenant created, with its generated identifier."},
            **refused,
            422: {"description": "The body does not validate.", **PROBLEM},
        },
    )
    async def create(
        body: TenantName, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        if (refusal := admitted(authorization)) is not None:
            return refusal
        try:
            entry = await services.tenants.create(body.name, by=body.by)
        except BadName as error:
            return problem(422, str(error))
        return JSONResponse(_document(entry), status_code=201)

    @routes.patch(
        "/administration/tenants/{tenant}",
        summary="Rename a tenant",
        description="The tenant's display name from now on; its identifier stays. The change "
        "is an entry of the tenant's ledger, `tenant.renamed`.",
        responses={
            200: {"description": "The tenant with its new name."},
            401: refused[401],
            404: {"description": "No such tenant, or the administration is off.", **PROBLEM},
            422: {"description": "The body does not validate.", **PROBLEM},
        },
    )
    async def rename(
        tenant: str, body: TenantName, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        if (refusal := admitted(authorization)) is not None:
            return refusal
        try:
            entry = await services.tenants.rename(tenant, body.name, by=body.by)
        except NoSuchTenant as error:
            return problem(404, str(error))
        except BadName as error:
            return problem(422, str(error))
        return JSONResponse(_document(entry))

    return routes
