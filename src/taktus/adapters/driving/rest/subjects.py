"""Data-protection requests and the processing evidence on the HTTP surface (ADR-0176, UC-11.2).

The same acts as `taktusctl subject` and `taktusctl evidence`, for a person who works in the web
app rather than on the instance's machine:

- `GET /subjects/requests` — the tenant's requests, oldest first: kind, state, who acted.
- `POST /subjects/requests` — a request prepared: what the tenant holds of the subject is found
  and shown. Preparing changes nothing else.
- `GET /subjects/requests/{request_id}` — one request with its holdings and its outcome.
- `POST /subjects/requests/{request_id}/confirm` — the request carried out by the caller, who
  states that they checked the requester's identity. Without the statement nothing happens. An
  access or portability export is in the answer and never stored.
- `POST /subjects/requests/{request_id}/withdraw` — a prepared request ended without acting.
- `GET /evidence` — what is processed for the tenant, where, by which adapter and kept how long,
  generated from configuration and the ledger, marked as not legally reviewed.

Each needs an account key in `Authorization: Bearer`, or the web app's session. The caller acts
as their own identity, which the ledger names; the ledger never names the subject. A request of
another tenant, or one that does not exist, is answered `404` alike.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.governance.application.service import PrepareRequest
from taktus.components.governance.domain.model import (
    RequestKind,
    RequestRefused,
    SubjectRequest,
)
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class PrepareBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RequestKind = Field(description="access, rectification, erasure or portability.")
    subject: str = Field(
        min_length=1,
        max_length=500,
        description="The subject, by the identifier the organisation's systems use — the value "
        "a case's scope names.",
    )


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_checked: bool = Field(
        description="You checked that the person asking is the subject, or may act for them. "
        "Without it nothing is carried out."
    )


def shown(request: SubjectRequest) -> dict[str, Any]:
    """The request as `taktusctl subject show` prints it: its document and a count of what it
    holds."""
    document = request.document()
    document["holds"] = {
        "runs": len(request.holdings),
        "objects": sum(len(h.objects) for h in request.holdings),
        "kept": sum(1 for h in request.holdings for o in h.objects if o.kept is not None),
        "in_flight": [h.run_id for h in request.holdings if not h.ended],
    }
    return document


def _refused(error: RequestRefused) -> JSONResponse:
    status = 404 if str(error).startswith("no request") else 409
    return problem(status, str(error))


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["data protection"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }
    one: dict[int | str, dict[str, Any]] = {
        404: {"description": "No request of that identifier in your tenant.", **PROBLEM},
        409: {"description": "The request is not in a state that allows it.", **PROBLEM},
        **common,
    }

    @routes.get(
        "/subjects/requests",
        summary="The data-protection requests of your tenant",
        description="Every request, oldest first: its kind, its state and who prepared, carried "
        "out or withdrew it (ADR-0176).",
        responses={200: {"description": "The requests."}, **common},
    )
    async def listing(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.subject_requests.list(who.tenant)
        return JSONResponse(
            {
                "requests": [
                    {
                        "id": r.id,
                        "kind": r.kind.value,
                        "state": r.state.value,
                        "created_at": r.created_at.isoformat(),
                        "prepared_by": r.prepared_by,
                        "carried_out_by": r.carried_out_by,
                        "withdrawn_by": r.withdrawn_by,
                    }
                    for r in found
                ]
            }
        )

    @routes.post(
        "/subjects/requests",
        summary="Prepare a data-protection request",
        description="Finds every run that served one of the subject's cases — through the "
        "provenance records whose scope names it and through the runs' intake — with each "
        "step, object and trace line, and stores the request as `prepared`. Changes nothing "
        "else; the ledger records `subject.request_prepared` with you as its actor and never the "
        "subject (ADR-0176 §1, §2).",
        status_code=201,
        responses={201: {"description": "The prepared request."}, 409: PROBLEM, **common},
    )
    async def prepare(body: PrepareBody, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            prepared = await services.subject_requests.prepare(
                PrepareRequest(tenant=who.tenant, kind=body.kind, subject=body.subject),
                by=who.identity,
            )
        except RequestRefused as error:
            return _refused(error)
        return JSONResponse(shown(prepared), status_code=201)

    @routes.get(
        "/subjects/requests/{request_id}",
        summary="One data-protection request",
        description="The request with its holdings and, once carried out, its outcome.",
        responses={200: {"description": "The request."}, **one},
    )
    async def show(request_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.subject_requests.get(who.tenant, request_id)
        if found is None:
            return problem(404, f"no request {request_id!r}")
        return JSONResponse(shown(found))

    @routes.post(
        "/subjects/requests/{request_id}/confirm",
        summary="Carry a prepared request out",
        description="You carry the request out and state that you checked the requester's "
        "identity; without the statement nothing happens. The holdings are found again first, "
        "and a request whose holdings changed since it was prepared is refused. An erasure "
        "erases and verifies the ledger and every erased run's provenance chain; an access or "
        "portability export is in the answer under `export` and Taktus keeps no copy; a "
        "rectification is recorded as done by you at the source (ADR-0176 §1, §3 to §5).",
        responses={200: {"description": "The request, carried out."}, **one},
    )
    async def confirm(
        request_id: str, body: ConfirmBody, authorization: str | None = Header(default=None)
    ) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            done = await services.subject_requests.confirm(
                who.tenant, request_id, by=who.identity, identity_checked=body.identity_checked
            )
        except RequestRefused as error:
            return _refused(error)
        document = shown(done.request)
        if done.export is not None:
            document["export"] = json.loads(done.export)
        return JSONResponse(document)

    @routes.post(
        "/subjects/requests/{request_id}/withdraw",
        summary="Withdraw a prepared request",
        description="Ends a prepared request without carrying it out.",
        responses={200: {"description": "The request, withdrawn."}, **one},
    )
    async def withdraw(request_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            ended = await services.subject_requests.withdraw(
                who.tenant, request_id, by=who.identity
            )
        except RequestRefused as error:
            return _refused(error)
        return JSONResponse(shown(ended))

    @routes.get(
        "/evidence",
        summary="What is processed for your tenant, generated, not legally reviewed",
        description="What is processed, where, by which adapter and kept how long, generated "
        "from the register of what acts, the active versions, the tenant's declarations, its "
        "trace retention and the ledger. Not legal advice, and it says so (ADR-0176 §8).",
        responses={200: {"description": "The processing evidence."}, **common},
    )
    async def evidence(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.processing_evidence.evidence(who.tenant)
        return JSONResponse(json.loads(json.dumps(found, ensure_ascii=False, default=str)))

    return routes
