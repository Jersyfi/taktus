"""How a request is authorised: a token signed with the team's API key.

The API admits a JSON Web Token signed with ES256 by the private key of a team API key. Its
header names `alg: ES256`, the key's identifier as `kid` and `typ: JWT`. Its payload names the
issuer as `iss`, `iat` and `exp` in Unix seconds, and `aud: appstoreconnect-v1`. The API
refuses a token whose lifetime, `exp` minus `iat`, exceeds 20 minutes for these requests; the
connector signs one of `LIFETIME` seconds per call.

The credential's value is one line, `<issuer id>:<key id>:<key>`, where `<key>` is the
base64 of the `.p8` file the API's key page offers once, PEM and all. One value is one file
the operator writes and rotates as a whole; the three parts cannot drift apart. Neither the
issuer nor the key id holds a colon, and base64 holds none. A value that does not parse, or a
key that does not load, is `unauthenticated`: the API would refuse anything signed with it.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
from dataclasses import dataclass

import jwt

from taktus_connectors.serving import TargetError

AUDIENCE = "appstoreconnect-v1"
LIFETIME = 900
"""Seconds a token lives; the API admits at most 1200."""
PART = re.compile(r"^[A-Za-z0-9-]{1,100}$")


@dataclass(frozen=True)
class ApiKey:
    issuer: str
    key_id: str
    pem: str


def _refused(detail: str) -> TargetError:
    return TargetError("unauthenticated", "none", False, detail)


def parse(value: str) -> ApiKey:
    """The three parts of the credential's value, or `unauthenticated`."""
    parts = value.strip().split(":")
    if len(parts) != 3 or not PART.match(parts[0]) or not PART.match(parts[1]):
        raise _refused("the credential is not `<issuer id>:<key id>:<base64 of the key file>`")
    try:
        pem = base64.b64decode(parts[2], validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise _refused("the credential's key is not the base64 of the key file") from error
    if "PRIVATE KEY" not in pem:
        raise _refused("the credential's key is not the base64 of a PEM private key")
    return ApiKey(parts[0], parts[1], pem)


def sign(key: ApiKey, now: int | None = None) -> str:
    """A token for the API, valid `LIFETIME` seconds from now."""
    issued = int(time.time()) if now is None else now
    claims = {"iss": key.issuer, "iat": issued, "exp": issued + LIFETIME, "aud": AUDIENCE}
    try:
        return jwt.encode(
            claims, key.pem, algorithm="ES256", headers={"kid": key.key_id, "typ": "JWT"}
        )
    except (ValueError, TypeError, jwt.PyJWTError) as error:
        # The type alone: the error's text could quote the key.
        raise _refused(f"the credential's key does not sign: {type(error).__name__}") from error
