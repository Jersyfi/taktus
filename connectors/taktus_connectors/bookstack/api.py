"""How the wiki connector talks to the wiki: one HTTP client per call, the requesting identity's
token and nothing else, every answer mapped to the contract's error vocabulary.

The wiki's interface for programs is under `<base address>/api`. It authenticates a request by
the header `Authorization: Token <id>:<secret>`, and answers a fault with its HTTP status and a
body `{"error": {"code": …, "message": …}}`. The status is what is mapped: 401 is
`unauthenticated`, 403 `forbidden`, 404 `not_found`, 409 `conflict`, 422 and every other 4xx
`invalid`, 429 and 5xx `unavailable`. A connection that was refused never reached the wiki, so
its effect is `none`. A request that was sent and whose answer never came may have been acted
on, so its effect is `unknown` — and only then. The wiki's own words stay out of `detail`: they
can echo a request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

type Json = dict[str, Any]

DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class TargetError(Exception):
    """The wiki refused, failed or vanished, or the input was refused before any request.
    `cause`, `effect` and `retryable` are the contract's (`Connector.json#/$defs/Error`)."""

    cause: str
    effect: str
    retryable: bool
    detail: str

    def envelope(self, requests: int) -> Json:
        error: Json = {
            "class": "failure",
            "cause": self.cause,
            "effect": self.effect,
            "retryable": self.retryable,
            "detail": self.detail,
        }
        if requests:
            error["consumption"] = {"quota_units": requests}
        return error


class Api:
    """The wiki's interface for programs, with one token, counting requests."""

    def __init__(self, target: str, token: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.target = target.rstrip("/")
        self.requests = 0
        self._client = httpx.AsyncClient(
            base_url=f"{self.target}/api",
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            headers={"Authorization": f"Token {token}", "Accept": "application/json"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: Json | None = None) -> Json:
        return await self._call("GET", path, params=params)

    async def post(self, path: str, body: Json) -> Json:
        return await self._call("POST", path, body=body)

    async def put(self, path: str, body: Json) -> Json:
        return await self._call("PUT", path, body=body)

    async def _call(
        self, verb: str, path: str, *, params: Json | None = None, body: Json | None = None
    ) -> Json:
        self.requests += 1
        try:
            response = await self._client.request(verb, path, params=params, json=body)
        except httpx.ConnectError as error:
            raise TargetError(
                "unavailable",
                "none",
                True,
                f"the wiki could not be reached: {type(error).__name__}",
            ) from error
        except httpx.ConnectTimeout as error:
            raise TargetError(
                "unavailable", "none", True, "the wiki did not accept the connection in time"
            ) from error
        except httpx.TimeoutException as error:
            if verb == "GET":
                raise TargetError(
                    "unavailable", "none", True, "the wiki did not answer a read in time"
                ) from error
            # A write left; whether it was acted on is not known.
            raise TargetError(
                "unknown",
                "unknown",
                False,
                f"the write was sent and no answer arrived: {type(error).__name__}",
            ) from error
        except httpx.HTTPError as error:
            raise TargetError(
                "unavailable", "none", True, f"transport fault: {type(error).__name__}"
            ) from error
        return parse(response)


def parse(response: httpx.Response) -> Json:
    status = response.status_code
    if status < 300:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise TargetError(
                "unavailable", "none", True, f"the wiki answered {status} without a JSON object"
            )
        return body
    raise classify(status)


def classify(status: int) -> TargetError:
    """The wiki's status as the contract's cause."""
    detail = f"the wiki answered {status}"
    if status == 401:
        return TargetError("unauthenticated", "none", False, f"{detail}: the token is not valid")
    if status == 403:
        return TargetError("forbidden", "none", False, f"{detail}: the identity may not do this")
    if status == 404:
        return TargetError("not_found", "none", False, f"{detail}: it does not exist")
    if status == 409:
        return TargetError("conflict", "none", False, detail)
    if status == 429:
        return TargetError("unavailable", "none", True, f"{detail}: the rate limit is exhausted")
    if status >= 500:
        return TargetError("unavailable", "none", True, detail)
    return TargetError("invalid", "none", False, f"{detail}: the input was refused")
