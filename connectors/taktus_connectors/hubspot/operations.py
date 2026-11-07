"""How the contacts are asked and their answers read (ADR-0209).

The CRM API v3 at `--target`, with the requesting identity's private app token as a bearer
token. The connector asks:

- `POST /crm/v3/objects/contacts/search` for the contacts that carry an address: two filter
  groups, OR-ed — `email` `EQ` the address, and `hs_additional_emails` `CONTAINS_TOKEN` it —
  the properties `email`, `createdate`, `lastmodifieddate`, `lifecyclestage`, sorted by
  `createdate` ascending, in pages of 100 followed by `paging.next.after`, up to 10 pages.
  Filter values are compared without regard to case, as the search guide states.
- `POST /crm/v3/objects/contacts` to create one, with the property `email` alone.
- `POST /crm/v3/objects/notes/search` for the notes associated with a contact, by the
  pseudo-property `associations.contact` `EQ` its id, with `hs_note_body`.
- `POST /crm/v3/objects/notes` for a note, with `hs_timestamp` and `hs_note_body`, associated
  with the contact by the type the system defines for a note to a contact, 202.

A contact is reduced to `{id, email, created_at, updated_at, lifecycle_stage}`. Its name, phone,
company, owner and every other property are never asked: what is not read cannot leak, and no
step needs them.

**Scoped.** Every operation names one address. A call that serves a case carries its subject;
an address other than the subject is refused as `out_of_scope` before the system is asked
(ADR-0130). Addresses are compared lower-cased.

**The marks.** A contact is marked by its address: a create that finds a contact carrying the
address creates none and answers it as replayed. A note's last line is `Taktus reference:
<idempotency key>`; a note of the contact that carries the line is the original.

| Answer | Cause |
|---|---|
| 400: a request the system refuses (`VALIDATION_ERROR`) | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the token's scopes do not cover the request | `forbidden` |
| 404: an object the system does not know | `not_found` |
| 409: a contact with the address was created meanwhile | `conflict` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable |
| a write timed out or answered unreadably | `unknown`, effect `unknown`; a repeat finds the mark |
| any other status, a body that is not the API's | `unexpected` |

Only the error's `category` is reported; its `message` stays out of `detail`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from taktus_connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    out_of_scope,
    unavailable,
)

type Json = dict[str, Any]

TARGET = "https://api.hubapi.com"
PAGE = 100
MAX_PAGES = 10
MAX_TEXT = 20_000
NOTE_TO_CONTACT = 202
PROPERTIES = ["email", "createdate", "lastmodifieddate", "lifecyclestage"]
EMAIL = re.compile(r"^[^@\s<>\"';]{1,64}@[^@\s<>\"';]{1,253}\.[^@\s<>\"';]{2,63}$")
MARK = "Taktus reference: "


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the product's own, or a fake's."""
    timeout: float = 30.0


