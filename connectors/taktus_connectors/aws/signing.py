"""How a request to the provider is signed: Signature Version 4, over HMAC-SHA256.

The requesting identity's credential is one text, `<access key id>:<secret access key>`, or
with a third part, `:<session token>`, for temporary credentials. The secret never leaves this
module: it keys the signature, and only the access key id and the signature go on the wire.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime

ALGORITHM = "AWS4-HMAC-SHA256"


@dataclass(frozen=True)
class Key:
    access_key_id: str
    secret: str = ""
    session_token: str | None = None

    def __repr__(self) -> str:
        return f"Key(access_key_id={self.access_key_id!r})"

    @classmethod
    def parse(cls, value: str) -> Key | None:
        """The key a credential's text holds, or None where it is not one."""
        parts = value.strip().split(":")
        if len(parts) not in (2, 3) or not all(parts):
            return None
        return cls(parts[0], parts[1], parts[2] if len(parts) == 3 else None)


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def signed_headers(
    key: Key,
    *,
    host: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    region: str,
    service: str,
    at: datetime,
) -> dict[str, str]:
    """The headers of a POST without a query, `headers` with the date, the session token where
    there is one, and the authorization added. Every header given is signed."""
    stamp = at.strftime("%Y%m%dT%H%M%SZ")
    day = stamp[:8]
    out = {**headers, "host": host, "x-amz-date": stamp}
    if key.session_token:
        out["x-amz-security-token"] = key.session_token
    names = sorted(name.lower() for name in out)
    lowered = {name.lower(): " ".join(str(value).split()) for name, value in out.items()}
    canonical = "\n".join(
        [
            "POST",
            path or "/",
            "",
            "".join(f"{name}:{lowered[name]}\n" for name in names),
            ";".join(names),
            hashlib.sha256(body).hexdigest(),
        ]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        [ALGORITHM, stamp, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()]
    )
    signing = _hmac(
        _hmac(_hmac(_hmac(f"AWS4{key.secret}".encode(), day), region), service), "aws4_request"
    )
    signature = hmac.new(signing, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    out["authorization"] = (
        f"{ALGORITHM} Credential={key.access_key_id}/{scope}, "
        f"SignedHeaders={';'.join(names)}, Signature={signature}"
    )
    del out["host"]  # the HTTP client sends it from the address
    return out
