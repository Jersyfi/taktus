#!/usr/bin/env python3
"""A fake App Store Connect API: the certificate list and the profile list, in memory.

The app stores connector under `connectors/taktus_connectors/appstores/` asks, for its
`expiry.credentials`,
`GET /v1/certificates` and `GET /v1/profiles`. This fake answers both in the API's shapes and
statuses, over certificates and profiles it holds in memory. It exists so that the connector
can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **The token.** Every request needs `Authorization: Bearer <JWT>`. The header must name
  `alg: ES256`, `typ: JWT` and a `kid`; the payload `aud: appstoreconnect-v1`, an `iss`, an
  `iat` not in the future and an `exp` after now and at most 20 minutes after `iat`. The `kid`
  and `iss` must be those of a value the fake was started with (`FAKE_TOKENS`, one value: the
  connector's credential `STORES_KEY`, whose `ios` member is `{issuer_id, key_id,
  private_key}`), and the ES256 signature must verify under that key's public half.
  Otherwise 401 with the API's error shape.
- **Parameters.** `limit` from 1 to 200; `fields[certificates]` and `fields[profiles]` only
  of the attributes the API documents; `cursor` as a next link names it. Anything else 400.
- **Pages.** `limit` entries per page, with `links.next` while entries remain.

The signature is verified with the `cryptography` package, not the standard library, which
has no elliptic-curve signatures. The fake is test code run by the environment that holds
the connectors' dependencies, `cryptography` among them; checking the claims alone would
admit a token signed with any key, which is the check the connector most needs.

A request without a sparse fieldset is answered with every attribute, the certificate's or
profile's content among them, as the API answers. `GET /_fake/state` counts the requests, the
entries answered with content (`content_served`, which must stay 0) and the key ids seen.

The entries, each expiring a number of days and twelve hours from the fake's start:
certificates `CERT0001` (`IOS_DISTRIBUTION`, 120), `CERT0002` (`DEVELOPMENT`, -10: expired;
its name names a person, which the connector must never copy) and `CERT0003`
(`MAC_APP_DISTRIBUTION`, 400); profiles `PROF0001` (`IOS_APP_STORE`, `ACTIVE`, 40),
`PROF0002` (`IOS_APP_DEVELOPMENT`, `INVALID`, -3), and `FAKE_PROFILES` more (default 0),
each `ACTIVE` and 200 days or more.
Runnable as `python3 tests/fakes/app_store_service.py --port 9225`.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import secrets
import string
import sys
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

AUDIENCE = "appstoreconnect-v1"
CERTIFICATE_FIELDS = {
    "name",
    "certificateType",
    "displayName",
    "serialNumber",
    "platform",
    "expirationDate",
    "certificateContent",
    "activated",
    "passTypeId",
}
PROFILE_FIELDS = {
    "name",
    "platform",
    "profileType",
    "profileState",
    "profileContent",
    "uuid",
    "createdDate",
    "expirationDate",
    "bundleId",
    "devices",
    "certificates",
}
CONTENT = {"certificateContent", "profileContent"}


def test_value() -> str:
    """A credential value the connector and this fake both accept: `STORES_KEY` with a fresh
    P-256 key as its `ios` member."""
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    key_id = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10))
    member = {"issuer_id": str(uuid.uuid4()), "key_id": key_id, "private_key": pem.decode()}
    return json.dumps({"ios": member})


def keys(values: set[str]) -> dict[tuple[str, str], ec.EllipticCurvePublicKey]:
    """The public key of each value, by its key id and issuer."""
    out: dict[tuple[str, str], ec.EllipticCurvePublicKey] = {}
    for value in values:
        member = json.loads(value)["ios"]
        issuer, key_id = member["issuer_id"], member["key_id"]
        private = serialization.load_pem_private_key(member["private_key"].encode(), None)
        if not isinstance(private, ec.EllipticCurvePrivateKey):
            raise ValueError("a FAKE_TOKENS key is not an elliptic-curve key")
        out[(key_id, issuer)] = private.public_key()
    return out


def _part(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def admitted(bearer: str, known: dict[tuple[str, str], ec.EllipticCurvePublicKey]) -> str | None:
    """The key id of a token the API would admit, or None."""
    try:
        head, body, signature = bearer.split(".")
        header = json.loads(_part(head))
        claims = json.loads(_part(body))
        raw = _part(signature)
    except (ValueError, binascii.Error):
        return None
    if not isinstance(header, dict) or not isinstance(claims, dict) or len(raw) != 64:
        return None
    if header.get("alg") != "ES256" or header.get("typ") != "JWT":
        return None
    public = known.get((str(header.get("kid")), str(claims.get("iss"))))
    issued, expires, now = claims.get("iat"), claims.get("exp"), time.time()
    if (
        public is None
        or claims.get("aud") != AUDIENCE
        or not isinstance(issued, int)
        or not isinstance(expires, int)
        or issued > now + 60
        or expires <= now
        or expires - issued > 1200
    ):
        return None
    der = encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:]))
    try:
        public.verify(der, f"{head}.{body}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return None
    return str(header["kid"])


def _date(start: datetime, days: int) -> str:
    at = start + timedelta(days=days, hours=12)
    return at.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


def certificates(start: datetime) -> list[dict[str, Any]]:
    rows = [
        ("CERT0001", "IOS_DISTRIBUTION", "Example Team", "IOS", 120),
        ("CERT0002", "DEVELOPMENT", "A Person", "IOS", -10),
        ("CERT0003", "MAC_APP_DISTRIBUTION", "Example Team", "MAC_OS", 400),
    ]
    return [
        {
            "type": "certificates",
            "id": id,
            "attributes": {
                "name": f"{kind.replace('_', ' ').title()}: {owner}",
                "certificateType": kind,
                "displayName": owner,
                "serialNumber": f"{n + 1:02d}4F2A9C1B7D3E5F60",
                "platform": platform,
                "expirationDate": _date(start, days),
                "certificateContent": "MIIFakeCertificateContent" + id,
                "activated": True,
            },
            "links": {"self": f"/v1/certificates/{id}"},
        }
        for n, (id, kind, owner, platform, days) in enumerate(rows)
    ]


def profiles(start: datetime, extra: int) -> list[dict[str, Any]]:
    rows = [
        ("PROF0001", "Example App Store", "IOS_APP_STORE", "ACTIVE", 40),
        ("PROF0002", "Example Development", "IOS_APP_DEVELOPMENT", "INVALID", -3),
    ]
    rows += [
        (f"PROF{n + 3:04d}", f"Example {n}", "IOS_APP_ADHOC", "ACTIVE", 200 + n)
        for n in range(extra)
    ]
    return [
        {
            "type": "profiles",
            "id": id,
            "attributes": {
                "name": name,
                "platform": "IOS",
                "profileType": kind,
                "profileState": state,
                "profileContent": "MIIFakeProfileContent" + id,
                "uuid": str(uuid.uuid5(uuid.NAMESPACE_OID, id)),
                "createdDate": _date(start, days - 365),
                "expirationDate": _date(start, days),
            },
            "links": {"self": f"/v1/profiles/{id}"},
        }
        for id, name, kind, state, days in rows
    ]


class State:
    def __init__(self, values: set[str], extra: int) -> None:
        start = datetime.now(UTC)
        self.keys = keys(values)
        self.lists = {
            "/v1/certificates": ("certificates", CERTIFICATE_FIELDS, certificates(start)),
            "/v1/profiles": ("profiles", PROFILE_FIELDS, profiles(start, extra)),
        }
        self.requests = 0
        self.content_served = 0
        self.key_ids: list[str] = []
        self.lock = threading.Lock()


def _error(status: int, code: str, title: str, detail: str) -> dict[str, Any]:
    return {
        "errors": [
            {
                "id": str(uuid.uuid4()),
                "status": str(status),
                "code": code,
                "title": title,
                "detail": detail,
            }
        ]
    }


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def invalid(self, detail: str) -> None:
            self.answer(
                400,
                _error(400, "PARAMETER_ERROR.INVALID", "A parameter has an invalid value", detail),
            )

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    body = {
                        "requests": state.requests,
                        "content_served": state.content_served,
                        "key_ids": list(state.key_ids),
                    }
                self.answer(200, body)
                return
            with state.lock:
                state.requests += 1
            bearer = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            key_id = admitted(bearer, state.keys)
            if key_id is None:
                self.answer(
                    401,
                    _error(
                        401,
                        "NOT_AUTHORIZED",
                        "Authentication credentials are missing or invalid.",
                        "Provide a properly configured and signed bearer token, and make sure "
                        "that it has not expired.",
                    ),
                )
                return
            with state.lock:
                state.key_ids.append(key_id)
            listed = state.lists.get(url.path.rstrip("/"))
            if listed is None:
                self.answer(
                    404,
                    _error(
                        404,
                        "NOT_FOUND",
                        "The specified resource does not exist",
                        "The path provided does not match a defined resource type.",
                    ),
                )
                return
            self._list(url.path.rstrip("/"), *listed, parse_qs(url.query))

        def _list(
            self,
            path: str,
            resource: str,
            allowed: set[str],
            items: list[dict[str, Any]],
            query: dict[str, list[str]],
        ) -> None:
            fieldset = f"fields[{resource}]"
            unknown = set(query) - {fieldset, "limit", "cursor"}
            if unknown:
                self.invalid(f"The parameter '{sorted(unknown)[0]}' can not be used here.")
                return
            try:
                limit = int(query.get("limit", ["20"])[0])
                cursor = int(query.get("cursor", ["0"])[0])
            except ValueError:
                self.invalid("limit and cursor must be numbers")
                return
            if not 1 <= limit <= 200 or cursor < 0:
                self.invalid("limit must be from 1 to 200")
                return
            fields = query[fieldset][0].split(",") if fieldset in query else None
            if fields is not None and not set(fields) <= allowed:
                self.invalid(f"The parameter '{fieldset}' has an invalid value.")
                return
            page = []
            for item in items[cursor : cursor + limit]:
                attributes = {
                    k: v for k, v in item["attributes"].items() if fields is None or k in fields
                }
                if CONTENT & set(attributes):
                    with state.lock:
                        state.content_served += 1
                page.append({**item, "attributes": attributes})
            base = f"http://{self.headers.get('Host')}{path}"
            own = {k: v[0] for k, v in query.items() if k != "cursor"}
            links: dict[str, str] = {"self": f"{base}?{urlencode(query, doseq=True)}"}
            if cursor + limit < len(items):
                links["next"] = f"{base}?{urlencode({**own, 'cursor': cursor + limit})}"
            body = {
                "data": page,
                "links": links,
                "meta": {"paging": {"total": len(items), "limit": limit}},
            }
            self.answer(200, body)

    return Handler


def make_server(host: str, port: int, values: set[str], profiles: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(values, profiles)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9225)
    args = parser.parse_args()
    given = os.environ.get("FAKE_TOKENS", "")
    values = {given} if given else set()
    extra = int(os.environ.get("FAKE_PROFILES", "0"))
    server = make_server(args.host, args.port, values, extra)
    sys.stderr.write(f"fake app store connect at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
