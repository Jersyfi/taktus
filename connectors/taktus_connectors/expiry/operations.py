"""How a certificate and a registration are read.

**A certificate** is what a TLS endpoint presents in its handshake (RFC 8446), an X.509
certificate (RFC 5280). The connector opens a verifying handshake against the system's trust
store, and the authority `--ca-file` names where there is one. When verification fails — an
expired certificate, another name, an unknown authority — it opens a second handshake that does
not verify, only to read the certificate, and answers `trusted: false` with the reason. Nothing
is sent over the connection; it is closed after the handshake. Only the endpoints the
configuration lists are admitted: a call cannot make the connector reach another host.

**A registration** is asked of the configured RDAP server as `GET <rdap>/domain/<name>`
(RFC 9082) and read as RFC 9083 answers it: the events `expiration`, `registration` and
`last changed`, and the status. The requesting identity's credential goes there as a bearer
token (RFC 7481 §3.2); a public server ignores it.

`days_left` is the whole days from `read_at` to the expiry moment, rounded down, negative once
it has passed (ADR-0196 §4). `key` names the thing and its expiry moment, so that a process can
mark what it filed and a renewal is a new key.

How the RDAP server's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: the name is not one the server accepts | `invalid` |
| 401: the credential is not admitted | `unauthenticated` |
| 403 | `forbidden` |
| 404: the registry holds no such domain | `not_found` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not RDAP's | `unexpected` |

A TLS endpoint that cannot be reached is `unavailable`; one that completes no handshake is
`unexpected`.
"""

from __future__ import annotations

import asyncio
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
LABEL = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
DOMAIN = re.compile(rf"^(?=.{{1,253}}$)({LABEL}\.)+{LABEL}$")
EVENTS = {"expiration": "expires", "registration": "registered", "last changed": "last_changed"}


def endpoint(text: str) -> tuple[str, int]:
    """`host:port`, or `host` for port 443, as the configuration names an endpoint."""
    host, _, port = text.rpartition(":") if ":" in text else (text, "", "443")
    if not HOST.match(host) or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError(f"not an endpoint host:port: {text!r}")
    return host.lower(), int(port)


@dataclass(frozen=True)
class Config:
    endpoints: frozenset[tuple[str, int]]
    """The TLS endpoints a call may read, as (host, port)."""
    rdap: str
    """The RDAP server's base address; empty when no domain is read."""
    ca_file: str | None = None
    """An authority the verification trusts beside the system's store."""
    timeout: float = 30.0


def _moment(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _days_left(until: datetime, now: datetime) -> int:
    return int((until - now).total_seconds() // 86400)


async def _handshake(host: str, port: int, context: ssl.SSLContext, seconds: float) -> bytes:
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=context, server_hostname=host), seconds
    )
    del reader
    try:
        der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
    finally:
        writer.close()
    if not der:
        raise TargetError("unexpected", "none", False, "the endpoint presented no certificate")
    return bytes(der)


def _name(name: x509.Name) -> str | None:
    common = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(common[0].value) if common else name.rfc4514_string() or None


def _names(certificate: x509.Certificate) -> list[str]:
    try:
        san = certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    except x509.ExtensionNotFound:
        return []
    value = san.value
    if not isinstance(value, x509.SubjectAlternativeName):
        return []
    return [str(n) for n in value.get_values_for_type(x509.DNSName)] + [
        str(n) for n in value.get_values_for_type(x509.IPAddress)
    ]


