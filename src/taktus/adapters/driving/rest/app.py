"""The FastAPI application: every route under the configured prefix.

Health and readiness are two different questions. `/health` says the process is alive — it
answers, therefore it is — and a platform restarts a process that stops answering it.
`/ready` says the process may receive traffic: the database answers and its schema is the one
this build needs. A role that has lost its database is not ready and must not receive traffic;
it is not therefore unhealthy, and restarting it in a loop would only make the outage louder.

The `api` role adds the rest: webhook intake for the channel a connector serves, the completion
of an intake event into a command by the configured identity, and a read API for runs and
ledger entries. No other write, no UI.

The prefix is applied to every route literally, so that an instance placed under a sub-path by
the platform works whether or not the platform strips the prefix before forwarding, and every
link it produces is right. The OpenAPI document (`api/openapi.yaml`, `make generate`) is
generated at the root and names the prefix as a server variable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from taktus.adapters.driving.rest.problems import on_http_exception, on_validation_error, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.command.application.service import (
    AlreadyCompleted,
    CompleteIntake,
    ReceiveIntake,
    UnknownChannel,
    UnknownIntakeEvent,
    UnknownSender,
)
from taktus.ports.connector import ConnectorError, Delivery, RefusalReason

VERSION = "0.1.0"
PROBLEM: dict[str, Any] = {"content": {"application/problem+json": {}}}
INVALID: dict[int | str, dict[str, Any]] = {
    422: {"description": "A parameter does not validate.", **PROBLEM}
}

# A refusal the sender should correct — no signature, a wrong one, a body that cannot be
# read — is answered with the status that says so; the rest are the sender's business
# fulfilled: the delivery was received and decided upon.
REFUSAL_STATUS = {
    RefusalReason.UNSIGNED: 401,
    RefusalReason.BAD_SIGNATURE: 401,
    RefusalReason.MALFORMED: 400,
    RefusalReason.UNSUPPORTED_EVENT: 202,
    RefusalReason.OWN_ACTION: 202,
}


def build_app(services: RestServices, *, prefix: str = "/", full: bool = True) -> FastAPI:
    """`full` is the `api` role: without it a process serves health and readiness only."""
    base = "" if prefix == "/" else prefix.rstrip("/")
    app = FastAPI(
        title="Taktus",
        version=VERSION,
        description="An operating layer for a business — the control plane's own interface.",
        openapi_url=f"{base}/openapi.json",
        docs_url=None,
        redoc_url=None,
        servers=[
            {
                "url": "{prefix}",
                "description": "The path prefix the instance is served under (TAKTUS_PATH_PREFIX).",
                "variables": {"prefix": {"default": "/"}},
            }
        ],
    )
    app.add_exception_handler(HTTPException, on_http_exception)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.include_router(_operations(services), prefix=base)
    if full:
        app.include_router(_intake(services), prefix=base)
        app.include_router(_reads(services), prefix=base)
    return app


def _operations(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["operations"])

    @router.get(
        "/health",
        summary="Liveness: the process is alive",
        responses={200: {"description": "The process answers."}},
    )
    async def health() -> dict[str, Any]:
        return {"status": "alive"}

    @router.get(
        "/ready",
        summary="Readiness: the process may receive traffic",
        responses={
            200: {"description": "The database answers and is at the schema this build needs."},
            503: {"description": "Not ready; the problem's detail says why.", **PROBLEM},
        },
    )
    async def ready() -> JSONResponse:
        reason = await services.ready()
        if reason is not None:
            return problem(503, reason, title="Not ready")
        return JSONResponse(
            {"status": "ready", "roles": list(services.roles), "leading": services.leading}
        )

    return router


def _intake(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["intake"])

    @router.post(
        "/intake/{channel}",
        summary="Webhook intake for a channel",
        description="The delivery as the source system sent it — every header, the raw body — "
        "is handed to the connector that serves the channel. The connector verifies the "
        "signature before it reads the body, then normalises the event into the channel's "
        "half of a command. The sender is placed in a tenant by the identity resolver — "
        "today the provisional operator identity (DEC-0013) — and the event is kept there "
        "until it is completed into a command. A sender that cannot be placed is answered "
        "`unknown_sender` and nothing is kept. Nothing is executed from here.",
        status_code=202,
        responses={
            202: {
                "description": "Decided: `accepted` with the intake event, `refused`, or "
                "`unknown_sender`."
            },
            400: {"description": "The body cannot be read.", **PROBLEM},
            401: {"description": "Unsigned, or the signature does not verify.", **PROBLEM},
            404: {"description": "No connector serves the channel.", **PROBLEM},
            503: {"description": "The connector did not answer.", **PROBLEM},
            **INVALID,
        },
    )
    async def intake(channel: str, request: Request) -> JSONResponse:
        body = (await request.body()).decode("utf-8", errors="replace")
        delivery = Delivery(
            headers={k: v for k, v in request.headers.items()},
            body=body,
            received_at=datetime.now(UTC),
        )
        try:
            outcome = await services.intake.execute(
                # The tenant is the resolver's to decide; the first configured tenant is the
                # fallback of an instance without an identity, and is named as such.
                ReceiveIntake(channel=channel, delivery=delivery, tenant=services.tenants[0])
            )
        except UnknownChannel as error:
            return problem(404, str(error))
        except ConnectorError as error:
            return problem(503, str(error))
        if outcome.refused is not None:
            status = REFUSAL_STATUS[outcome.refused.reason]
            if status == 202:
                return JSONResponse({"refused": outcome.refused.document()}, status_code=202)
            return problem(
                status,
                outcome.refused.detail,
                title="Refused",
                reason=outcome.refused.reason,
            )
        if outcome.unknown_sender is not None:
            return JSONResponse(
                {"unknown_sender": outcome.unknown_sender.document()}, status_code=202
            )
        if outcome.accepted is None:  # unreachable: an outcome is one of the three
            return problem(503, "the intake decided nothing")
        return JSONResponse({"accepted": outcome.accepted.document()}, status_code=202)

    tenant_query = Query(
        default=None,
        description="The tenant; the instance's first configured tenant when absent.",
    )

    @router.post(
        "/intake-events/{event_id}/complete",
        summary="Complete an intake event into a command",
        description="The event the connector accepted becomes a command: the identity resolver "
        "supplies who acts — today the provisional operator identity of the tenant "
        "(DEC-0013), marked as such in the command's context — and the event is marked "
        "completed. Nothing is executed; the command is returned for whoever commissions a "
        "plan from it.",
        status_code=200,
        responses={
            200: {"description": "The command the event became."},
            404: {"description": "No such intake event in the tenant.", **PROBLEM},
            409: {"description": "The event was completed before.", **PROBLEM},
            422: {"description": "The sender cannot be placed.", **PROBLEM},
            503: {"description": "No identity is configured.", **PROBLEM},
        },
    )
    async def complete(event_id: str, tenant: str | None = tenant_query) -> JSONResponse:
        handler = services.complete_intake
        if handler is None:
            return problem(503, "no identity is configured; nothing can complete an intake")
        chosen = tenant or services.tenants[0]
        try:
            command = await handler.execute(CompleteIntake(tenant=chosen, event_id=event_id))
        except UnknownIntakeEvent as error:
            return problem(404, str(error))
        except AlreadyCompleted as error:
            return problem(409, str(error))
        except UnknownSender as error:
            return problem(422, str(error))
        return JSONResponse(command.document(), status_code=200)

    return router


def _reads(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["runs"])
    tenant_query = Query(
        default=None,
        description="The tenant; the instance's first configured tenant when absent.",
    )

    @router.get(
        "/runs",
        summary="The runs of a tenant, newest first",
        responses={
            200: {"description": "A list of runs as the run component records them."},
            **INVALID,
        },
    )
    async def list_runs(tenant: str | None = tenant_query) -> JSONResponse:
        chosen = tenant or services.tenants[0]
        async with services.work.transaction(chosen):
            runs = list(await services.runs.list(chosen))
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return JSONResponse({"tenant": chosen, "runs": [r.document() for r in runs]})

    @router.get(
        "/runs/{run_id}",
        summary="One run",
        responses={
            200: {"description": "The run."},
            404: {"description": "No such run in the tenant.", **PROBLEM},
            **INVALID,
        },
    )
    async def get_run(run_id: str, tenant: str | None = tenant_query) -> JSONResponse:
        chosen = tenant or services.tenants[0]
        async with services.work.transaction(chosen):
            run = await services.runs.get(chosen, run_id)
        if run is None:
            return problem(404, f"tenant {chosen!r} has no run {run_id!r}")
        return JSONResponse(run.document())

    @router.get(
        "/runs/{run_id}/ledger",
        summary="The ledger entries of one run, in sequence",
        responses={
            200: {"description": "The entries, and whether the tenant's chain verifies."},
            404: {"description": "No such run in the tenant.", **PROBLEM},
            **INVALID,
        },
    )
    async def run_ledger(run_id: str, tenant: str | None = tenant_query) -> JSONResponse:
        chosen = tenant or services.tenants[0]
        async with services.work.transaction(chosen):
            run = await services.runs.get(chosen, run_id)
            if run is None:
                return problem(404, f"tenant {chosen!r} has no run {run_id!r}")
            entries = await services.ledger.entries(chosen, run_id)
            verification = await services.ledger.verify(chosen)
        return JSONResponse(
            {
                "run_id": run_id,
                "entries": [e.document() for e in entries],
                "chain": {"intact": verification.intact, "entries": verification.entries},
            }
        )

    return router
