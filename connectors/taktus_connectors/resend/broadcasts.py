"""`newsletter.broadcasts` over the Resend Broadcasts API, with the inputs and outputs of the
newsletter connector (`connectors/taktus_connectors/mailchimp/`), so that the newsletter
process runs on either.

**The audience is a segment.** The API sends a broadcast to the contacts of one segment; the
input `list` is the segment's identifier. The API counts no recipients: `recipients` is the
number of the segment's contacts that are not unsubscribed, counted page by page from
`GET /contacts?segment_id=`, a hundred per page, fifty pages at most. A segment of more contacts
than that is counted as unknown, `null`. A broadcast to a topic reaches fewer: those
unsubscribed from the topic are not subtracted. No contact's address leaves the connector.

**The mark of a draft.** A broadcast has an internal name the recipients never see (`name`). A
draft is created with the name `taktus-` and the first 24 hexadecimal digits of the SHA-256 of
the idempotency key; the key itself never leaves Taktus. Before creating, the connector lists
the account's broadcasts, a hundred per page, ten pages at most, and looks for that name: one
found is the original, and nothing is created again.

**The mark of a send.** A broadcast that is `scheduled`, `queued` or `sent` is not sent again:
its status is its own mark. Weaker than a key, and stated so: a repeat after somebody else sent
the broadcast reports replayed too. One `canceled` cannot be sent again, `conflict`.

What the API does not have is `null` in the output: a broadcast has no number of its own that
people see (`web_id`) and the API reports no count of messages sent (`emails_sent`).
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any

from taktus_connectors.resend.api import Config, request, unexpected
from taktus_connectors.resend.messages import moment
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

IDENTIFIER = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
ADDRESS = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
NAME = re.compile(r"^[^<>\"\r\n]{1,100}$")
SUBJECT = 150
TEXT = 200_000
PAGE = 100
PAGES = 10
CONTACT_PAGES = 50
SENT = frozenset({"scheduled", "queued", "sent"})


def mark(key: str) -> str:
    """The draft's internal name: a digest of the key, never the key."""
    return "taktus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _identifier(input: Json, field: str) -> str:
    value = input.get(field)
    if not isinstance(value, str) or IDENTIFIER.match(value) is None:
        raise invalid(f"{field} must be the identifier the newsletter service gave it")
    return value.lower()


def _text(input: Json, field: str, limit: int, *, required: bool = True) -> str | None:
    value = input.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise invalid(f"{field} must be text of at most {limit} characters")
    return value


async def _count(config: Config, call: Call, segment: str) -> int | None:
    """The segment's contacts that are not unsubscribed; None beyond the pages counted."""
    count = 0
    after: str | None = None
    for _ in range(CONTACT_PAGES):
        params: Json = {"segment_id": segment, "limit": PAGE}
        if after:
            params["after"] = after
        listed = await request(config, call, "GET", "/contacts", params=params)
        data = listed.get("data") if isinstance(listed, dict) else None
        if not isinstance(data, list):
            raise unexpected("the API's list of contacts is not a list")
        count += sum(1 for c in data if isinstance(c, dict) and c.get("unsubscribed") is False)
        if not listed.get("has_more") or not data:
            return count
        after = str(data[-1].get("id", "")) or None
        if after is None:
            return None
    return None


def broadcast_output(found: Any, recipients: int | None) -> Json:
    """What a reading yields of a broadcast: never a recipient."""
    if not isinstance(found, dict) or not isinstance(found.get("id"), str):
        raise unexpected("the API answered a broadcast in a shape the connector does not know")
    segment = found.get("segment_id") or found.get("audience_id")
    return {
        "id": found["id"],
        "web_id": None,
        "status": str(found.get("status", "")),
        "list": segment if isinstance(segment, str) else None,
        "recipients": recipients,
        "emails_sent": None,
        "send_time": moment(found.get("sent_at")),
    }