def _obj(value: Any) -> Json:
    """The value when it is an object, else an empty one."""
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str | None:
    """The value when it is a text, else None."""
    return value if isinstance(value, str) else None


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _category(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    category = body.get("category") if isinstance(body, dict) else None
    return category if isinstance(category, str) else ""


async def _post(config: Config, call: Call, path: str, body: Json, *, writing: bool) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}", "Accept": "application/json"},
        ) as client:
            response = await client.post(path, json=body)
    except httpx.ConnectError as error:
        raise unavailable(f"the system could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the system did not answer the write in time"
            ) from error
        raise unavailable(f"the system did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the system could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            if writing:
                raise TargetError("unknown", "unknown", False, "the system answered unreadably")
            raise _unexpected("the system answered with a body it does not use")
        return answer
    category = _category(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the system does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the token's scopes do not cover this")
    if status == 404:
        raise TargetError("not_found", "none", False, "the system knows no such object")
    if status == 409:
        raise TargetError("conflict", "none", False, f"the system answered 409 {category}".rstrip())
    if status == 429 or status >= 500:
        raise unavailable(f"the system answered {status} {category}".rstrip())
    if status == 400:
        raise invalid(f"the system refused the request: {category}".rstrip(": "))
    raise _unexpected(f"the system answered {status} {category}".rstrip())


def _email(call: Call, input: Json) -> str:
    value = input.get("email")
    if not isinstance(value, str) or EMAIL.match(value.strip()) is None:
        raise invalid("email must be one e-mail address")
    address = value.strip().lower()
    if call.scope is not None and address != call.scope.strip().lower():
        raise out_of_scope("the address is not the subject of the case this call serves")
    return address


def _contact(record: Any) -> Json:
    if not isinstance(record, dict) or not isinstance(record.get("id"), str):
        raise _unexpected("a contact has no identifier")
    properties = _obj(record.get("properties"))
    email = properties.get("email")
    return {
        "id": record["id"],
        "email": email.lower() if isinstance(email, str) else None,
        "created_at": record.get("createdAt") or properties.get("createdate"),
        "updated_at": record.get("updatedAt") or properties.get("lastmodifieddate"),
        "lifecycle_stage": properties.get("lifecyclestage"),
    }


async def _search(
    config: Config, call: Call, path: str, groups: list[Json], properties: list[str]
) -> list[Json]:
    found: list[Json] = []
    after: str | None = None
    for _ in range(MAX_PAGES):
        body: Json = {
            "filterGroups": groups,
            "properties": properties,
            "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
            "limit": PAGE,
        }
        if after is not None:
            body["after"] = after
        page = await _post(config, call, path, body, writing=False)
        results = page.get("results")
        if not isinstance(results, list):
            raise _unexpected("the answer is not a page of results")
        found.extend(results)
        paging = _obj(page.get("paging"))
        following = _obj(paging.get("next"))
        after = _str(following.get("after"))
        if after is None or not results:
            return found
    return found


async def _carrying(config: Config, call: Call, address: str) -> list[Json]:
    groups = [
        {"filters": [{"propertyName": "email", "operator": "EQ", "value": address}]},
        {
            "filters": [
                {
                    "propertyName": "hs_additional_emails",
                    "operator": "CONTAINS_TOKEN",
                    "value": address,
                }
            ]
        },
    ]
    records = await _search(config, call, "/crm/v3/objects/contacts/search", groups, PROPERTIES)
    contacts = [_contact(record) for record in records]
    return sorted(contacts, key=lambda c: (str(c["created_at"] or ""), c["id"]))


async def find(config: Config, call: Call, input: Json) -> Outcome:
    address = _email(call, input)
    contacts = await _carrying(config, call, address)
    output = {"email": address, "contacts": contacts, "count": len(contacts)}
    return Outcome(output=output, effect={"kind": "read"})


async def create(config: Config, call: Call, input: Json) -> Outcome:
    address = _email(call, input)
    existing = await _carrying(config, call, address)
    if existing:
        return _written(existing[0], "crm.contact", existing[0]["id"], replayed=True)
    made = await _post(
        config, call, "/crm/v3/objects/contacts", {"properties": {"email": address}}, writing=True
    )
    contact = _contact(made)
    return _written(contact, "crm.contact", contact["id"], replayed=False)


async def note(config: Config, call: Call, input: Json) -> Outcome:
    address = _email(call, input)
    text = input.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise invalid(f"text must be the note, 1 to {MAX_TEXT} characters")
    contacts = await _carrying(config, call, address)
    if not contacts:
        raise TargetError("not_found", "none", False, "no contact carries the address")
    contact = contacts[0]["id"]
    groups = [{"filters": [{"propertyName": "associations.contact", "operator": "EQ",
                            "value": contact}]}]  # fmt: skip
    notes = await _search(config, call, "/crm/v3/objects/notes/search", groups, ["hs_note_body"])
    for found in notes:
        properties = found.get("properties") if isinstance(found, dict) else None
        body = properties.get("hs_note_body") if isinstance(properties, dict) else None
        if isinstance(body, str) and f"{MARK}{call.key}" in body:
            return _written(
                {"contact": contact, "note": str(found.get("id"))},
                "crm.note",
                str(found.get("id")),
                replayed=True,
            )
    stamp = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    made = await _post(
        config,
        call,
        "/crm/v3/objects/notes",
        {
            "properties": {
                "hs_timestamp": stamp,
                "hs_note_body": f"{text.rstrip()}\n\n{MARK}{call.key}",
            },
            "associations": [
                {
                    "to": {"id": contact},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": NOTE_TO_CONTACT,
                        }
                    ],
                }
            ],
        },
        writing=True,
    )
    if not isinstance(made.get("id"), str):
        raise TargetError("unknown", "unknown", False, "the system did not name the note")
    return _written(
        {"contact": contact, "note": made["id"]}, "crm.note", made["id"], replayed=False
    )


def _written(output: Json, kind: str, identifier: str, *, replayed: bool) -> Outcome:
    return Outcome(
        output=output,
        effect={
            "kind": "write",
            "replayed": replayed,
            "records": [{"kind": kind, "id": identifier}],
        },
    )


OPERATIONS = {
    "crm.contacts.find": find,
    "crm.contacts.create": create,
    "crm.contacts.note": note,
}
