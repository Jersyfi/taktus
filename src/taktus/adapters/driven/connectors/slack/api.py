"""How the chat connector talks to the service: one HTTP client per call, the requesting
identity's token and nothing else, every answer mapped to the contract's error vocabulary.

The service's web interface answers most faults with status 200 and a body
`{"ok": false, "error": "<code>"}`; the code is what is mapped. A rate limit is status 429, an
outage a 5xx. A connection that was refused never reached the service, so its effect is `none`.
A request that was sent and whose answer never came may have been acted on, so its effect is
`unknown` — and only then. The service's own words stay out of `detail` beyond the code: they
can echo a request, and a request can carry a credential.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx

type Json = dict[str, Any]

DEFAULT_TIMEOUT = 30.0

# The service's error codes, by the contract's cause. A code not listed is `invalid`: the service
# refused, for a reason this connector does not know.
UNAUTHENTICATED = frozenset(
    {"not_authed", "invalid_auth", "account_inactive", "token_revoked", "token_expired"}
)
FORBIDDEN = frozenset(
    {
        "missing_scope",
        "not_in_channel",
        "restricted_action",
        "no_permission",
        "access_denied",
        "ekm_access_denied",
        "team_access_not_granted",
        "not_allowed_token_type",
    }
)
NOT_FOUND = frozenset({"channel_not_found", "thread_not_found", "message_not_found"})
CONFLICT = frozenset({"is_archived", "channel_is_archived"})
UNAVAILABLE = frozenset({"ratelimited", "internal_error", "service_unavailable"})
UNKNOWN = frozenset({"fatal"})
"""The service says some of the operation may have happened before it failed."""


@dataclass(frozen=True)
class TargetError(Exception):
    """The service refused, failed or vanished. `cause`, `effect` and `retryable` are the
    contract's (`Connector.json#/$defs/Error`)."""

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
    """The service's web interface, with one token, counting requests."""

    def __init__(self, target: str, token: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.target = target.rstrip("/")
        self.requests = 0
        self._client = httpx.AsyncClient(
            base_url=self.target,
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            headers={"Authorization": f"Bearer {token}"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def read(self, method: str, params: Json) -> Json:
        """A method that changes nothing, its arguments as a query."""
        return await self._call("GET", method, params=params)

    async def write(self, method: str, body: Json) -> Json:
        """A method that acts, its arguments as a JSON body."""
        return await self._call("POST", method, body=body)

    async def _call(
        self, verb: str, method: str, *, params: Json | None = None, body: Json | None = None
    ) -> Json:
        self.requests += 1
        try:
            response = await self._client.request(
                verb,
                f"/{method}",
                params=params,
                content=None if body is None else json.dumps(body).encode(),
                headers=None
                if body is None
                else {"Content-Type": "application/json; charset=utf-8"},
            )
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
        return parse(response)


def parse(response: httpx.Response) -> Json:
    status = response.status_code
    if status == 429:
        raise (TargetError("unavailable", "none", True, "the rate limit is exhausted"))
    if status >= 500:
        raise (TargetError("unavailable", "none", True, f"the service answered {status}"))
    if status in (401, 403):
        raise (classify("invalid_auth" if status == 401 else "access_denied"))
    if status == 404:
        raise (TargetError("not_found", "none", False, "the method does not exist"))
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise (
            TargetError("unavailable", "none", True, f"the service answered {status} without JSON")
        )
    if body.get("ok") is True:
        return body
    raise (classify(str(body.get("error") or "unknown_error")))


def classify(code: str) -> TargetError:
    """The service's error code as the contract's cause."""
    detail = f"the service answered {code!r}"
    if code in UNAUTHENTICATED:
        return TargetError("unauthenticated", "none", False, detail)
    if code in FORBIDDEN:
        return TargetError("forbidden", "none", False, f"{detail}: the identity may not do this")
    if code in NOT_FOUND:
        return TargetError(
            "not_found", "none", False, f"{detail}: it does not exist or is not visible"
        )
    if code in CONFLICT:
        return TargetError("conflict", "none", False, f"{detail}: the conversation is archived")
    if code in UNAVAILABLE:
        return TargetError("unavailable", "none", True, detail)
    if code in UNKNOWN:
        return TargetError(
            "unknown", "unknown", False, f"{detail}: part of the operation may have happened"
        )
    return TargetError("invalid", "none", False, f"{detail}: the input was refused")


def digest_of(body: Json) -> str:
    """The digest of what is written: the request body in canonical form."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
