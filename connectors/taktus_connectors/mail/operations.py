"""What each operation does, and how a repeat is recognised.

**The mark.** A message sent carries a message identifier derived from the idempotency key:
`<` the first 40 hexadecimal digits of the key's SHA-256 `.taktus@` the sender's domain `>`.
The key itself never leaves Taktus; a recipient sees only its digest. The same key gives the
same identifier, so the identifier is the mark.

**The lookup, before sending.** A copy of every message sent is in the sent folder: the
connector files it there after the server accepted the message, or the server files it itself
(`Config.file_sent`). Before sending, the connector searches the sent folder for the mark. A
copy found is the original: the call returns it with `replayed: true` and sends nothing. IMAP
answers a search from what it holds, so a copy filed is found by the next search.

**Where the promise ends.** Between the server's acceptance and the copy filed lies one IMAP
session. A connector stopped exactly there has sent a message no lookup finds, and a repeat
sends it again, with the same message identifier. A receiving system that recognises
identifiers — this connector's intake does — keeps one; a person reading the mailbox sees two.

Every function takes the configuration, the call and the operation's input, and returns an
`Outcome`. Input the operation cannot use is an `invalid` error before any session is opened.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import format_datetime, getaddresses, parsedate_to_datetime
from typing import Any

from taktus_connectors.mail.protocol import Config, imap, submit
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

MESSAGE_ID = re.compile(r"^<[^<>\s]{1,250}@[^<>\s]{1,250}>$")
MARK = re.compile(r"^<[0-9a-f]{40}\.taktus@[^<>\s]+>$")
ADDRESS = re.compile(r"^[^@\s<>,;\"]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")
MAX_TEXT = 1_000_000
MAX_RECIPIENTS = 50
FOLDERS = ("inbox", "sent")


def mark_of(key: str, domain: str) -> str:
    """The message identifier a send with this key carries."""
    return f"<{hashlib.sha256(key.encode()).hexdigest()[:40]}.taktus@{domain}>"


def is_own(message_id: str) -> bool:
    return MARK.match(message_id.strip()) is not None


def message_id(value: Any, name: str = "message_id") -> str:
    if not isinstance(value, str):
        raise invalid(f"{name} must be a message identifier, <local@domain>")
    text = value.strip()
    if not text.startswith("<"):
        text = f"<{text}>"
    if MESSAGE_ID.match(text) is None:
        raise invalid(f"{name} must be a message identifier, <local@domain>")
    return text


def _addresses(value: Any) -> list[str]:
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


def parse(raw: bytes) -> EmailMessage:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if not isinstance(message, EmailMessage):  # the default policy always makes one
        raise TargetError("unexpected", "none", False, "a message the parser cannot read")
    return message


def text_of(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain",))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):
        return ""
    return content.replace("\r\n", "\n") if isinstance(content, str) else ""


def addresses_in(message: Message, header: str) -> list[str]:
    return [address for _, address in getaddresses(message.get_all(header, [])) if address]


def moment_of(message: Message) -> str | None:
    value = message.get("Date")
    if not value:
        return None
    try:
        moment = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest_of(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_sync(config: Config, call: Call, mid: str, folder: str) -> bytes:
    call.count()
    with imap(config, call.token) as session:
        session.select(config.inbox if folder == "inbox" else config.sent)
        found = session.by_header("Message-ID", mid)
        if not found:
            raise TargetError("not_found", "none", False, f"no message {mid} in the {folder}")
        return session.fetch(found[0])


async def read(config: Config, call: Call, input: Json) -> Outcome:
    mid = message_id(input.get("message_id"))
    folder = input.get("folder", "inbox")
    if folder not in FOLDERS:
        raise invalid("folder is inbox or sent")
    raw = await asyncio.to_thread(_read_sync, config, call, mid, folder)
    message = parse(raw)
    attachments = [
        {"name": part.get_filename() or "", "type": part.get_content_type()}
        for part in message.iter_attachments()
    ]
    return Outcome(
        output={
            "message_id": mid,
            "from": addresses_in(message, "From"),
            "to": addresses_in(message, "To"),
            "cc": addresses_in(message, "Cc"),
            "subject": str(message.get("Subject", "")),
            "date": moment_of(message),
            "in_reply_to": str(message.get("In-Reply-To", "")).strip() or None,
            "text": text_of(message),
            "attachments": attachments,
        },
        effect={"kind": "read"},
    )


def _compose(
    config: Config,
    mid: str,
    to: list[str],
    subject: str,
    text: str,
    reply_to: str | None,
    *,
    automatic: bool,
) -> bytes:
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = config.address
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message["Date"] = format_datetime(datetime.now(UTC))
    message["Message-ID"] = mid
    if reply_to:
        message["In-Reply-To"] = reply_to
        message["References"] = reply_to
    if automatic:
        # RFC 3834: an automatic reply says so, and an automaton does not answer it.
        message["Auto-Submitted"] = "auto-replied"
    message.set_content(text)
    return message.as_bytes()


def _send_sync(
    config: Config,
    call: Call,
    to: list[str],
    subject: str | None,
    text: str,
    reply_to: str | None,
    *,
    automatic: bool,
) -> tuple[Json, Json]:
    mid = mark_of(call.key, config.domain)
    call.count()
    with imap(config, call.token) as session:
        session.select(config.sent)
        found = session.by_header("Message-ID", mid)
        if found:
            raw = session.fetch(found[0])
            copy = parse(raw)
            output = {
                "message_id": mid,
                "to": addresses_in(copy, "To"),
                "subject": str(copy.get("Subject", "")),
                "refused": [],
                "filed": True,
            }
            return output, _effect(mid, raw, replayed=True)
        if subject is None:
            subject = "Re: your message"
            if reply_to is not None:
                session.select(config.inbox)
                original = session.by_header("Message-ID", reply_to)
                if original:
                    before = str(parse(session.fetch(original[0])).get("Subject", "")).strip()
                    subject = before if before.lower().startswith("re:") else f"Re: {before}"
    raw = _compose(config, mid, to, subject, text, reply_to, automatic=automatic)
    call.count()
    refused = submit(config, call.token, raw, config.address, to)
    filed = False
    if config.file_sent:
        call.count()
        try:
            with imap(config, call.token) as session:
                session.append(config.sent, raw)
            filed = True
        except TargetError:
            # Sent and not filed: the window ADR-0111 bounds. The result says so.
            filed = False
    output = {"message_id": mid, "to": to, "subject": subject, "refused": refused, "filed": filed}
    return output, _effect(mid, raw, replayed=False)


def _effect(mid: str, raw: bytes, *, replayed: bool) -> Json:
    return {
        "kind": "delivery",
        "replayed": replayed,
        "records": [{"kind": "mail.message", "id": mid}],
        "content_digest": digest_of(raw),
    }


def _text(input: Json) -> str:
    text = input.get("text")
    if not isinstance(text, str) or not text or len(text) > MAX_TEXT:
        raise invalid(f"text must be a text of 1 to {MAX_TEXT} characters")
    return text


async def send(config: Config, call: Call, input: Json) -> Outcome:
    to = _addresses(input.get("to"))
    subject = _line(input.get("subject"), "subject")
    text = _text(input)
    reply_to = input.get("in_reply_to")
    reply_to = message_id(reply_to, "in_reply_to") if reply_to is not None else None
    output, effect = await asyncio.to_thread(
        _send_sync, config, call, to, subject, text, reply_to, automatic=False
    )
    return Outcome(output=output, effect=effect)


async def reply(config: Config, call: Call, input: Json) -> Outcome:
    to = _addresses(input.get("address"))
    thread = input.get("thread")
    thread = message_id(thread, "thread") if thread else None
    text = _text(input)
    output, effect = await asyncio.to_thread(
        _send_sync, config, call, to, None, text, thread, automatic=True
    )
    return Outcome(output=output, effect=effect)


OPERATIONS = {
    "mail.messages.read": read,
    "mail.messages.send": send,
    "channel.mail.reply": reply,
}
