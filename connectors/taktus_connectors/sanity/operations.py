"""How the Sanity HTTP API is asked, and its answers read (`website.posts`).

Every request goes to `--target` under `/<api version>/data/`, against one dataset,
authenticated as the API documents it: `Authorization: Bearer` and the requesting identity's
token. The token is never one of the connector's own.

**A post is a document, and its draft another.** A document's draft is the document whose
identifier is the published one's with the prefix `drafts.`; the Studio edits the draft and
publishing replaces the published document with it. A post the connector drafts is the draft
document `drafts.taktus-<digest>` of the post type, nothing published.

**The mark of a draft.** The post's identifier is `taktus-` and the first 24 hexadecimal digits
of the SHA-256 of the idempotency key; the key itself never leaves Taktus. Before creating, the
connector asks for the published document and its draft by that identifier: either found is
the original, and nothing is created again. The draft is created by `createIfNotExists`, which
leaves a document already there as it is, so two repeats at once create one draft.

**The mark of publishing.** A post with a draft is published by the action
`sanity.action.document.publish`, locked on the revision of the draft as read: a draft a person
changed in between is refused, `conflict`. A post published with no draft left is not
published again: its state is its own mark. Weaker than a key, and stated so.

How the API's answers map to the contract's causes (the API documents no error body, so only
the status is read):

| Answer | Cause |
|---|---|
| 400: a request the API refuses | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the token may not do this | `forbidden` |
| 404: no such dataset, or no such draft to publish | `not_found` |
| 409: the draft changed since it was read | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from taktus_connectors.sanity.portable import blocks
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

API_VERSION = "v2025-02-19"
"""The API's dated version this connector was written against; actions need v2024-05-23."""
DRAFTS = "drafts."
TITLE = 300
CONTENT = 500_000
IDENTIFIER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,127}$")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
DATASET = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VERSIONED = re.compile(r"^v(1|\d{4}-\d{2}-\d{2})$")
PUBLISH = "sanity.action.document.publish"


@dataclass(frozen=True)
class Fields:
    """The fields of the post type the connector writes, as the tenant's schema names them."""

    title: str = "title"
    slug: str = "slug"
    body: str = "body"
    excerpt: str = "excerpt"


@dataclass(frozen=True)
class Config:
    target: str
    """The project's API address, `https://<project id>.api.sanity.io`."""
    dataset: str = "production"
    api_version: str = API_VERSION
    type: str = "post"
    studio: str = ""
    """The Studio's address; a post's link opens it there. Empty: a post has no link."""
    fields: Fields = field(default_factory=Fields)
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if VERSIONED.match(self.api_version) is None:
            raise ValueError("the API version is `v` and a date, YYYY-MM-DD")
        if DATASET.match(self.dataset) is None:
            raise ValueError(f"{self.dataset!r} is no dataset's name")
        if TYPE.match(self.type) is None:
            raise ValueError(f"{self.type!r} is no document type's name")
        for name in vars(self.fields).values():
            if NAME.match(name) is None:
                raise ValueError(f"{name!r} is no field's name")

    def path(self, endpoint: str) -> str:
        return f"/{self.api_version}/data/{endpoint}/{self.dataset}"

    def link(self, identifier: str) -> str:
        if not self.studio:
            return ""
        return f"{self.studio.rstrip('/')}/intent/edit/id={identifier};type={self.type}"


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def mark(key: str) -> str:
    """The post's identifier and slug: a digest of the key, never the key."""
    return "taktus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


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
                path,
                headers={"Authorization": f"Bearer {call.token}", "Accept": "application/json"},
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
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
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
        raise invalid("the API refused the request: 400")
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the API does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the token may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such dataset, or no such draft")
    if status == 409:
        raise TargetError("conflict", "none", False, "the post changed since it was read")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}, which the connector does not foresee")


def _identifier(input: Json) -> str:
    value = input.get("id")
    if not isinstance(value, str) or IDENTIFIER.match(value) is None:
        raise invalid(
            "id must be a post's published identifier: letters, digits, dashes, underscores"
        )
    return value


def _text(input: Json, name: str, limit: int, *, required: bool = True) -> str | None:
    value = input.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise invalid(f"{name} must be text of at most {limit} characters")
    return value


