"""What each operation does, and how a repeat is recognised.

The one outward operation, `chat.threads.post`, is `marked`. The service keeps a structured field
on every message, its metadata: an event type and a payload. The connector writes the
idempotency key there and looks for it **before** posting. The connector keeps no memory of what
it posted; the service does, and that memory survives a restart of the connector — which is the
point (README §4 of the contract). The text of the message carries no mark: a person reads
exactly what was asked to be said.

Where the lookup is exact and where it is bounded is stated. A post into a thread is looked for
among every reply of that thread, page by page, up to `MAX_PAGES` pages. A post at the top of a
conversation is looked for among the `RECENT` most recent messages of it. A repeat that arrives
after more than that many other messages is not recognised; the bound is stated, as the
repository connector states its own.

Every function takes the service, the operation's input and the idempotency key, and returns an
`Outcome`: the operation's output and the effect report. Faults of the service arrive as
`TargetError`. Input the operation cannot use is an `invalid` error before any request is made.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from taktus.adapters.driven.connectors.slack.api import Api, TargetError, digest_of
from taktus.adapters.driven.connectors.slack.declaration import MAX_PAGES

type Json = dict[str, Any]

MARK_TYPE = "taktus_delivery"
"""The event type of the metadata a post carries: the connector's mark."""
RECENT = 100
"""How many of a conversation's most recent messages a top-level post is looked for in."""
PAGE = 200
CONVERSATION = re.compile(r"^[A-Z0-9]{2,64}$")
TS = re.compile(r"^\d{1,12}\.\d{1,9}$")
MAX_TEXT = 40000
"""The longest text the service accepts in one message."""


@dataclass(frozen=True)
class Outcome:
    output: Json
    effect: Json


def invalid(detail: str) -> TargetError:
    return TargetError("invalid", "none", False, detail)


def mark(key: str) -> Json:
    return {"event_type": MARK_TYPE, "event_payload": {"idempotency_key": key}}


def mark_of(message: Json) -> str | None:
    """The key a message carries in its metadata, or None."""
    metadata = message.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("event_type") != MARK_TYPE:
        return None
    payload = metadata.get("event_payload")
    key = payload.get("idempotency_key") if isinstance(payload, dict) else None
    return key if isinstance(key, str) else None


def _conversation(input: Json) -> str:
    value = input.get("address")
    if not isinstance(value, str) or CONVERSATION.match(value) is None:
        raise invalid("address must be the identifier of a conversation")
    return value


def _thread(input: Json) -> str:
    value = input.get("thread")
    if not isinstance(value, str) or TS.match(value) is None:
        raise invalid("thread must be the timestamp of the message that opens the thread")
    return value


def _thread_if_any(input: Json) -> str | None:
    return None if input.get("thread") is None else _thread(input)


def _account(message: Json) -> Json:
    if message.get("bot_id"):
        return {"account": str(message.get("user") or message["bot_id"]), "kind": "automation"}
    return {"account": str(message.get("user", "")), "kind": "person"}


def message_output(message: Json) -> Json:
    return {
        "ts": str(message.get("ts", "")),
        "thread": str(message.get("thread_ts") or message.get("ts", "")),
        "text": str(message.get("text") or ""),
        "author": _account(message),
    }


async def _replies(api: Api, conversation: str, thread: str) -> tuple[list[Json], bool]:
    """Every message of a thread, oldest first, and whether every page was read."""
    found: list[Json] = []
    cursor = ""
    for _ in range(MAX_PAGES):
        params: Json = {
            "channel": conversation,
            "ts": thread,
            "limit": PAGE,
            "include_all_metadata": "true",
        }
        if cursor:
            params["cursor"] = cursor
        page = await api.read("conversations.replies", params)
        found.extend(m for m in page.get("messages") or [] if isinstance(m, dict))
        cursor = str((page.get("response_metadata") or {}).get("next_cursor") or "")
        if not page.get("has_more") or not cursor:
            return found, True
    return found, False


# --- reads ------------------------------------------------------------------------------------


async def read_thread(api: Api, input: Json, key: str) -> Outcome:
    conversation = _conversation(input)
    thread = _thread(input)
    messages, complete = await _replies(api, conversation, thread)
    output = {
        "address": conversation,
        "thread": thread,
        "messages": [message_output(m) for m in messages],
        "complete": complete,
    }
    return Outcome(output, {"kind": "read"})


# --- deliveries: marked -----------------------------------------------------------------------


async def post_message(api: Api, input: Json, key: str) -> Outcome:
    """Lookup first: in the thread, every reply; at the top of a conversation, the RECENT most
    recent messages. A message that carries the key is ours, replayed. Then one post, with the
    key in the message's metadata."""
    conversation = _conversation(input)
    thread = _thread_if_any(input)
    text = input.get("text")
    if not isinstance(text, str) or not text.strip():
        raise invalid("text must be a non-empty string")
    if len(text) > MAX_TEXT:
        raise invalid(f"text is longer than {MAX_TEXT} characters")
    request: Json = {"channel": conversation, "text": text}
    if thread is not None:
        request["thread_ts"] = thread
    digest = digest_of(request)
    if thread is not None:
        candidates, _ = await _replies(api, conversation, thread)
    else:
        page = await api.read(
            "conversations.history",
            {"channel": conversation, "limit": RECENT, "include_all_metadata": "true"},
        )
        candidates = [m for m in page.get("messages") or [] if isinstance(m, dict)]
    for message in candidates:
        if mark_of(message) == key:
            return _delivered(conversation, message, digest, replayed=True)
    posted = await api.write("chat.postMessage", {**request, "metadata": mark(key)})
    answered = posted.get("message")
    sent: Json = dict(answered) if isinstance(answered, dict) else {"text": text}
    sent.setdefault("ts", posted.get("ts"))
    if thread is not None:
        sent.setdefault("thread_ts", thread)
    return _delivered(conversation, sent, digest, replayed=False)


def _delivered(conversation: str, message: Json, digest: str, *, replayed: bool) -> Outcome:
    ts = str(message.get("ts", ""))
    if not ts:
        raise TargetError("unavailable", "none", True, "the service named no message")
    output = {"address": conversation, **message_output(message)}
    records = [{"kind": "chat.message", "id": f"{conversation}/{ts}"}]
    effect = {
        "kind": "delivery",
        "replayed": replayed,
        "records": records,
        "content_digest": digest,
    }
    return Outcome(output, effect)


type Operation = Callable[[Api, Json, str], Awaitable[Outcome]]

OPERATIONS: dict[str, Operation] = {
    "chat.threads.read": read_thread,
    "chat.threads.post": post_message,
}
