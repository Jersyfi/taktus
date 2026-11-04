#!/usr/bin/env python3
"""A fake RDAP server, and TLS endpoints that present a certificate of a chosen validity.

The expiry connector under `connectors/taktus_connectors/expiry/` asks `GET /domain/<name>`
(RFC 9082) and reads the answer as RFC 9083 gives it; it reads a certificate from a TLS
handshake. This fake answers the first over memory, and `tls_endpoint` serves the second. They
exist so that the connector can be exercised in CI without a network, an account or a secret.

What the RDAP server enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the
  fake was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **Names.** A name that is not letters, digits, hyphens and dots is 400; a name the fake does
  not hold is 404 with the RDAP error body.

The domains, each counted from the moment the fake started: `example-product.test` expires in
25 days, `example-later.test` in 400, and `example-dropped.test` carries no expiration event.
Test-only: `GET /_fake/state` counts the requests and names the bearer tokens seen.

`tls_endpoint(days)` starts, in this process, a TLS listener on 127.0.0.1 whose certificate,
for `localhost` and `127.0.0.1`, expires `days` from now (negative: it has expired), signed by
a test authority whose certificate it writes to a file. It needs the `cryptography` package; the
RDAP server is standard library only, runnable as `python3 tests/fakes/expiry_service.py
--port 9215`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

NAME = re.compile(r"^[a-z0-9.-]+$")


def _moment(at: datetime) -> str:
    return at.isoformat(timespec="seconds").replace("+00:00", "Z")


def domains(now: datetime) -> dict[str, dict[str, Any]]:
    """The registrations the fake holds, counted from `now`."""

    def domain(name: str, expires: int | None) -> dict[str, Any]:
        events = [
            {"eventAction": "registration", "eventDate": _moment(now - timedelta(days=700))},
            {"eventAction": "last changed", "eventDate": _moment(now - timedelta(days=30))},
        ]
        if expires is not None:
            events.append(
                {"eventAction": "expiration", "eventDate": _moment(now + timedelta(days=expires))}
            )
        return {
            "objectClassName": "domain",
            "rdapConformance": ["rdap_level_0"],
            "handle": f"{name.split('.')[0].upper()}-TEST",
            "ldhName": name,
            "status": ["active", "client transfer prohibited"],
            "events": events,
        }

    return {
        "example-product.test": domain("example-product.test", 25),
        "example-later.test": domain("example-later.test", 400),
        "example-dropped.test": domain("example-dropped.test", None),
    }


@dataclass
class State:
    tokens: set[str]
    held: dict[str, dict[str, Any]]
    requests: int = 0
    seen_tokens: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/rdap+json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200, {"requests": state.requests, "seen_tokens": list(state.seen_tokens)}
                    )
                return
            auth = self.headers.get("Authorization", "")
            with state.lock:
                state.requests += 1
                state.seen_tokens.append(auth[7:] if auth.startswith("Bearer ") else "")
            if not auth.startswith("Bearer ") or auth[7:] not in state.tokens:
                self.answer(401, {"errorCode": 401, "title": "Unauthorized"})
                return
            if not path.startswith("/domain/"):
                self.answer(404, {"errorCode": 404, "title": "Not Found"})
                return
            name = path.removeprefix("/domain/").lower()
            if NAME.match(name) is None:
                self.answer(400, {"errorCode": 400, "title": "Bad Request"})
            elif name in state.held:
                self.answer(200, state.held[name])
            else:
                self.answer(404, {"errorCode": 404, "title": "Not Found"})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), handler(State(tokens, domains(datetime.now(UTC)))))
    server.daemon_threads = True
    return server


@dataclass
class TlsEndpoint:
    port: int
    ca_file: str
    not_after: datetime
    _socket: socket.socket
    _stopped: threading.Event

    def stop(self) -> None:
        self._stopped.set()
        self._socket.close()


def tls_endpoint(days: int) -> TlsEndpoint:
    """A TLS listener on 127.0.0.1 presenting a certificate that expires `days` from now."""
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(UTC).replace(microsecond=0)
    authority_key = ec.generate_private_key(ec.SECP256R1())
    authority_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fake Test Authority")])
    authority = (
        x509.CertificateBuilder()
        .subject_name(authority_name)
        .issuer_name(authority_name)
        .public_key(authority_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=800))
        .not_valid_after(now + timedelta(days=800))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(authority_key.public_key()), critical=False
        )
        .sign(authority_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    not_after = now + timedelta(days=days)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(authority_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(min(now, not_after) - timedelta(days=90))
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(authority_key, hashes.SHA256())
    )
    folder = Path(tempfile.mkdtemp(prefix="fake-tls-"))
    ca_file = folder / "authority.pem"
    ca_file.write_bytes(authority.public_bytes(serialization.Encoding.PEM))
    chain = folder / "leaf.pem"
    chain.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        + leaf.public_bytes(serialization.Encoding.PEM)
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(chain))
    listener = socket.create_server(("127.0.0.1", 0))
    stopped = threading.Event()

    def serve() -> None:
        while not stopped.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            try:
                with context.wrap_socket(connection, server_side=True) as wrapped:
                    wrapped.settimeout(2)
                    try:
                        wrapped.recv(1)
                    except (OSError, ssl.SSLError):
                        pass
            except (OSError, ssl.SSLError):
                # A client that refused the certificate ends the handshake; the next one comes.
                connection.close()

    threading.Thread(target=serve, daemon=True).start()
    return TlsEndpoint(listener.getsockname()[1], str(ca_file), not_after, listener, stopped)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9215)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake RDAP server at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
