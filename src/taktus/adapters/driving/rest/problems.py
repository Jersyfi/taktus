"""RFC 9457 problem details: every error the surface answers has this one shape."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

MEDIA_TYPE = "application/problem+json"

TITLES = {
    400: "Bad request",
    401: "Unauthorized",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    422: "Unprocessable content",
    503: "Service unavailable",
}


def problem(status: int, detail: str, *, title: str | None = None, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title or TITLES.get(status, "Error"),
        "status": status,
        "detail": detail,
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type=MEDIA_TYPE)


async def on_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):  # registered for HTTPException only
        raise exc
    return problem(exc.status_code, str(exc.detail), instance=str(request.url.path))


async def on_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # registered for that class only
        raise exc
    findings = "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}" for e in exc.errors()
    )
    return problem(422, findings or "the request does not validate", instance=str(request.url.path))
