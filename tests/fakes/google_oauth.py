"""The token endpoint of Google's OAuth 2.0 server-to-server flow, as the fakes of Google APIs
serve it at `POST /token`.

A service account signs a statement (a JSON Web Token, RS256) with its key and exchanges it for
an access token (https://developers.google.com/identity/protocols/oauth2/service-account). The
fake is given the service account keys it admits, each the key JSON as Google issues it. It
finds the key by the statement's `iss`, the key's `client_email`, verifies the signature with the
public half of that key's private key, and requires an `aud` ending in `/token` and a `scope`. It
answers `{"access_token", "expires_in", "token_type"}`, or 400 `invalid_grant`. An API request is
admitted only with a token it issued.

Imported by a fake both as `fakes.google_oauth` (in a test) and as `google_oauth` (a fake run as
a script from its own directory).
"""

from __future__ import annotations

import json
import secrets
import threading
from typing import Any
from urllib.parse import parse_qs

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key

GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"


def service_account_key(
    token_uri: str, email: str = "release@example.iam.gserviceaccount.com"
) -> str:
    """A fresh service account key in the shape Google issues it, for a test: a new RSA key,
    its token endpoint the fake's."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "example",
            "private_key_id": secrets.token_hex(8),
            "private_key": pem,
            "client_email": email,
            "client_id": "1",
            "token_uri": token_uri,
        }
    )


def keys_from(value: str) -> set[str]:
    """`FAKE_TOKENS` as a fake's `main` reads it: one key JSON whole, or comma-split tokens."""
    if value.lstrip().startswith("{"):
        return {value}
    return {t for t in value.split(",") if t}


class Tokens:
    """The keys admitted, and the access tokens issued for them."""

    def __init__(self, keys: set[str]) -> None:
        self._public: dict[str, Any] = {}
        for text in keys:
            try:
                key = json.loads(text)
                private = load_pem_private_key(key["private_key"].encode("utf-8"), password=None)
            except (ValueError, KeyError, TypeError):
                continue
            self._public[str(key["client_email"])] = private.public_key()
        self._issued: dict[str, tuple[str, str]] = {}
        self._lock = threading.Lock()
        self.grants = 0

    def grant(self, body: bytes) -> tuple[int, dict[str, Any]]:
        form = parse_qs(body.decode("utf-8", "replace"))
        assertion = (form.get("assertion") or [""])[0]
        if (form.get("grant_type") or [""])[0] != GRANT or not assertion:
            return 400, {"error": "unsupported_grant_type"}
        try:
            unverified = jwt.decode(assertion, options={"verify_signature": False})
            public = self._public.get(str(unverified.get("iss")))
            if public is None:
                return 400, {"error": "invalid_grant", "error_description": "unknown issuer"}
            claims = jwt.decode(
                assertion, public, algorithms=["RS256"], options={"verify_aud": False}
            )
        except jwt.PyJWTError:
            return 400, {"error": "invalid_grant", "error_description": "invalid signature"}
        if not str(claims.get("aud", "")).endswith("/token") or not claims.get("scope"):
            return 400, {"error": "invalid_grant", "error_description": "invalid claims"}
        token = "ya29.fake-" + secrets.token_hex(16)
        with self._lock:
            self._issued[token] = (str(claims["iss"]), str(claims["scope"]))
            self.grants += 1
        return 200, {"access_token": token, "expires_in": 3599, "token_type": "Bearer"}

    def admits(self, authorization: str | None) -> bool:
        return self.holder(authorization) is not None

    def holder(self, authorization: str | None) -> tuple[str, str] | None:
        """The service account a token was issued to and the scope it was issued for; None for
        a token the fake did not issue."""
        if not authorization or not authorization.startswith("Bearer "):
            return None
        with self._lock:
            return self._issued.get(authorization[len("Bearer ") :])
