"""A Google service account key turned into an access token, per call.

The credential's value is a service account key as Google issues it: JSON with `type`,
`project_id`, `private_key_id`, `private_key` (PEM), `client_email` and `token_uri`. Each call
signs a statement — a JSON Web Token, RS256, "I am this service account, for this scope, until
one hour from now" — with the key and exchanges it at the configured token endpoint for an
access token, Google's documented flow for server-to-server applications
(https://developers.google.com/identity/protocols/oauth2/service-account#httprest). Nothing is
kept between calls: the key is read at the moment of the call and dropped after signing, and the
exchange counts as one request of the call.

The key's own `token_uri` is never followed: a key is data, and a key that named another address
would otherwise receive a signed statement (the rule of the cloud connector, `gcp`). The endpoint
is Google's while the API is Google's own, `<target>/token` where the target is another address
(a fake serves both at one address), or the one `--token-endpoint` names.
A key that is not such JSON, and a token endpoint that refuses the statement, end the call
`unauthenticated`; neither detail quotes the key or the statement.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import jwt

from taktus_connectors.serving import Call, TargetError, unavailable

GOOGLE_ENDPOINT = "https://oauth2.googleapis.com/token"
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
LIFETIME = 3600


def _refused(detail: str) -> TargetError:
    return TargetError("unauthenticated", "none", False, detail)


def _key(value: str) -> dict[str, Any]:
    try:
        key = json.loads(value)
    except ValueError:
        key = None
    if (
        not isinstance(key, dict)
        or not isinstance(key.get("private_key"), str)
        or not isinstance(key.get("client_email"), str)
    ):
        raise _refused("the credential is not a service account key")
    return key


def token_endpoint(target: str, google: str, configured: str = "") -> str:
    """Where a key is exchanged: the endpoint configured; else Google's while the API at `target`
    is Google's own (`google`); else `<target>/token`, where a stand-in serves both."""
    if configured:
        return configured.rstrip("/")
    base = target.rstrip("/")
    return GOOGLE_ENDPOINT if base == google.rstrip("/") else f"{base}/token"


async def access_token(call: Call, scope: str, seconds: float, uri: str) -> str:
    """The access token of the call's service account key for `scope`, exchanged at `uri`."""
    key = _key(call.token)
    now = int(time.time())
    claims = {
        "iss": key["client_email"],
        "scope": scope,
        "aud": uri,
        "iat": now,
        "exp": now + LIFETIME,
    }
    headers = {"kid": str(key["private_key_id"])} if key.get("private_key_id") else None
    try:
        assertion = jwt.encode(claims, key["private_key"], algorithm="RS256", headers=headers)
    except (ValueError, TypeError, jwt.PyJWTError) as error:
        raise _refused("the service account key cannot sign: its private key is unreadable") from (
            error
        )
    call.count()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(seconds)) as client:
            response = await client.post(uri, data={"grant_type": GRANT, "assertion": assertion})
    except httpx.HTTPError as error:
        raise unavailable(f"the token endpoint could not be reached: {type(error).__name__}") from (
            error
        )
    if response.status_code in (400, 401, 403):
        raise _refused("the token endpoint refused the service account's statement")
    if response.status_code != 200:
        raise unavailable(f"the token endpoint answered {response.status_code}")
    try:
        token = response.json().get("access_token")
    except ValueError:
        token = None
    if not isinstance(token, str) or not token:
        raise unavailable("the token endpoint answered without an access token")
    return token
