"""What the mail connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Three operations and an intake. A read of one message is `read`. A message sent is a
`delivery`: it reaches a person (ADR-0022). Its idempotency is `marked`: the message identifier
is derived from the idempotency key, and a copy of every message sent is kept in the sent
folder, where a repeat finds it before sending (`operations.py`). The reply on the channel is
the same send, addressed by what an accepted intake carried (contract §7).

Demand counts requests as sessions with the server: a read opens one IMAP session; a send looks
in the sent folder, submits over SMTP and files the copy, three.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CHANNEL = "channel.mail"

ACTIONS_CREDENTIAL = "MAIL_PASSWORD"
INTAKE_CREDENTIAL = "MAIL_INTAKE_SECRET"

CAPABILITIES = ["mail.messages", CHANNEL]

OPERATIONS: list[Json] = [
    {
        "name": "mail.messages.read",
        "demand": {"quota_units": 1},
        "capability": "mail.messages",
        "effect": "read",
        "summary": "Read one message by its message identifier, from the inbox or the sent "
        "folder: its addresses, subject, date, the text of its plain part and the names of "
        "its attachments. Never an attachment's content.",
    },
    {
        "name": "mail.messages.send",
        "demand": {"quota_units": 3},
        "capability": "mail.messages",
        "effect": "delivery",
        "idempotency": "marked",
        "summary": "Send a message of plain text to one or more addresses, as a reply when "
        "`in_reply_to` names a message. Its message identifier is derived from the "
        "idempotency key, and a copy is filed in the sent folder; a repeat finds the copy "
        "there and sends nothing.",
    },
    {
        "name": "channel.mail.reply",
        "demand": {"quota_units": 3},
        "capability": CHANNEL,
        "effect": "delivery",
        "idempotency": "marked",
        "summary": "Answer at a reply address this connector's intake produced — `address`, "
        "an optional `thread`, `text` — as `mail.messages.send` sends, marked as an "
        "automatic reply (contract §7).",
    },
]

INTAKE_EVENTS = ["message.posted"]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": list(CAPABILITIES),
        "operations": [dict(op) for op in OPERATIONS],
        "intake": {"events": list(INTAKE_EVENTS), "signature": {"scheme": "hmac-sha256"}},
        "credentials": [
            {"name": ACTIONS_CREDENTIAL, "purpose": "actions"},
            {"name": INTAKE_CREDENTIAL, "purpose": "intake"},
        ],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
