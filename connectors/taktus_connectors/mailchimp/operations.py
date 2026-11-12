"""How the Marketing API is asked, and its answers read.

Every request goes to `--target` under `/3.0/`, authenticated as the API documents it: HTTP
Basic, any user name, the requesting identity's API key as the password. The key is never one
of the connector's own.

**The mark of a draft.** A campaign has an internal title the recipients never see
(`settings.title`). A draft is created with the title `taktus-` and the first 24 hexadecimal
digits of the SHA-256 of the idempotency key; the key itself never leaves Taktus. Before
creating, the connector lists the audience's campaigns and looks for that title: one found is
the original, and nothing is created again. A connector stopped between the creation and its
answer creates nothing twice.

**The mark of a send.** A campaign that is scheduled, sending or sent is not sent again: its
status is its own mark. Weaker than a key, and stated so: a repeat after somebody else sent the
campaign reports replayed too.

**No recipient leaves the service.** Every output names the audience by its identifier and its
size; the API's own fields that could carry an address are never read into an output.

How the API's answers map to the contract's causes (its error body is `type`, `title`,
`status`, `detail`, `instance`; only `title` is passed on):

| Answer | Cause |
|---|---|
| 400: a request the API refuses, a campaign not ready to send | `invalid` |
| 401: the key is invalid or disabled | `unauthenticated` |
| 403: the key's user may not do this | `forbidden` |
| 404: no such campaign or audience | `not_found` |
| 405: the campaign's state does not allow the action | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
ADDRESS = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
SUBJECT = 150
NAME = 100
TEXT = 200_000
PAGE = 1000
PAGES = 10
SENT = frozenset({"schedule", "sending", "sent"})
FIELDS = "id,web_id,status,type,emails_sent,send_time,recipients.list_id,recipients.recipient_count"


@dataclass(frozen=True)
class Config:
    target: str
    """The account's API address, `https://<data centre>.api.mailchimp.com`."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def mark(key: str) -> str:
    """The draft's internal title: a digest of the key, never the key."""
    return "taktus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _title(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    title = body.get("title") if isinstance(body, dict) else None
    return str(title)[:100] if isinstance(title, str) else ""


async def _request(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    body: Json | None = None,
    params: Json | None = None,
) -> Any:
    writing = method != "GET"
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(
                method,
                f"/3.0/{path}",
                auth=("taktus", call.token),
                headers={"Accept": "application/json"},
                params=params,
                json=body,
            )
    except httpx.ConnectError as error:
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the API did not answer the write in time"
            ) from error
        raise unavailable(f"the API did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the key among it.
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 204:
        return None
    if status == 200:
        try:
            return response.json()
        except ValueError as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the API answered the write unreadably"
                ) from error
            raise _unexpected("the API answered with a body that is not JSON") from error
    if status == 400:
        raise invalid(f"the API refused the request: {_title(response) or status}")
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the API does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key's user may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such campaign or audience")
    if status == 405:
        raise TargetError(
            "conflict", "none", False, "the campaign's state does not allow the action"
        )
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}, which the connector does not foresee")


def _identifier(input: Json, field: str) -> str:
    value = input.get(field)
    if not isinstance(value, str) or IDENTIFIER.match(value) is None:
        raise invalid(f"{field} must be an identifier: letters, digits, dashes, underscores")
    return value


def _text(input: Json, field: str, limit: int, *, required: bool = True) -> str | None:
    value = input.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise invalid(f"{field} must be text of at most {limit} characters")
    return value


def campaign_output(found: Any) -> Json:
    """What a reading yields of a campaign: never a recipient."""
    if not isinstance(found, dict) or not isinstance(found.get("id"), str):
        raise _unexpected("the API answered a campaign in a shape the connector does not know")
    recipients = found.get("recipients") or {}
    count = recipients.get("recipient_count") if isinstance(recipients, dict) else None
    return {
        "id": found["id"],
        "web_id": found.get("web_id"),
        "status": str(found.get("status", "")),
        "list": recipients.get("list_id") if isinstance(recipients, dict) else None,
        "recipients": count if isinstance(count, int) else None,
        "emails_sent": found.get("emails_sent")
        if isinstance(found.get("emails_sent"), int)
        else None,
        "send_time": found.get("send_time") or None,
    }


async def _campaign(config: Config, call: Call, identifier: str) -> Json:
    found = await _request(
        config, call, "GET", f"campaigns/{identifier}", params={"fields": FIELDS}
    )
    return campaign_output(found)


async def _marked(config: Config, call: Call, audience: str, title: str) -> Json | None:
    """The audience's campaign whose internal title is the mark, or None."""
    for page in range(PAGES):
        listed = await _request(
            config,
            call,
            "GET",
            "campaigns",
            params={
                "list_id": audience,
                "count": PAGE,
                "offset": page * PAGE,
                "fields": "total_items,campaigns.id,campaigns.settings.title",
            },
        )
        campaigns = listed.get("campaigns") if isinstance(listed, dict) else None
        if not isinstance(campaigns, list):
            raise _unexpected("the API's list of campaigns is not a list")
        for found in campaigns:
            if isinstance(found, dict) and (found.get("settings") or {}).get("title") == title:
                return dict(found)
        total = listed.get("total_items")
        if not campaigns or not isinstance(total, int) or (page + 1) * PAGE >= total:
            return None
    raise unavailable(f"the audience holds more than {PAGES * PAGE} campaigns to look through")


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
    return Outcome(await _campaign(config, call, _identifier(input, "id")), {"kind": "read"})


async def draft(config: Config, call: Call, input: Json) -> Outcome:
    audience = _identifier(input, "list")
    subject = _text(input, "subject", SUBJECT)
    text = _text(input, "text", TEXT)
    given_html = _text(input, "html", TEXT, required=False)
    sender = _text(input, "from_name", NAME)
    reply_to = input.get("reply_to")
    if not isinstance(reply_to, str) or ADDRESS.match(reply_to) is None:
        raise invalid("reply_to must be a mail address")
    title = mark(call.key)
    found = await _marked(config, call, audience, title)
    if found is not None:
        return _write(
            await _campaign(config, call, str(found["id"])), "newsletter.campaign", replayed=True
        )
    created = await _request(
        config,
        call,
        "POST",
        "campaigns",
        body={
            "type": "regular",
            "recipients": {"list_id": audience},
            "settings": {
                "subject_line": subject,
                "title": title,
                "from_name": sender,
                "reply_to": reply_to,
            },
        },
    )
    output = campaign_output(created)
    await _request(
        config,
        call,
        "PUT",
        f"campaigns/{output['id']}/content",
        body={"plain_text": text, "html": given_html or _html(str(text))},
    )
    return _write(output, "newsletter.campaign", replayed=False)


async def send(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input, "id")
    before = await _campaign(config, call, identifier)
    if before["status"] in SENT:
        return _write(before, "newsletter.send", replayed=True)
    await _request(config, call, "POST", f"campaigns/{identifier}/actions/send")
    # The API answers 204 and starts sending; the campaign is not read again, so that a reading
    # that fails after the send cannot report a send that happened as one that did not.
    return _write({**before, "status": "sending"}, "newsletter.send", replayed=False)


OPERATIONS = {
    "newsletter.broadcasts.read": read,
    "newsletter.broadcasts.draft": draft,
    "newsletter.broadcasts.send": send,
}
