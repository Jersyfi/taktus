"""How the connector reaches the provider's APIs: the addresses, the access token, one request.

**The credential.** Its value is one of two things. An OAuth 2.0 access token is sent as it is,
as a bearer token. A service account key — the JSON document the provider issues, with
`"type": "service_account"` — is exchanged for an access token first: the connector signs a JSON
Web Token (RS256) that names the account (`iss`), the scope it asks for, the token endpoint
(`aud`), and an issue and expiry time one hour apart, and posts it to the token endpoint with
the grant type `urn:ietf:params:oauth:grant-type:jwt-bearer`. The token endpoint is the
connector's configured one, **never the `token_uri` the key names**: a key is data, and a key
that named another address would otherwise receive a signed statement. The access token is
held for the one call and dropped; the exchange is one request of that call.

**The scope.** Each operation asks for the narrowest scope its API admits: `logs.query`,
`billing.costs` and `models.costs` ask for `cloud-platform.read-only`, which the logging and the
query API both accept; `metrics.series` asks for `monitoring.read`; `secrets.metadata` and
`models.catalogue` ask for `cloud-platform`, the only scope the secret API and the model API
name besides their own.

**One request.** Every answer maps to the contract's causes the same way:

| Answer | Cause |
|---|---|
| 400: the filter, the query or a parameter is refused | `invalid` |
| 404: the project, the table or the secret is unknown | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The provider's own `message` stays out of the error's `detail`: it can quote the filter or the
query. Only its `status` word (`INVALID_ARGUMENT`) is reported.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt

from taktus_connectors.serving import Call, TargetError, invalid, unavailable

type Json = dict[str, Any]

LOGGING = "https://logging.googleapis.com"
BIGQUERY = "https://bigquery.googleapis.com"
SECRETS = "https://secretmanager.googleapis.com"
MONITORING = "https://monitoring.googleapis.com"
AIPLATFORM = "https://aiplatform.googleapis.com"
MODEL_SERVICE = "Vertex AI"
"""The model service's description in the billing export, unless configured otherwise."""
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 - an address, not a secret
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
READ_ONLY = "https://www.googleapis.com/auth/cloud-platform.read-only"
FULL = "https://www.googleapis.com/auth/cloud-platform"
LIFETIME = 3600
"""Seconds the signed statement is valid: the most the token endpoint accepts."""
PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$|^[a-z0-9.-]+:[a-z][a-z0-9-]{4,28}[a-z0-9]$")
"""A project identifier: six to thirty lowercase letters, digits and hyphens, optionally under a
domain (`example.com:project`)."""


@dataclass(frozen=True)
class Config:
    project: str = ""
    """The project whose logs and secrets are read, and in which the cost query runs."""
    billing_table: str = ""
    """The billing export table, `project.dataset.table`; without it costs are `invalid`."""
    timeout: float = 30.0
    logging: str = LOGGING
    bigquery: str = BIGQUERY
    secrets: str = SECRETS
    token_endpoint: str = TOKEN_ENDPOINT
    monitoring: str = MONITORING
    aiplatform: str = AIPLATFORM
    model_service: str = MODEL_SERVICE
    """The model service's charges in the billing export are those of this description."""
    metrics: dict[str, str] = field(default_factory=dict)
    """The named metrics the monitoring service answers, each with its PromQL (ADR-0328)."""

    @classmethod
    def at(
        cls,
        project: str,
        billing_table: str = "",
        timeout: float = 30.0,
        target: str | None = None,
        *,
        metrics: dict[str, str] | None = None,
        model_service: str = MODEL_SERVICE,
        **overrides: str | None,
    ) -> Config:
        """A configuration whose every service is at `target` when one is given (the token
        endpoint at `<target>/token`), each overridden by its own address where one is named."""
        base = target.rstrip("/") if target else None
        addresses = {
            "logging": base or LOGGING,
            "bigquery": base or BIGQUERY,
            "secrets": base or SECRETS,
            "monitoring": base or MONITORING,
            "aiplatform": base or AIPLATFORM,
            "token_endpoint": f"{base}/token" if base else TOKEN_ENDPOINT,
        }
        for name, value in overrides.items():
            if value:
                addresses[name] = value.rstrip("/")
        return cls(
            project,
            billing_table,
            timeout,
            **addresses,
            model_service=model_service,
            metrics=dict(metrics or {}),
        )


def project(config: Config) -> str:
    if PROJECT.match(config.project) is None:
        raise invalid("the connector names no project, or not one project identifier")
    return config.project