async def _versions(config: Config, call: Call, identifier: str) -> tuple[Json | None, Json | None]:
    """The published document and its draft, each None where the dataset holds none."""
    found = await _request(
        config, call, "GET", f"{config.path('doc')}/{identifier},{DRAFTS}{identifier}"
    )
    documents = found.get("documents") if isinstance(found, dict) else None
    if not isinstance(documents, list):
        raise _unexpected("the API answered documents in a shape the connector does not know")
    by_id = {d.get("_id"): d for d in documents if isinstance(d, dict)}
    return by_id.get(identifier), by_id.get(f"{DRAFTS}{identifier}")


def _slug(document: Json, config: Config) -> str:
    slug = document.get(config.fields.slug)
    if isinstance(slug, dict):
        return str(slug.get("current") or "")
    return str(slug or "")


def post_output(
    config: Config, identifier: str, published: Json | None, draft: Json | None
) -> Json:
    """What a reading yields of a post: the draft where there is one, else the published."""
    document = draft or published
    if document is None:
        raise TargetError("not_found", "none", False, "no such post in the dataset")
    return {
        "id": identifier,
        "status": "draft" if draft is not None else "publish",
        "title": str(document.get(config.fields.title) or ""),
        "link": config.link(identifier),
        "slug": _slug(document, config),
        "modified": document.get("_updatedAt"),
    }


def _short(post: Json) -> Json:
    return {k: post[k] for k in ("id", "status", "link", "slug")}


def _write(output: Json, kind: str, *, replayed: bool) -> Outcome:
    records = [{"kind": kind, "id": str(output["id"])}]
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    published, draft = await _versions(config, call, identifier)
    output = post_output(config, identifier, published, draft)
    return Outcome(
        {k: output[k] for k in ("id", "status", "title", "link", "modified")}, {"kind": "read"}
    )


async def draft(config: Config, call: Call, input: Json) -> Outcome:
    title = _text(input, "title", TITLE)
    content = _text(input, "content", CONTENT)
    excerpt = _text(input, "excerpt", TITLE * 4, required=False)
    identifier = mark(call.key)
    published, drafted = await _versions(config, call, identifier)
    if published is not None or drafted is not None:
        output = post_output(config, identifier, published, drafted)
        return _write(_short(output), "website.post", replayed=True)
    names = config.fields
    document: Json = {
        "_id": f"{DRAFTS}{identifier}",
        "_type": config.type,
        names.title: title,
        names.slug: {"_type": "slug", "current": identifier},
        names.body: blocks(str(content)),
    }
    if excerpt is not None:
        document[names.excerpt] = excerpt
    answered = await _request(
        config,
        call,
        "POST",
        config.path("mutate"),
        params={"returnIds": "true", "visibility": "sync"},
        body={"mutations": [{"createIfNotExists": document}]},
    )
    if not isinstance(answered, dict) or not isinstance(answered.get("transactionId"), str):
        raise TargetError("unknown", "unknown", False, "the API answered the draft unreadably")
    output = {
        "id": identifier,
        "status": "draft",
        "link": config.link(identifier),
        "slug": identifier,
    }
    return _write(output, "website.post", replayed=False)


async def publish(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    published, drafted = await _versions(config, call, identifier)
    before = post_output(config, identifier, published, drafted)
    if drafted is None:
        return _write(_short(before), "website.publish", replayed=True)
    action: Json = {
        "actionType": PUBLISH,
        "publishedId": identifier,
        "versionId": f"{DRAFTS}{identifier}",
    }
    if isinstance(drafted.get("_rev"), str):
        action["ifVersionRevisionId"] = drafted["_rev"]
    answered = await _request(
        config, call, "POST", config.path("actions"), body={"actions": [action]}
    )
    if not isinstance(answered, dict) or not isinstance(answered.get("transactionId"), str):
        raise TargetError("unknown", "unknown", False, "the API answered the publish unreadably")
    return _write({**_short(before), "status": "publish"}, "website.publish", replayed=False)


OPERATIONS = {
    "website.posts.read": read,
    "website.posts.draft": draft,
    "website.posts.publish": publish,
}
