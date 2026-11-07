"""`mail.messages` and `channel.mail.reply` over the Resend API, with the inputs and outputs of
the mail connector (`connectors/taktus_connectors/mail/`), so that a process runs on either.

**A message is named by the service's identifier.** The API names every message it sent or
received by an identifier of its own; that identifier is `message_id` here, in an input and in
an output. A message received is read from `GET /emails/receiving/<id>`, one sent from
`GET /emails/<id>`.

**Two guards.** The first is the API's own: the send carries the idempotency key as the
`Idempotency-Key` header, which the API honours for 24 hours; a repeat within them sends nothing
twice. The second is the mark. A message sent carries the tag `taktus_key`, the first 40
hexadecimal digits of the SHA-256 of the idempotency key; the key itself never leaves Taktus.
Before sending, the connector lists the hundred messages sent most recently and reads those to
the same recipients under the same subject, two at most: one that carries the tag is the
original, and nothing is sent.

**Where the promise ends.** Beyond 24 hours, a copy older than the latest hundred messages
sent, or behind two later ones to the same recipients under the same subject, is not found,
and a repeat sends again. Within 24 hours a repeat the lookup did not find is held by the API's
key, which answers the original's identifier; the connector cannot tell it from a new one, and
the result says `replayed: false`.

**An automatic message is not answered.** The webhook carries no headers, so the intake cannot
see that a message was sent by an automaton. The reply reads the message it answers first, and
refuses one whose `Auto-Submitted` is not `no` (RFC 3834), or that a list or a bulk sender sent,
as `invalid`.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from email.utils import getaddresses
from typing import Any

from taktus_connectors.resend.api import Config, request, unexpected
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

IDENTIFIER = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
ADDRESS = re.compile(r"^[^@\s<>,;\"]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")
MAX_TEXT = 1_000_000
MAX_RECIPIENTS = 50
FOLDERS = ("inbox", "sent")
TAG = "taktus_key"
PAGE = 100
PAGES = 1
CANDIDATES = 2
AUTOMATED = frozenset({"bulk", "list", "junk"})


def mark_of(key: str) -> str:
    """The tag's value a send with this key carries: a digest of the key, never the key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]


def identifier(value: Any, name: str = "message_id") -> str:
    if not isinstance(value, str) or IDENTIFIER.match(value.strip()) is None:
        raise invalid(f"{name} must be the identifier the mail service gave the message")
    return value.strip().lower()


def addresses(value: Any) -> list[str]:
    """The plain addresses in a field of the API: a string or a list of strings, each an
    address or a name and an address."""
    given = [value] if isinstance(value, str) else value
    if not isinstance(given, list):
        return []
    return [a for _, a in getaddresses([str(v) for v in given if isinstance(v, str)]) if a]


def _recipients(value: Any) -> list[str]:
    given = [value] if isinstance(value, str) else value
    if not isinstance(given, list) or not 1 <= len(given) <= MAX_RECIPIENTS:
        raise invalid(f"to must be an address or a list of 1 to {MAX_RECIPIENTS} addresses")
    out = []
    for item in given:
        if not isinstance(item, str) or ADDRESS.match(item.strip()) is None:
            raise invalid("every recipient must be a plain address, local@domain")
        out.append(item.strip())
    return out


def _line(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) > 900 or "\r" in value or "\n" in value:
        raise invalid(f"{name} must be one line of at most 900 characters")
    return value


def _text(input: Json) -> str:
    text = input.get("text")
    if not isinstance(text, str) or not text or len(text) > MAX_TEXT:
        raise invalid(f"text must be a text of 1 to {MAX_TEXT} characters")
    return text


def moment(value: Any) -> str | None:
    """A moment as the API writes it, `2026-04-03 22:13:42.674981+00` or ISO 8601, in UTC."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace(" ", "T", 1).replace("Z", "+00:00")
    if re.search(r"[+-]\d{2}$", text):
        text += ":00"
    try:
        found = datetime.fromisoformat(text)
    except ValueError:
        return None
    if found.tzinfo is None:
        found = found.replace(tzinfo=UTC)
    return found.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _headers(found: Json) -> dict[str, str]:
    given = found.get("headers")
    if not isinstance(given, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in given.items()}


async def _message(config: Config, call: Call, mid: str, folder: str) -> Json:
    path = f"/emails/receiving/{mid}" if folder == "inbox" else f"/emails/{mid}"
    found = await request(config, call, "GET", path)
    if not isinstance(found, dict) or not isinstance(found.get("id"), str):
        raise unexpected("the API answered a message in a shape the connector does not know")
    return found


def message_output(found: Json, mid: str) -> Json:
    """What a reading yields of a message, in the mail connector's shape."""
    headers = _headers(found)
    attachments = found.get("attachments") or []
    return {
        "message_id": mid,
        "from": addresses(found.get("from")),
        "to": addresses(found.get("to")),
        "cc": addresses(found.get("cc")),
        "subject": str(found.get("subject") or ""),
        "date": moment(found.get("created_at")),
        "in_reply_to": headers.get("in-reply-to", "").strip() or None,
        "text": str(found.get("text") or "").replace("\r\n", "\n"),
        "attachments": [
            {"name": str(a.get("filename") or ""), "type": str(a.get("content_type") or "")}
            for a in attachments
            if isinstance(a, dict)
        ],
    }