def _refused(detail: str) -> TargetError:
    return TargetError("unauthenticated", "none", False, detail)


def _account(value: str) -> Json | None:
    """The service account key the value is, or None for an access token."""
    if not value.lstrip().startswith("{"):
        return None
    try:
        key = json.loads(value)
    except ValueError:
        raise _refused("the credential is neither an access token nor a key document") from None
    if not isinstance(key, dict) or key.get("type") != "service_account":
        raise _refused("the credential's key document is not a service account key")
    if not isinstance(key.get("client_email"), str) or not isinstance(key.get("private_key"), str):
        raise _refused("the service account key names no account or no private key")
    return key


def _client(config: Config) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout))
    )


async def _exchange(config: Config, call: Call, key: Json, scope: str) -> str:
    now = int(time.time())  # the token endpoint checks the statement against its own clock
    claims = {
        "iss": key["client_email"],
        "scope": scope,
        "aud": config.token_endpoint,
        "iat": now,
        "exp": now + LIFETIME,
    }
    headers = {"kid": key["private_key_id"]} if isinstance(key.get("private_key_id"), str) else {}
    try:
        statement = jwt.encode(claims, key["private_key"], algorithm="RS256", headers=headers)
    except (ValueError, TypeError, jwt.PyJWTError):
        raise _refused("the service account key holds no usable RSA private key") from None
    call.count()
    try:
        async with _client(config) as client:
            response = await client.post(
                config.token_endpoint, data={"grant_type": GRANT, "assertion": statement}
            )
    except httpx.TimeoutException as error:
        raise unavailable(
            f"the token endpoint did not answer in time: {type(error).__name__}"
        ) from None
    except httpx.HTTPError as error:
        raise unavailable(
            f"the token endpoint could not be reached: {type(error).__name__}"
        ) from None
    status = response.status_code
    if status in (400, 401, 403):
        raise _refused(f"the token endpoint refused the service account key ({status})")
    if status == 429 or status >= 500:
        raise unavailable(f"the token endpoint answered {status}")
    try:
        body = response.json()
    except ValueError:
        body = None
    token = body.get("access_token") if isinstance(body, dict) else None
    if status != 200 or not isinstance(token, str) or not token:
        raise TargetError("unexpected", "none", False, "the token endpoint gave no access token")
    return token


async def bearer(config: Config, call: Call, scope: str) -> str:
    """The access token a call's requests carry: the credential, or what its key exchanges for."""
    key = _account(call.token)
    if key is None:
        return call.token
    return await _exchange(config, call, key, scope)


def _status_word(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    status = error.get("status") if isinstance(error, dict) else None
    return status if isinstance(status, str) and re.fullmatch(r"[A-Z_]{1,40}", status) else ""


async def request(
    config: Config,
    call: Call,
    token: str,
    method: str,
    url: str,
    *,
    params: Json | None = None,
    body: Json | None = None,
) -> Json:
    """One request to an API, its JSON answer, or the contract's error."""
    call.count()
    try:
        async with _client(config) as client:
            response = await client.request(
                method,
                url,
                params=params,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    word = _status_word(response)
    if status == 200:
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            raise TargetError("unexpected", "none", False, "the answer is not the API's")
        return answer
    if status == 401:
        raise _refused("the provider does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not read this")
    if status == 404:
        raise invalid("the provider knows no such project, table or secret")
    if status == 400:
        raise invalid(f"the provider refused the request {word}".rstrip())
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status} {word}".rstrip())
    raise TargetError("unexpected", "none", False, f"the provider answered {status}")


FRACTION = re.compile(r"\.(\d+)")


def instant(text: Any) -> datetime | None:
    """An RFC 3339 timestamp as a moment in UTC; fractions beyond microseconds are cut, because
    the provider writes up to nine digits."""
    if not isinstance(text, str) or not text:
        return None
    cut = FRACTION.sub(lambda m: "." + m.group(1)[:6], text.strip(), count=1)
    try:
        moment = datetime.fromisoformat(cut.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(UTC)


def stamp(moment: datetime) -> str:
    """A moment as RFC 3339 UTC with `Z`, to the second, or to the microsecond where it has one."""
    spec = "microseconds" if moment.microsecond else "seconds"
    return moment.astimezone(UTC).isoformat(timespec=spec).replace("+00:00", "Z")


def utc_text(text: Any) -> str | None:
    """A timestamp the provider gave, as RFC 3339 UTC with `Z`; None where it gave none."""
    moment = instant(text)
    return stamp(moment) if moment is not None else None
