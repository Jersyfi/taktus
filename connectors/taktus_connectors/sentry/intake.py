"""Intake: the error tracker's webhook for a new issue becomes an intake command, or is refused
(ADR-0331).

An integration of the error tracker sends a webhook for every new issue, the resource `issue`
with the action `created`. It signs the raw body: `Sentry-Hook-Signature` is the HMAC-SHA256 of
the body, keyed with the integration's client secret, in lowercase hexadecimal, without a
prefix. That is the contract's scheme `hmac-sha256`. The signature is verified before the body
is read. The scheme has no moment, so a captured delivery can be replayed; the event's
identifier makes a replay one event, not a second run (below).

**De-duplicated by the issue.** The event's identifier is `error:<issue id>`: a redelivery, and
a second `created` delivery of the same issue, carry the same one, and the intake keeps one
event (`components/command`, ADR-0048 §4). The context names the issue as `error`, its project's
slug as `project`, and its link where the payload gives one as `link`.

The sender is the integration's installation, `installation.uuid`, an automation: the tracker
names no person who created an issue, and the intake copies none (principle 14). The event
carries no text: what the issue says is read by `errors.issues.read`. Refused:

- a delivery of another resource or action, as `unsupported_event`;
- a body without an issue identifier, a project or an installation, as `malformed`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from taktus_connectors.sentry.declaration import CAPABILITY

type Json = dict[str, Any]

SIGNATURE_HEADER = "sentry-hook-signature"
RESOURCE_HEADER = "sentry-hook-resource"
EVENT = "error.created"


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def signature_of(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def signed(body: str, secret: str) -> dict[str, str]:
    """The header the tracker writes for `body`: what the faults and the tests sign with."""
    return {SIGNATURE_HEADER: signature_of(body.encode("utf-8"), secret)}


def normalise(headers: Mapping[str, str], body: str, received_at: str, secret: str | None) -> Json:
    """The whole of intake: verify, read, refuse or accept."""
    lowered = {name.lower(): value for name, value in headers.items()}
    given = lowered.get(SIGNATURE_HEADER, "").strip()
    if not given:
        return refused("unsigned", f"no {SIGNATURE_HEADER} header")
    if not secret:
        return refused("bad_signature", "no intake secret is available; nothing can be verified")
    if not hmac.compare_digest(given.lower(), signature_of(body.encode("utf-8"), secret)):
        return refused("bad_signature", f"{SIGNATURE_HEADER} does not verify against the secret")
    try:
        payload = json.loads(body)
    except ValueError:
        return refused("malformed", "the body is not JSON")
    if not isinstance(payload, dict):
        return refused("malformed", "the body is not an object")
    resource = lowered.get(RESOURCE_HEADER, "").strip()
    action = payload.get("action")
    if resource != "issue" or action != "created":
        return refused(
            "unsupported_event",
            f"a delivery of {resource or 'no resource'} {action!r} is not a new issue",
        )
    data = payload.get("data")
    issue = data.get("issue") if isinstance(data, dict) else None
    if not isinstance(issue, dict):
        return refused("malformed", "the delivery names no issue")
    number = issue.get("id")
    if isinstance(number, int) and not isinstance(number, bool):
        number = str(number)
    project = issue.get("project")
    slug = project.get("slug") if isinstance(project, dict) else None
    installation = payload.get("installation")
    account = installation.get("uuid") if isinstance(installation, dict) else None
    if not isinstance(number, str) or not number.isdigit():
        return refused("malformed", "the issue has no numeric identifier")
    if not isinstance(slug, str) or not slug:
        return refused("malformed", "the issue names no project")
    if not isinstance(account, str) or not account:
        return refused("malformed", "the delivery names no installation")
    context: Json = {"project": slug, "error": number}
    link = issue.get("web_url") or issue.get("permalink")
    if isinstance(link, str) and link.startswith("https://"):
        context["link"] = link
    first = issue.get("firstSeen")
    return {
        "accepted": {
            "event_id": f"error:{number}",
            "event": EVENT,
            "channel": CAPABILITY,
            "sender": {"account": account, "kind": "automation"},
            "intent": {"raw": EVENT, "authored": False},
            "context": context,
            "reply_to": {"channel": CAPABILITY, "address": account},
            "occurred_at": first if isinstance(first, str) and first else received_at,
        }
    }
