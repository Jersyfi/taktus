"""Intake: a signed webhook delivery becomes an intake command, or is refused.

A function from the delivery — headers, raw body, the moment it arrived — and the intake secret
to an `IntakeResult` (`Connector.json#/$defs/IntakeResult`). The transport that received the
delivery is not here; the MCP tool in `server.py` and the tests call this directly.

The order is the contract's: the signature is verified over the raw bytes before the body is
read, so that nothing unsigned or wrongly signed is ever parsed, let alone acted on. Then the
event is normalised as far as the channel can: who caused it as the service names them (the
numeric account, never the login), what was said, the issue or pull request it concerns, and
where the reply goes — a comment on the same issue or pull request. An event caused by one of
this connector's own earlier actions carries the connector's mark, and is refused so that a
reply is never answered.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from taktus.adapters.driven.connectors.github.declaration import CHANNEL, INTAKE_CREDENTIAL
from taktus.adapters.driven.connectors.github.operations import mark_of

type Json = dict[str, Any]

SIGNATURE_HEADER = "x-hub-signature-256"
SIGNATURE_PREFIX = "sha256="
EVENT_HEADER = "x-github-event"
DELIVERY_HEADER = "x-github-delivery"

# (service event, action) -> the event kind the declaration lists.
EVENTS: Mapping[tuple[str, str], str] = {
    ("issues", "opened"): "issues.opened",
    ("issue_comment", "created"): "issue_comment.created",
    ("pull_request", "opened"): "pull_request.opened",
    ("workflow_run", "completed"): "pipeline_run.completed",
}


class Malformed(Exception):
    """The body is not a delivery this connector can read."""


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def signature_of(body: bytes, secret: str) -> str:
    return SIGNATURE_PREFIX + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(headers: Mapping[str, str], body: bytes, secret: str | None) -> Json | None:
    """None when the delivery is signed with the secret; otherwise the refusal."""
    given = headers.get(SIGNATURE_HEADER, "")
    if not given:
        return refused("unsigned", f"no {SIGNATURE_HEADER} header")
    if not secret:
        return refused(
            "bad_signature",
            f"no intake secret is available under {INTAKE_CREDENTIAL}; nothing can be verified",
        )
    if not hmac.compare_digest(given.strip(), signature_of(body, secret)):
        return refused("bad_signature", f"{SIGNATURE_HEADER} does not verify against the secret")
    return None


def normalise(headers: Mapping[str, str], body: str, received_at: str, secret: str | None) -> Json:
    """The whole of intake: verify, read, refuse or accept."""
    lowered = {name.lower(): value for name, value in headers.items()}
    raw = body.encode("utf-8")
    refusal = verify(lowered, raw, secret)
    if refusal is not None:
        return refusal
    try:
        payload = json.loads(raw)
    except ValueError as error:
        return refused("malformed", f"the body is not JSON: {error}")
    if not isinstance(payload, dict):
        return refused("malformed", "the body is not an object")
    kind = EVENTS.get((lowered.get(EVENT_HEADER, ""), str(payload.get("action", ""))))
    if kind is None:
        return refused(
            "unsupported_event",
            f"{lowered.get(EVENT_HEADER) or 'no'} event with action "
            f"{payload.get('action')!r} is not one this connector normalises",
        )
    delivery = lowered.get(DELIVERY_HEADER, "")
    if not delivery:
        return refused("malformed", f"no {DELIVERY_HEADER} header")
    try:
        intake = _intake(kind, delivery, payload, received_at)
    except Malformed as error:
        return refused("malformed", str(error))
    if intake is None:
        return refused("own_action", "the record carries this connector's own mark")
    return {"accepted": intake}


# --- normalisation per event --------------------------------------------------------------------


def _field(container: Any, *path: str) -> Any:
    node = container
    for name in path:
        if not isinstance(node, dict) or name not in node:
            raise Malformed(f"the delivery has no {'.'.join(path)}")
        node = node[name]
    return node


def _sender(payload: Json) -> Json:
    sender = _field(payload, "sender")
    account = _field(sender, "id")
    kind = "automation" if str(sender.get("type", "")).lower() == "bot" else "person"
    return {"account": str(account), "kind": kind}


def _intake(kind: str, delivery: str, payload: Json, received_at: str) -> Json | None:
    repository = str(_field(payload, "repository", "full_name"))
    sender = _sender(payload)
    context: Json = {"repository": repository, "event": kind}
    if kind == "issue_comment.created":
        comment = _field(payload, "comment")
        issue = _field(payload, "issue")
        text = str(comment.get("body") or "")
        if mark_of(text) is not None:
            return None
        number = str(_field(issue, "number"))
        context.update(
            {
                "issue": number,
                "comment": str(_field(comment, "id")),
                "is_pull_request": "pull_request" in issue,
            }
        )
        reply_to = {
            "channel": CHANNEL,
            "address": f"{repository}#{number}",
            "thread": context["comment"],
        }
        occurred = str(comment.get("created_at") or received_at)
    elif kind == "issues.opened":
        issue = _field(payload, "issue")
        text = _text(issue)
        if mark_of(str(issue.get("body") or "")) is not None:
            return None
        number = str(_field(issue, "number"))
        context["issue"] = number
        reply_to = {"channel": CHANNEL, "address": f"{repository}#{number}"}
        occurred = str(issue.get("created_at") or received_at)
    elif kind == "pull_request.opened":
        pull = _field(payload, "pull_request")
        text = _text(pull)
        if mark_of(str(pull.get("body") or "")) is not None:
            return None
        number = str(_field(pull, "number"))
        context.update(
            {
                "pull_request": number,
                "head": str(_field(pull, "head", "ref")),
                "base": str(_field(pull, "base", "ref")),
            }
        )
        reply_to = {"channel": CHANNEL, "address": f"{repository}#{number}"}
        occurred = str(pull.get("created_at") or received_at)
    else:  # pipeline_run.completed
        run = _field(payload, "workflow_run")
        text = f"{run.get('name', 'pipeline')}: {run.get('conclusion', 'completed')}"
        context.update(
            {
                "run": str(_field(run, "id")),
                "conclusion": str(run.get("conclusion") or ""),
                "head": str(run.get("head_branch") or ""),
            }
        )
        pulls = run.get("pull_requests") or []
        address = repository
        if pulls and isinstance(pulls[0], dict) and "number" in pulls[0]:
            context["pull_request"] = str(pulls[0]["number"])
            address = f"{repository}#{pulls[0]['number']}"
        reply_to = {"channel": CHANNEL, "address": address}
        occurred = str(run.get("updated_at") or received_at)
    return {
        "event_id": delivery,
        "event": kind,
        "channel": CHANNEL,
        "sender": sender,
        "intent": {"raw": text},
        "context": context,
        "reply_to": reply_to,
        "occurred_at": occurred,
    }


def _text(record: Json) -> str:
    title = str(record.get("title") or "")
    body = str(record.get("body") or "")
    return f"{title}\n\n{body}".strip() if body else title
