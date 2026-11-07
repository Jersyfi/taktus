"""How the connector reaches the provider's APIs: where each one is, and one signed request.

Every API this connector calls answers one JSON request, `POST /` with the header
`X-Amz-Target` naming the action, signed with Signature Version 4 for the API's service
(`signing.py`). Cost Explorer is served in one region, `us-east-1`. CloudWatch Logs and
Secrets Manager are regional: `--services-region` names the region they are read in.

When the connector is pointed at one address with `--target`, and the regional addresses are
not given, every API is reached at that address: a fake serves all of them on one port.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| a refusal of the request, an error type in `INVALID` | `invalid` |
| the key is not admitted, an error type in `UNAUTHENTICATED`, or 401 | `unauthenticated` |
| `AccessDeniedException`, or 403 without one of the above | `forbidden` |
| an error type in `UNAVAILABLE`, 429, 5xx, no answer in time | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its error type is reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from taktus_connectors.aws.signing import Key, signed_headers
from taktus_connectors.serving import Call, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://ce.us-east-1.amazonaws.com"
REGION = "us-east-1"
INVALID = {
    "ValidationException",
    "ValidationError",
    "DataUnavailableException",
    "InvalidNextTokenException",
    "BillExpirationException",
    "RequestChangedException",
    "InvalidParameterException",
    "InvalidRequestException",
    "ResourceNotFoundException",
}
UNAUTHENTICATED = {
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "IncompleteSignature",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "MissingAuthenticationToken",
}
UNAVAILABLE = {
    "LimitExceededException",
    "ThrottlingException",
    "ServiceUnavailable",
    "ServiceUnavailableException",
    "InternalFailure",
    "InternalServiceError",
}


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """Cost Explorer's address; the provider's own, or a fake's that serves every API."""
    region: str = REGION
    """The region Cost Explorer requests are signed for."""
    timeout: float = 30.0
    services_region: str = REGION
    """The region CloudWatch Logs and Secrets Manager are read in, and signed for."""
    logs_target: str | None = None
    """CloudWatch Logs' address; by default the regional one, or `target` where it was moved."""
    secrets_target: str | None = None
    """Secrets Manager's address; by default the regional one, or `target` where it was moved."""
    log_group: str | None = None
    """The log group a log query reads when the call names no `source`."""

    def _regional(self, given: str | None, service: str) -> str:
        if given:
            return given
        if self.target != TARGET:
            return self.target
        return f"https://{service}.{self.services_region}.amazonaws.com"

    def logs(self) -> str:
        return self._regional(self.logs_target, "logs")

    def secrets(self) -> str:
        return self._regional(self.secrets_target, "secretsmanager")


def key_of(call: Call) -> Key:
    key = Key.parse(call.token)
    if key is None:
        raise TargetError(
            "unauthenticated",
            "none",
            False,
            "the credential is not `<access key id>:<secret access key>[:<session token>]`",
        )
    return key


def _error_type(response: httpx.Response) -> str:
    kind = response.headers.get("x-amzn-errortype", "")
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        kind = str(body.get("__type") or body.get("code") or kind)
    return str(kind).split("#")[-1].split(":")[0].strip()


async def post(
    config: Config,
    call: Call,
    key: Key,
    *,
    address: str,
    region: str,
    service: str,
    action: str,
    body: Json,
    what: str,
) -> Json:
    """One signed request of `action`, counted; its answer as a JSON object. `what` names what
    a refused identity may not read, for the `forbidden` detail."""
    url = httpx.URL(address.rstrip("/") + "/")
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = signed_headers(
        key,
        host=url.netloc.decode("ascii"),
        path=url.path,
        headers={"content-type": "application/x-amz-json-1.1", "x-amz-target": action},
        body=data,
        region=region,
        service=service,
        at=datetime.now(UTC),
    )
    call.count()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout))
        ) as client:
            response = await client.post(url, content=data, headers=headers)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            raise TargetError("unexpected", "none", False, "the answer is not a JSON object")
        return answer
    kind = _error_type(response)
    if kind in UNAUTHENTICATED or status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the key")
    if kind == "AccessDeniedException" or status == 403:
        raise TargetError("forbidden", "none", False, f"the key may not read {what}")
    if kind in UNAVAILABLE or status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status} {kind}".rstrip())
    if kind in INVALID and status == 400:
        raise invalid(f"the provider refused the request: {kind}")
    raise TargetError("unexpected", "none", False, f"the provider answered {status} {kind}")


def rfc3339(moment: datetime) -> str:
    """A moment as RFC 3339 in UTC with `Z`, with the fraction of a second only where it has
    one, to the millisecond."""
    moment = moment.astimezone(UTC)
    text = moment.strftime("%Y-%m-%dT%H:%M:%S")
    millis = moment.microsecond // 1000
    return f"{text}.{millis:03d}Z" if millis else f"{text}Z"


def from_epoch(value: Any, per_second: int) -> datetime | None:
    """A number of seconds (`per_second` 1) or milliseconds (1000) since the epoch as a moment,
    computed in decimal arithmetic; None where the value is absent or not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value)) / per_second
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    whole = int(amount)
    micros = int((amount - whole) * 1_000_000)
    try:
        return datetime.fromtimestamp(whole, UTC).replace(microsecond=max(0, micros))
    except (OverflowError, OSError, ValueError):
        return None
