"""The web app's sign-in on the HTTP surface (ADR-0119).

A person exchanges their account key once, `POST /session` with `Authorization: Bearer`, for a
session cookie. The cookie is `HttpOnly`, so the page's scripts cannot read it. It is `Secure`,
so the browser sends it over HTTPS only (and to `localhost`). It is `SameSite=Strict`, so the
browser does not send it with a request another site starts. `DELETE /session` ends it.

Wherever the surface accepts the account key, it accepts the cookie. `SessionCookies` turns a
cookie into the request's credential before any route reads it, as the internal scheme
`Session`. A request that carries its own `Authorization` header is left as it is: the bearer
key keeps working for every other client, and the cookie is then not read. A credential of the
scheme `Session` that a client sends itself is dropped, so that the token is accepted from the
cookie and nowhere else.

A request that changes state and is authenticated by the cookie must come from the instance's
own pages. `SameSite=Strict` is the first guard. The second is the request's own word on where
it comes from: `Sec-Fetch-Site: same-origin` where the browser sends it, otherwise an `Origin`
whose host is the host the request was sent to. A request with neither is refused with `403`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse, Response
from starlette.requests import cookie_parser

from taktus.adapters.driving.rest.problems import problem
from taktus.adapters.driving.rest.wiring import RestServices

COOKIE = "taktus_session"
"""The cookie's name. It carries no `__Host-` prefix: that prefix requires `Path=/`, and an
instance under a path prefix scopes its cookie to the prefix (ADR-0119 §2)."""
SCHEME = "session"
"""The internal scheme a cookie is handed to the routes under."""
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CROSS_SITE = (
    "a request that changes state with the session cookie must come from this instance's own "
    "pages; use the account key in Authorization: Bearer from anywhere else"
)
PROBLEM: dict[str, Any] = {"content": {"application/problem+json": {}}}
INVALID: dict[int | str, dict[str, Any]] = {
    422: {"description": "A parameter does not validate.", **PROBLEM}
}

type Scope = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
type Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    for key, value in headers:
        if key == name:
            return value.decode("latin-1")
    return None


def same_origin(headers: list[tuple[bytes, bytes]]) -> bool:
    """Whether the request says it comes from a page of the host it was sent to."""
    site = _header(headers, b"sec-fetch-site")
    if site is not None:
        return site.strip().lower() == "same-origin"
    origin = _header(headers, b"origin")
    if not origin or origin.strip().lower() == "null":
        return False
    came_from = urlsplit(origin.strip()).netloc.lower()
    hosts = {
        (_header(headers, b"host") or "").strip().lower(),
        (_header(headers, b"x-forwarded-host") or "").split(",")[0].strip().lower(),
    }
    return bool(came_from) and came_from in hosts


class SessionCookies:
    """Hands a session cookie to the routes as the request's credential, and refuses a request
    that changes state with it from anywhere but the instance's own pages."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers: list[tuple[bytes, bytes]] = [
            (key, value)
            for key, value in scope["headers"]
            if not (key == b"authorization" and _scheme(value) == SCHEME)
        ]
        token = cookie_parser(_header(headers, b"cookie") or "").get(COOKIE, "").strip()
        if token and _header(headers, b"authorization") is None:
            if scope["method"] not in SAFE_METHODS and not same_origin(headers):
                await problem(403, CROSS_SITE)(scope, receive, send)
                return
            headers.append((b"authorization", f"Session {token}".encode("latin-1")))
        await self.app({**scope, "headers": headers}, receive, send)


def _scheme(value: bytes) -> str:
    return value.decode("latin-1").partition(" ")[0].strip().lower()


def router(services: RestServices, base: str) -> APIRouter:
    routes = APIRouter(tags=["identity"])
    path = f"{base}/"

    @routes.post(
        "/session",
        summary="Sign in to the web app: exchange your account key for a session cookie",
        description="The account key in `Authorization: Bearer` proves the identity, once. The "
        "answer sets the cookie `taktus_session`: `HttpOnly`, `Secure`, `SameSite=Strict`, "
        "scoped to the instance's path prefix, and valid for `TAKTUS_SESSION_HOURS` (12 by "
        "default). From then on the cookie is accepted wherever the account key is. The token "
        "is never in the body. The session ends at its time, on `DELETE /session`, and when the "
        "identity's key is replaced (ADR-0119).",
        status_code=201,
        responses={
            201: {"description": "Signed in: who, and until when. The cookie is set."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            **INVALID,
        },
    )
    async def sign_in(authorization: str | None = Header(default=None)) -> Response:
        scheme, _, key = (authorization or "").partition(" ")
        if scheme.lower() != "bearer":
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        signed = await services.identities.sign_in(key.strip())
        if signed is None:
            return problem(401, "the account key proves no identity")
        token, session = signed
        response = JSONResponse(
            {
                "tenant": session.tenant,
                "identity": session.identity,
                "expires_at": session.expires_at.isoformat(),
            },
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            COOKIE,
            token,
            max_age=_seconds(session.created_at, session.expires_at),
            path=path,
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return response

    @routes.delete(
        "/session",
        summary="Sign out of the web app",
        description="The session the cookie names ends now, and the answer clears the cookie. "
        "Signing out without a session clears the cookie too.",
        status_code=204,
        responses={
            204: {"description": "Signed out."},
            403: {"description": "The request did not come from the instance's pages.", **PROBLEM},
            **INVALID,
        },
    )
    async def sign_out(authorization: str | None = Header(default=None)) -> Response:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() == SCHEME:
            await services.identities.sign_out(token.strip())
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, path=path, secure=True, httponly=True, samesite="strict")
        return response

    return routes


def _seconds(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds()))