async def certificate(config: Config, call: Call, input: Json) -> Outcome:
    host = input.get("host")
    port = input.get("port", 443)
    if not isinstance(host, str) or isinstance(port, bool) or not isinstance(port, int):
        raise invalid("host must be a text and port a whole number")
    if (host.lower(), port) not in config.endpoints:
        raise invalid("the endpoint is not one the connector is configured for")
    host = host.lower()
    verifying = ssl.create_default_context(cafile=config.ca_file)
    failure: str | None = None
    try:
        call.count()
        der = await _handshake(host, port, verifying, config.timeout)
    except ssl.SSLCertVerificationError as error:
        failure = str(error.verify_message or "the certificate does not verify")
        reading = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        reading.check_hostname = False
        reading.verify_mode = ssl.CERT_NONE  # only to read what failed to verify
        try:
            call.count()
            der = await _handshake(host, port, reading, config.timeout)
        except (OSError, TimeoutError) as again:
            raise _unreached(again) from again
    except ssl.SSLError as error:
        raise TargetError(
            "unexpected", "none", False, f"the endpoint completed no TLS handshake: {error.reason}"
        ) from error
    except (OSError, TimeoutError) as error:
        raise _unreached(error) from error
    try:
        parsed = x509.load_der_x509_certificate(der)
    except ValueError as error:
        raise TargetError(
            "unexpected", "none", False, "the endpoint's certificate is not X.509"
        ) from error
    now = datetime.now(UTC)
    until = parsed.not_valid_after_utc
    return Outcome(
        output={
            "host": host,
            "port": port,
            "subject": _name(parsed.subject),
            "issuer": _name(parsed.issuer),
            "names": _names(parsed),
            "serial": format(parsed.serial_number, "x"),
            "not_before": _moment(parsed.not_valid_before_utc),
            "not_after": _moment(until),
            "read_at": _moment(now),
            "days_left": _days_left(until, now),
            "trusted": failure is None,
            "verify_failure": failure,
            "key": f"certificate:{host}:{port}:{_moment(until)}",
        },
        effect={"kind": "read"},
    )


def _unreached(error: BaseException) -> TargetError:
    # The type alone: an error's text can quote the address.
    return unavailable(f"the endpoint could not be reached: {type(error).__name__}")


def _event_dates(events: Any) -> dict[str, datetime | None]:
    found: dict[str, datetime | None] = dict.fromkeys(EVENTS.values())
    if not isinstance(events, list):
        return found
    for event in events:
        if not isinstance(event, dict):
            continue
        field = EVENTS.get(str(event.get("eventAction", "")).lower())
        text = event.get("eventDate")
        if field is None or not isinstance(text, str):
            continue
        try:
            at = datetime.fromisoformat(text)
        except ValueError as error:
            raise TargetError(
                "unexpected", "none", False, "an event's date is not an RFC 3339 moment"
            ) from error
        found[field] = at if at.tzinfo else at.replace(tzinfo=UTC)
    return found


async def domain(config: Config, call: Call, input: Json) -> Outcome:
    name = input.get("domain")
    if not isinstance(name, str) or not DOMAIN.match(name.lower().rstrip(".")):
        raise invalid("domain must be a domain name in its ASCII form, such as example.com")
    if not config.rdap:
        raise invalid("the connector is configured with no RDAP server")
    name = name.lower().rstrip(".")
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.rdap.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={
                "Authorization": f"Bearer {call.token}",
                "Accept": "application/rdap+json",
            },
            follow_redirects=False,
        ) as client:
            response = await client.get(f"/domain/{name}")
    except httpx.TimeoutException as error:
        raise unavailable(
            f"the RDAP server did not answer in time: {type(error).__name__}"
        ) from error
    except httpx.HTTPError as error:
        raise unavailable(
            f"the RDAP server could not be reached: {type(error).__name__}"
        ) from error
    status = response.status_code
    if status == 400:
        raise invalid("the RDAP server does not accept the name")
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the server does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not read this registration")
    if status == 404:
        raise TargetError("not_found", "none", False, "the registry holds no such domain")
    if status == 429 or status >= 500:
        raise unavailable(f"the RDAP server answered {status}")
    try:
        body = response.json()
    except ValueError:
        body = None
    if status != 200 or not isinstance(body, dict) or body.get("objectClassName") != "domain":
        raise TargetError(
            "unexpected", "none", False, f"the RDAP server answered {status} without a domain"
        )
    dates = _event_dates(body.get("events"))
    now = datetime.now(UTC)
    expires = dates["expires"]
    status_list = body.get("status")
    return Outcome(
        output={
            "domain": str(body.get("ldhName") or name).lower(),
            "handle": body.get("handle") if isinstance(body.get("handle"), str) else None,
            "expires": _moment(expires) if expires else None,
            "registered": _moment(d) if (d := dates["registered"]) else None,
            "last_changed": _moment(d) if (d := dates["last_changed"]) else None,
            "status": [str(s) for s in status_list] if isinstance(status_list, list) else [],
            "read_at": _moment(now),
            "days_left": _days_left(expires, now) if expires else None,
            "key": f"domain:{name}:{_moment(expires) if expires else 'none'}",
        },
        effect={"kind": "read"},
    )


OPERATIONS = {"expiry.certificates.read": certificate, "expiry.domains.read": domain}
