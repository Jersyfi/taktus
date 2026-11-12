"""A deprecated operation of the HTTP surface says so in every answer (ADR-0220 §3, §4).

An operation is deprecated by `deprecated(since=..., removal=...)`, given to its decorator: it
marks the operation in `api/openapi.yaml` with `deprecated: true`, `x-taktus-deprecated` and
`x-taktus-removal`. `Deprecations` is the middleware that answers each call of such an operation
with the header `Deprecation` of RFC 9745, the date of its deprecation as a structured date, and
`Taktus-Removal`, the product major that removes it. An operation that is not deprecated gets
neither header.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REMOVAL = re.compile(r"[1-9][0-9]*\.0\.0")
"""A removal is a product major: only a major removes (ADR-0220 §1)."""
SINCE = re.compile(r"\d{4}-\d{2}-\d{2}")


def deprecated(*, since: str, removal: str) -> dict[str, Any]:
    """The keyword arguments that deprecate an operation: `@routes.get(..., **deprecated(...))`."""
    if not SINCE.fullmatch(since):
        raise ValueError(f"a deprecation's date is YYYY-MM-DD, not {since!r}")
    date.fromisoformat(since)
    if not REMOVAL.fullmatch(removal):
        raise ValueError(f"a removal is a product major N.0.0, not {removal!r}")
    return {
        "deprecated": True,
        "openapi_extra": {"x-taktus-deprecated": since, "x-taktus-removal": removal},
    }


def headers(extra: dict[str, Any] | None) -> dict[str, str]:
    """The headers of a deprecated operation's answer, from its OpenAPI extension; none for an
    operation that names no removal."""
    if not extra or "x-taktus-removal" not in extra:
        return {}
    since = datetime.combine(
        date.fromisoformat(str(extra["x-taktus-deprecated"])), datetime.min.time(), UTC
    )
    return {
        "Deprecation": f"@{int(since.timestamp())}",
        "Taktus-Removal": str(extra["x-taktus-removal"]),
    }


class Deprecations:
    """Adds the headers of ADR-0220 §4.1 to the answer of a deprecated operation. A plain ASGI
    middleware, so that a streamed answer stays streamed: the router has placed the matched
    route in the scope by the time the answer starts."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def sending(message: Message) -> None:
            if message["type"] == "http.response.start":
                route = scope.get("route")
                if route is not None and getattr(route, "deprecated", False):
                    found = headers(getattr(route, "openapi_extra", None))
                    if found:
                        answer = MutableHeaders(scope=message)
                        for name, value in found.items():
                            answer[name] = value
            await send(message)

        await self.app(scope, receive, sending)