async def _broadcast(config: Config, call: Call, identifier: str) -> Json:
    found = await request(config, call, "GET", f"/broadcasts/{identifier}")
    broadcast_output(found, None)  # refuses a shape it does not know
    segment = found.get("segment_id") or found.get("audience_id")
    recipients = await _count(config, call, segment) if isinstance(segment, str) else None
    return broadcast_output(found, recipients)


async def _marked(config: Config, call: Call, name: str) -> Json | None:
    """The account's broadcast whose internal name is the mark, or None."""
    after: str | None = None
    for _ in range(PAGES):
        params: Json = {"limit": PAGE}
        if after:
            params["after"] = after
        listed = await request(config, call, "GET", "/broadcasts", params=params)
        data = listed.get("data") if isinstance(listed, dict) else None
        if not isinstance(data, list):
            raise unexpected("the API's list of broadcasts is not a list")
        for found in data:
            if isinstance(found, dict) and found.get("name") == name:
                return dict(found)
        if not listed.get("has_more") or not data:
            return None
        after = str(data[-1].get("id", "")) or None
        if after is None:
            return None
    raise unavailable(f"the account holds more than {PAGES * PAGE} broadcasts to look through")


def _write(output: Json, kind: str, *, replayed: bool) -> Outcome:
    records = [{"kind": kind, "id": str(output["id"])}]
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


def _html(text: str) -> str:
    """The plain text as HTML, paragraph by paragraph, every character escaped."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "".join(
        "<p>" + html.escape(p.strip()).replace("\n", "<br>") + "</p>" for p in paragraphs
    )


async def read(config: Config, call: Call, input: Json) -> Outcome:
    return Outcome(await _broadcast(config, call, _identifier(input, "id")), {"kind": "read"})


async def draft(config: Config, call: Call, input: Json) -> Outcome:
    segment = _identifier(input, "list")
    subject = _text(input, "subject", SUBJECT)
    text = _text(input, "text", TEXT)
    given_html = _text(input, "html", TEXT, required=False)
    sender = input.get("from_name")
    if not isinstance(sender, str) or NAME.match(sender) is None:
        raise invalid('from_name must be a name of at most 100 characters, without <, > or "')
    reply_to = input.get("reply_to")
    if not isinstance(reply_to, str) or ADDRESS.match(reply_to) is None:
        raise invalid("reply_to must be a mail address")
    name = mark(call.key)
    found = await _marked(config, call, name)
    if found is not None:
        return _write(
            await _broadcast(config, call, str(found["id"])), "newsletter.campaign", replayed=True
        )
    created = await request(
        config,
        call,
        "POST",
        "/broadcasts",
        body={
            "segment_id": segment,
            "from": f"{sender} <{config.sender}>",
            "subject": subject,
            "reply_to": reply_to,
            "text": text,
            "html": given_html or _html(str(text)),
            "name": name,
        },
    )
    if not isinstance(created, dict) or not isinstance(created.get("id"), str):
        raise TargetError("unknown", "unknown", False, "the API answered the draft unreadably")
    return _write(
        await _broadcast(config, call, created["id"]), "newsletter.campaign", replayed=False
    )


async def send(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input, "id")
    before = await _broadcast(config, call, identifier)
    if before["status"] in SENT:
        return _write(before, "newsletter.send", replayed=True)
    if before["status"] == "canceled":
        raise TargetError("conflict", "none", False, "a canceled broadcast cannot be sent again")
    await request(config, call, "POST", f"/broadcasts/{identifier}/send", body={})
    # The API answers and starts sending; the broadcast is not read again, so that a reading
    # that fails after the send cannot report a send that happened as one that did not.
    return _write({**before, "status": "queued"}, "newsletter.send", replayed=False)


OPERATIONS = {
    "newsletter.broadcasts.read": read,
    "newsletter.broadcasts.draft": draft,
    "newsletter.broadcasts.send": send,
}
