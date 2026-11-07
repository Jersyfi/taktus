"""What the transactional mail connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

The operations of the mail connector under the same names, inputs and outputs, so that the
support processes run on either, and the operations of the newsletter connector likewise, so
that the newsletter process does. A message sent is a `delivery`, `marked`: it carries a tag
with a digest of the idempotency key, which a repeat finds among the messages sent, and the
API's own idempotency key besides. A broadcast's draft is `marked` by its internal name, its
send by its status. The intake is the service's webhook, signed under the open specification
of signed webhooks (ADR-0186).

Demand counts requests. A send reads the message it answers, lists the hundred messages sent
most recently and reads at most two of them before it sends: five at most, four without a
message answered. A reading of a broadcast counts the segment's contacts, at most fifty pages.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
MAIL = "mail.messages"
CHANNEL = "channel.mail"
NEWSLETTER = "newsletter.broadcasts"

ACTIONS_CREDENTIAL = "MAIL_PASSWORD"
"""The parameter the support processes reference; here it holds an API key."""
NEWSLETTER_CREDENTIAL = "NEWSLETTER_TOKEN"
"""The parameter the newsletter process references; an API key with full access."""
INTAKE_CREDENTIAL = "MAIL_INTAKE_SECRET"
"""The webhook's signing secret, as the service shows it."""

OPERATIONS: list[Json] = [
    {
        "name": "mail.messages.read",
        "demand": {"quota_units": 1},
        "capability": MAIL,
        "effect": "read",
        "summary": "Read one message by the service's identifier, from what the domain received "
        "(`inbox`) or what was sent (`sent`): its addresses, subject, date, the text of its "
        "plain part and the names of its attachments. Never an attachment's content.",
    },
    {
        "name": "mail.messages.send",
        "demand": {"quota_units": 5},
        "capability": MAIL,
        "effect": "delivery",
        "idempotency": "marked",
        "summary": "Send a message of plain text to one or more addresses, as a reply when "
        "`in_reply_to` names a received message. The message carries a tag with a digest of the "
        "idempotency key, which a repeat finds among the hundred messages sent most recently, "
        "and the API's own idempotency key, honoured for 24 hours.",
    },
    {
        "name": "channel.mail.reply",
        "demand": {"quota_units": 5},
        "capability": CHANNEL,
        "effect": "delivery",
        "idempotency": "marked",
        "summary": "Answer at a reply address this connector's intake produced — `address`, "
        "an optional `thread`, `text` — as `mail.messages.send` sends, marked as an "
        "automatic reply (contract §7). An automatic message is not answered.",
    },
    {
        "name": "newsletter.broadcasts.read",
        "demand": {"quota_units": 51},
        "capability": NEWSLETTER,
        "effect": "read",
        "summary": "Read one broadcast: its status, its segment, how many subscribed contacts "
        "the segment holds, and when it was sent. Never a recipient's address.",
    },
    {
        "name": "newsletter.broadcasts.draft",
        "demand": {"quota_units": 62},
        "capability": NEWSLETTER,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a broadcast to one segment as a draft, with its subject, sender name, "
        "reply address and content. Nothing is sent. The broadcast's internal name carries a "
        "digest of the idempotency key; a repeat finds the broadcast by it.",
    },
    {
        "name": "newsletter.broadcasts.send",
        "demand": {"quota_units": 52},
        "capability": NEWSLETTER,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Send a drafted broadcast to its segment. The broadcast's status is its own "
        "mark: one already scheduled, queued or sent is not sent again and reports replayed. "
        "Weaker than a key, and stated so.",
    },
]

INTAKE_EVENTS = ["message.posted"]
SCHEME = "hmac-sha256-identified"


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [MAIL, CHANNEL, NEWSLETTER],
        "operations": [dict(op) for op in OPERATIONS],
        "intake": {"events": list(INTAKE_EVENTS), "signature": {"scheme": SCHEME}},
        "credentials": [
            {"name": ACTIONS_CREDENTIAL, "purpose": "actions"},
            {"name": NEWSLETTER_CREDENTIAL, "purpose": "actions"},
            {"name": INTAKE_CREDENTIAL, "purpose": "intake"},
        ],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
