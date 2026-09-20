"""How the reference connector talks to the service: one HTTP client per call, the requesting
identity's token and nothing else, every answer mapped to the contract's error vocabulary.

The mapping is the honest part. A connection that was refused never reached the service, so the
effect is `none`. A request that was sent and whose answer never came may have been acted on, so
the effect is `unknown` — and only then. The service's own words for a fault are kept out of
`detail` beyond a short message: they can carry request bodies, and a request body can carry a
credential.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx

type Json = dict[str, Any]

ACCEPT = "application/vnd.github+json"
API_VERSION = "2022-11-28"
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class TargetError(Exception):
    """The service refused, failed or vanished. `cause`, `effect` and `retryable` are the
    contract's (`Connector.json#/$defs/Error`); `status` is what the service answered, 0 when
    it did not."""

    cause: str
    effect: str
    retryable: bool
    detail: str
    status: int = 0

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
    """The service's REST interface for one repository, with one token, counting requests."""

    def __init__(
        self, target: str, repository: str, token: str, *, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        self.target = target.rstrip("/")
        self.repository = repository
        self.owner = repository.split("/", 1)[0]
        self.requests = 0
        # Where a person looks at what the API names: the service's web address, derived from
        # the API's for the real service and equal to it for a fake.
        self.web = "https://github.com" if self.target == "https://api.github.com" else self.target
        self._client = httpx.AsyncClient(
            base_url=self.target,
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            headers={
                "Accept": ACCEPT,
                "X-GitHub-Api-Version": API_VERSION,
                "Authorization": f"Bearer {token}",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: Json | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, body: Json) -> Any:
        return await self._request("POST", path, body=body)

    async def get_page(self, path: str, params: Json) -> tuple[Any, str | None]:
        """One page and the URL of the next, from the `Link` header."""
        response = await self._send("GET", path, params=params, body=None)
        return self._parse(response), _next_link(response.headers.get("Link", ""))

    async def get_url(self, url: str) -> tuple[Any, str | None]:
        response = await self._send("GET", url, params=None, body=None)
        return self._parse(response), _next_link(response.headers.get("Link", ""))

    def repo(self, tail: str) -> str:
        return f"/repos/{self.repository}/{tail}"

    async def _request(
        self, method: str, path: str, *, params: Json | None = None, body: Json | None = None
    ) -> Any:
        response = await self._send(method, path, params=params, body=body)
        return self._parse(response)

    async def _send(
        self, method: str, path: str, *, params: Json | None, body: Json | None
    ) -> httpx.Response:
        self.requests += 1
        try:
            return await self._client.request(method, path, params=params, json=body)
        except httpx.ConnectError as error:
            raise TargetError(
                "unavailable", "none", True, f"the service could not be reached: {error}"
            ) from error
        except httpx.ConnectTimeout as error:
            raise TargetError(
                "unavailable", "none", True, "the service did not accept the connection in time"
            ) from error
        except httpx.TimeoutException as error:
            # The request left; whether it was acted on is not known.
            raise TargetError(
                "unknown",
                "unknown",
                False,
                f"the request was sent and no answer arrived: {type(error).__name__}",
            ) from error
        except httpx.HTTPError as error:
            raise TargetError("unavailable", "none", True, f"transport fault: {error}") from error

    def _parse(self, response: httpx.Response) -> Any:
        if response.status_code < 300:
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError as error:
                raise TargetError(
                    "unavailable",
                    "none",
                    True,
                    "the service answered with something that is not JSON",
                ) from error
        raise classify(response)


def classify(response: httpx.Response) -> TargetError:
    """The service's status code and message, as the contract's cause."""
    status = response.status_code
    message = _message(response)
    if status == 401:
        return TargetError(
            "unauthenticated", "none", False, "the credential was not accepted", status
        )
    if status == 403:
        if response.headers.get("X-RateLimit-Remaining") == "0":
            return TargetError("unavailable", "none", True, "the rate limit is exhausted", status)
        return TargetError(
            "forbidden",
            "none",
            False,
            f"the requesting identity may not do this: {message}",
            status,
        )
    if status == 404:
        return TargetError(
            "not_found", "none", False, "the record does not exist or is not visible", status
        )
    if status == 409:
        return TargetError("conflict", "none", False, message, status)
    if status == 422:
        if "already exists" in message:
            return TargetError("conflict", "none", False, message, status)
        return TargetError("invalid", "none", False, f"the input was refused: {message}", status)
    if status == 429 or status >= 500:
        return TargetError("unavailable", "none", True, f"the service answered {status}", status)
    return TargetError(
        "invalid", "none", False, f"the service answered {status}: {message}", status
    )


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"status {response.status_code}"
    if not isinstance(body, dict):
        return f"status {response.status_code}"
    parts = [str(body.get("message", ""))]
    for error in body.get("errors", []) or []:
        if isinstance(error, dict) and error.get("message"):
            parts.append(str(error["message"]))
    return "; ".join(p for p in parts if p)[:200]


def _next_link(header: str) -> str | None:
    for part in header.split(","):
        section = part.strip().split(";")
        if len(section) >= 2 and section[1].strip() == 'rel="next"':
            return section[0].strip().strip("<>")
    return None


def digest_of(body: Json) -> str:
    """The digest of what is written: the request body in canonical form."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