async def read(config: Config, call: Call, input: Json) -> Outcome:
    mid = identifier(input.get("message_id"))
    folder = input.get("folder", "inbox")
    if folder not in FOLDERS:
        raise invalid("folder is inbox or sent")
    found = await _message(config, call, mid, folder)
    return Outcome(output=message_output(found, mid), effect={"kind": "read"})


def _tagged(found: Json, mark: str) -> bool:
    return any(
        isinstance(t, dict) and t.get("name") == TAG and t.get("value") == mark
        for t in found.get("tags") or []
    )


async def _marked(
    config: Config, call: Call, mark: str, to: list[str], subject: str
) -> Json | None:
    """The message sent earlier with this mark, or None."""
    wanted = sorted(a.lower() for a in to)
    after: str | None = None
    looked = 0
    for _ in range(PAGES):
        params: Json = {"limit": PAGE}
        if after:
            params["after"] = after
        listed = await request(config, call, "GET", "/emails", params=params)
        data = listed.get("data") if isinstance(listed, dict) else None
        if not isinstance(data, list):
            raise unexpected("the API's list of messages sent is not a list")
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            same = sorted(a.lower() for a in addresses(item.get("to"))) == wanted
            if not same or str(item.get("subject") or "") != subject:
                continue
            if looked >= CANDIDATES:
                return None
            looked += 1
            found = await _message(config, call, item["id"], "sent")
            if _tagged(found, mark):
                return found
        if not listed.get("has_more") or not data:
            return None
        after = str(data[-1].get("id", "")) or None
        if after is None:
            return None
    return None


def _digest(body: Json) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _effect(mid: str, body: Json, *, replayed: bool) -> Json:
    return {
        "kind": "delivery",
        "replayed": replayed,
        "records": [{"kind": "mail.message", "id": mid}],
        "content_digest": _digest(body),
    }


def _automatic(headers: dict[str, str]) -> str | None:
    """Why a message was sent by an automaton, or None."""
    submitted = headers.get("auto-submitted", "no").strip().lower()
    if submitted != "no":
        return f"Auto-Submitted: {submitted}"
    if headers.get("precedence", "").strip().lower() in AUTOMATED:
        return f"Precedence: {headers['precedence'].strip().lower()}"
    if "list-id" in headers:
        return "a list sent it"
    return None


async def _send(
    config: Config,
    call: Call,
    to: list[str],
    subject: str | None,
    text: str,
    answered: str | None,
    *,
    automatic: bool,
) -> Outcome:
    headers: dict[str, str] = {}
    if answered is not None:
        original = await _message(config, call, answered, "inbox")
        if automatic and (why := _automatic(_headers(original))) is not None:
            raise invalid(f"an automatic message is not answered ({why})")
        reference = str(original.get("message_id") or "").strip()
        if reference:
            headers["In-Reply-To"] = reference
            headers["References"] = reference
        if subject is None:
            before = str(original.get("subject") or "").strip()
            subject = before if before.lower().startswith("re:") else f"Re: {before}"
    if subject is None:
        subject = "Re: your message"
    if automatic:
        # RFC 3834: an automatic reply says so, and an automaton does not answer it.
        headers["Auto-Submitted"] = "auto-replied"
    mark = mark_of(call.key)
    body: Json = {"from": config.sender, "to": to, "subject": subject, "text": text}
    if headers:
        body["headers"] = headers
    output = {"to": to, "subject": subject, "refused": [], "filed": True}
    found = await _marked(config, call, mark, to, subject)
    if found is not None:
        mid = str(found["id"])
        return Outcome({"message_id": mid, **output}, _effect(mid, body, replayed=True))
    sent = await request(
        config,
        call,
        "POST",
        "/emails",
        body={**body, "tags": [{"name": TAG, "value": mark}]},
        key=call.key[:256],
    )
    if not isinstance(sent, dict) or not isinstance(sent.get("id"), str):
        raise TargetError("unknown", "unknown", False, "the API answered the send unreadably")
    mid = sent["id"]
    return Outcome({"message_id": mid, **output}, _effect(mid, body, replayed=False))


async def send(config: Config, call: Call, input: Json) -> Outcome:
    to = _recipients(input.get("to"))
    subject = _line(input.get("subject"), "subject")
    text = _text(input)
    answered = input.get("in_reply_to")
    answered = identifier(answered, "in_reply_to") if answered is not None else None
    return await _send(config, call, to, subject, text, answered, automatic=False)


async def reply(config: Config, call: Call, input: Json) -> Outcome:
    to = _recipients(input.get("address"))
    thread = input.get("thread")
    thread = identifier(thread, "thread") if thread else None
    text = _text(input)
    return await _send(config, call, to, None, text, thread, automatic=True)


OPERATIONS = {
    "mail.messages.read": read,
    "mail.messages.send": send,
    "channel.mail.reply": reply,
}
