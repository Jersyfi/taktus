"""How the app stores connector signs in: one credential, two keys, a token per call.

The credential `STORES_KEY` is a JSON object with up to two members. `ios` is an App Store
Connect API key: `{"issuer_id", "key_id", "private_key"}`, the private key a P-256 key in PEM as
App Store Connect issues it. `android` is a Google service account key as Google issues it
(`client_email`, `private_key_id`, `private_key`, `token_uri`). A call for a platform whose
member is absent is `unauthenticated`.

**App Store Connect** ("Generating Tokens for API Requests"): an ES256 JWT, header `kid` the
key's identifier, claims `iss` the issuer, `iat`, `exp` twenty minutes later at most, `aud`
`appstoreconnect-v1`, sent as `Authorization: Bearer`. Signing needs no request.

**Google Play** ("Using OAuth 2.0 for Server to Server Applications"): an RS256 JWT, header
`kid` the key's identifier, claims `iss` the service account, `scope` the Play Developer API's,
`aud` the key's `token_uri`, `iat`, `exp` an hour later, exchanged at `token_uri` for an access
token. The exchange counts as one request. Nothing is cached between calls.

Neither key nor token is ever logged or put into an error's text.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt

from taktus_connectors.serving import Call, TargetError, unavailable

type Json = dict[str, Any]

PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 — an address, not a secret
APP_STORE_AUDIENCE = "appstoreconnect-v1"
APP_STORE_LIFETIME = 1200
"""Twenty minutes: the longest App Store Connect admits."""


def _refused(detail: str) -> TargetError:
    return TargetError("unauthenticated", "none", False, detail)


def _member(call: Call, platform: str) -> Json:
    try:
        document = json.loads(call.token)
    except ValueError:
        raise _refused("the credential is not the JSON object the connector reads") from None
    member = document.get(platform) if isinstance(document, dict) else None
    if not isinstance(member, dict):
        raise _refused(f"the credential holds no key for the platform {platform!r}")
    return member


def app_store_token(call: Call) -> str:
    """A token for App Store Connect, signed now."""
    key = _member(call, "ios")
    issuer, key_id, private = key.get("issuer_id"), key.get("key_id"), key.get("private_key")
    if not all(isinstance(v, str) and v for v in (issuer, key_id, private)):
        raise _refused("the App Store Connect key lacks its issuer, identifier or private key")
    now = int(time.time())
    claims = {"iss": issuer, "iat": now, "exp": now + APP_STORE_LIFETIME, "aud": APP_STORE_AUDIENCE}
    try:
        return jwt.encode(
            claims, str(private), algorithm="ES256", headers={"kid": key_id, "typ": "JWT"}
        )
    except (ValueError, TypeError, jwt.PyJWTError):
        raise _refused("the App Store Connect private key cannot sign") from None


def _token_uri(key: Json) -> str:
    uri = key.get("token_uri") or GOOGLE_TOKEN_URI
    parsed = urlparse(str(uri))
    local = parsed.hostname in ("127.0.0.1", "localhost")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise _refused("the service account key names a token address that is not https")
    return str(uri)


async def play_token(call: Call, seconds: float) -> str:
    """An access token for the Play Developer API, exchanged now."""
    key = _member(call, "android")
    email, key_id, private = (
        key.get("client_email"),
        key.get("private_key_id"),
        key.get("private_key"),
    )
    if not all(isinstance(v, str) and v for v in (email, private)):
        raise _refused("the service account key lacks its account or private key")
    uri = _token_uri(key)
    now = int(time.time())
    claims = {"iss": email, "scope": PLAY_SCOPE, "aud": uri, "iat": now, "exp": now + 3600}
    headers = {"kid": key_id} if isinstance(key_id, str) and key_id else None
    try:
        assertion = jwt.encode(claims, str(private), algorithm="RS256", headers=headers)
    except (ValueError, TypeError, jwt.PyJWTError):
        raise _refused("the service account's private key cannot sign") from None
    call.count()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(seconds)) as client:
            answer = await client.post(
                uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
    except httpx.HTTPError as error:
        raise unavailable(f"the token endpoint could not be reached: {type(error).__name__}") from (
            error
        )
    if answer.status_code in (400, 401, 403):
        raise _refused("the token endpoint does not admit the service account key")
    if answer.status_code == 429 or answer.status_code >= 500:
        raise unavailable(f"the token endpoint answered {answer.status_code}")
    try:
        token = answer.json().get("access_token")
    except ValueError:
        token = None
    if answer.status_code != 200 or not isinstance(token, str) or not token:
        raise TargetError(
            "unexpected", "none", False, "the token endpoint answered without an access token"
        )
    return token
