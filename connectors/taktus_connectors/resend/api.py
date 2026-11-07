"""How the Resend API is asked, and its answers read.

Every request goes to `--target`, authenticated as the API documents it: `Authorization:
Bearer` and the requesting identity's API key. The key is never one of the connector's own.

How the API's answers map to the contract's causes. Its error body is `statusCode`, `message`
and `name`; only `name` is passed on, because a message can quote what was sent.

| Answer | Cause |
|---|---|
| 400 `validation_error` naming the API key | `unauthenticated` |
| 400, 422: a request the API refuses | `invalid` |
| 401 `restricted_api_key`: the key may only send | `forbidden` |
| 401: no key, or a key the API does not admit | `unauthenticated` |
| 403: the key may not do this, the sender's domain is not verified | `forbidden` |
| 404: no such message, broadcast or segment | `not_found` |
| 409 `invalid_idempotent_request`: the key reused with another body | `conflict` |
| 409 `concurrent_idempotent_requests`, `resource_locked` | `unavailable`, retryable |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.resend.com"


@dataclass(frozen=True)
class Config:
    target: str
    """The API's address: `https://api.resend.com`, or a fake's."""
    sender: str
    """The address messages and broadcasts are sent from, on a domain the account verified."""
    timeout: float = 30.0

    @property
    def domain(self) -> str:
        return self.sender.rsplit("@", 1)[-1].lower()


def unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _error(response: httpx.Response) -> tuple[str, str]:
    """The error's `name` and `message`, or empty strings for a body that is not the API's."""
    try:
        body = response.json()
    except ValueError:
        return "", ""
    if not isinstance(body, dict):
        return "", ""
    name = body.get("name")
    message = body.get("message")
    return (
        str(name)[:60] if isinstance(name, str) else "",
        str(message) if isinstance(message, str) else "",
    )


async def request(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    body: Json | None = None,
    params: Json | None = None,
    key: str | None = None,
) -> Any:
    """One request; the answer's JSON body. `key` is sent as the API's `Idempotency-Key`."""
    writing = method != "GET"
    call.count()
    headers = {"Authorization": f"Bearer {call.token}", "Accept": "application/json"}
    if key is not None:
        headers["Idempotency-Key"] = key
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(method, path, headers=headers, params=params, json=body)
    except httpx.ConnectError as error:
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the API did not answer the write in time"
            ) from error
        raise unavailable(f"the API did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the key among it.
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            return response.json()
        except ValueError as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the API answered the write unreadably"
                ) from error
            raise unexpected("the API answered with a body that is not JSON") from error
    name, message = _error(response)
    if status == 400 and name == "validation_error" and "api key" in message.lower():
        raise TargetError("unauthenticated", "none", False, "the API does not admit the key")
    if status in (400, 422):
        raise invalid(f"the API refused the request: {name or status}")
    if status == 401 and name == "restricted_api_key":
        raise TargetError("forbidden", "none", False, "the key may only send messages")
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the API does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, f"the key may not do this: {name or 403}")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such message, broadcast or segment")
    if status == 409 and name == "invalid_idempotent_request":
        raise TargetError(
            "conflict", "none", False, "the idempotency key was used with another message"
        )
    if status in (409, 429) or status >= 500:
        raise unavailable(f"the API answered {status} {name}".rstrip())
    raise unexpected(f"the API answered {status}, which the connector does not foresee")
