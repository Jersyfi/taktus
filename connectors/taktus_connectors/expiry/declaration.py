"""What the expiry connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations, both of effect `read`: reading a certificate or a registration changes nothing.
A certificate read makes one handshake, or two when the first does not verify; a domain read
makes one request (ADR-0196).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CERTIFICATES = "expiry.certificates"
DOMAINS = "expiry.domains"
ACTIONS_CREDENTIAL = "EXPIRY_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "expiry.certificates.read",
        "demand": {"quota_units": 2},
        "capability": CERTIFICATES,
        "effect": "read",
        "summary": "Read the certificate a configured TLS endpoint (`host`, `port`) presents: "
        "subject, issuer, the names it covers, its validity, whether it verifies with the "
        "reason when it does not, and the whole days left from the moment it was read. An "
        "endpoint the connector is not configured for is refused.",
    },
    {
        "name": "expiry.domains.read",
        "demand": {"quota_units": 1},
        "capability": DOMAINS,
        "effect": "read",
        "summary": "Read a domain's registration at the configured RDAP server: its expiration, "
        "registration and last change as the registry gave them, its status, and the whole "
        "days left from the moment it was read. A registration without an expiration answers "
        "`expires` and `days_left` null.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CERTIFICATES, DOMAINS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
