"""The FastAPI application: every route under the configured prefix.

Health and readiness are two different questions. `/health` says the process is alive — it
answers, therefore it is — and a platform restarts a process that stops answering it.
`/ready` says the process may receive traffic: the database answers and its schema is the one
this build needs. A role that has lost its database is not ready and must not receive traffic;
it is not therefore unhealthy, and restarting it in a loop would only make the outage louder.

The prefix is applied to every route literally, so that an instance placed under a sub-path by
the platform works whether or not the platform strips the prefix before forwarding, and every
link it produces is right. The OpenAPI document (`api/openapi.yaml`, `make generate`) is
generated at the root and names the prefix as a server variable.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from taktus.adapters.driving.rest.problems import on_http_exception, on_validation_error, problem
from taktus.adapters.driving.rest.wiring import RestServices

VERSION = "0.1.0"


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
    return app


def _operations(services: RestServices) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/health",
        summary="Liveness: the process is alive",
        tags=["operations"],
        responses={200: {"description": "The process answers."}},
    )
    async def health() -> dict[str, Any]:
        return {"status": "alive"}

    @router.get(
        "/ready",
        summary="Readiness: the process may receive traffic",
        tags=["operations"],
        responses={
            200: {"description": "The database answers and is at the schema this build needs."},
            503: {
                "description": "Not ready; the problem's detail says why.",
                "content": {"application/problem+json": {}},
            },
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
