"""The administration of the instance's tenants on the HTTP surface (ADR-0104).

An administrator lists the tenants, creates one with a display name, and renames one. Taktus
generates the identifier; a request never names one it wants. The surface admits the holder of
the instance's administration key, `Authorization: Bearer`, compared in constant time. An
account key of an identity is not admitted: an identity belongs to one tenant, and
administering the instance from inside a tenant would reach past that tenant's boundary.
Without the key configured, the routes answer 404 and say how to enable them.

The same key exports a tenant — everything the instance holds of it, in one document — and
imports such a document into a tenant that holds nothing here, answering what the check of its
chains found (ADR-0221).
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from taktus.adapters.driving.inventory import read_recorded
from taktus.adapters.driving.rest.problems import problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.identity.application.service import BadName, NoSuchTenant
from taktus.ports.persistence import TenantEntry, TenantNotEmpty

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


def tenant_document(entry: TenantEntry) -> dict[str, Any]:
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
        every = await services.tenants.every()
        for entry in every:
            await read_recorded(
                services.ledger, services.work, entry.id, "tenant.list", "administrator"
            )
        return JSONResponse({"tenants": [tenant_document(e) for e in every]})

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
        return JSONResponse(tenant_document(entry), status_code=201)

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
        return JSONResponse(tenant_document(entry))

    @routes.get(
        "/administration/tenants/{tenant}/export",
        summary="Export a tenant",
        description="Everything the instance holds of the tenant — processes, runs, ledger, "
        "provenance, artifacts, identities — in one document, with the newest hash of every "
        "chain and the document's own digest, for another instance to import (ADR-0221). The "
        "export is an entry of the tenant's ledger, `tenant.exported`, after it was read. It "
        "holds the tenant's data: keep it as a backup is kept.",
        responses={
            200: {"description": "The export.", "content": {"application/json": {}}},
            401: refused[401],
            404: {"description": "No such tenant, or the administration is off.", **PROBLEM},
            409: {"description": "This instance keeps its state in files.", **PROBLEM},
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def export(tenant: str, authorization: str | None = Header(default=None)) -> Response:
        if (refusal := admitted(authorization)) is not None:
            return refusal
        exports = services.tenant_exports
        if exports is None:
            return problem(409, "an export reads the database; this instance has none")
        try:
            content = await exports.export(tenant, by="administrator")
        except ValueError as error:
            return problem(404, str(error))
        return Response(content, media_type="application/json")

    @routes.post(
        "/administration/tenants/import",
        summary="Import a tenant",
        description="An export written into this instance, into a tenant that holds nothing "
        "here, then checked: the ledger verified from its first entry, every chain's newest "
        "entry the one the export names, every run's provenance chain verified. The body is "
        "the export as `GET …/export` answered it. The import is an entry of the tenant's "
        "ledger, `tenant.imported`, after the check (ADR-0221).",
        status_code=201,
        responses={
            201: {"description": "What was written and what the check found."},
            401: refused[401],
            404: refused[404],
            409: {"description": "The tenant holds something here already.", **PROBLEM},
            422: {"description": "Not an export, or one whose bytes changed.", **PROBLEM},
        },
    )
    async def imported(request: Request, authorization: str | None = Header(default=None)) -> Any:
        if (refusal := admitted(authorization)) is not None:
            return refusal
        exports = services.tenant_exports
        if exports is None:
            return problem(409, "an import writes the database; this instance has none")
        try:
            done = await exports.import_(await request.body(), by="administrator")
        except TenantNotEmpty as error:
            return problem(409, str(error))
        except ValueError as error:
            return problem(422, str(error))
        return JSONResponse(
            {**done.document(), "verified": done.verified},
            status_code=201 if done.verified else 200,
        )

    return routes
