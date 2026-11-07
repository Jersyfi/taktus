"""What the customer system connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes of the capability `crm.contacts`, declared `scoped` (ADR-0130,
ADR-0209): every operation names one address, and a call that serves a case answers only the
case's subject, refusing another address as `out_of_scope` before the system is asked.

Creating a contact is `marked` by the address itself, as scaling is marked by its number
(ADR-0097): a repeat that finds a contact carrying the address creates none and reports
replayed. A note is `marked` by the idempotency key in its last line, found again among the
contact's notes. Merging two contacts is not declared: the system cannot undo it, and B-5.05
proposes it to a person.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "crm.contacts"
ACTIONS_CREDENTIAL = "CRM_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "crm.contacts.create",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a contact with the address `email`, and nothing else of the person. "
        "The address is its own mark: a repeat that finds a contact carrying it creates none "
        "and reports replayed, with the oldest such contact. Weaker than a key, and stated so: "
        "a contact somebody else created for the address reports replayed too. Scoped.",
    },
    {
        "name": "crm.contacts.find",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Every contact that carries `email` as its address or as an additional one, "
        "oldest first: each its id, email, created_at, updated_at and lifecycle_stage, and "
        "nothing else of the person. `count` is how many; two or more are duplicates. Scoped: "
        "a call that serves a case answers only the case's subject.",
    },
    {
        "name": "crm.contacts.note",
        "demand": {"quota_units": 4},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Write `text` as a note of a touchpoint on the oldest contact carrying "
        "`email`; no such contact is not_found. The note's last line carries the idempotency "
        "key, and a repeat that finds it among the contact's notes writes nothing and reports "
        "replayed. Scoped.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
        "scoped": [CAPABILITY],
    }
