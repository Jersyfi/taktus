"""How the inbox is asked and a document read.

The inbox is one folder served over WebDAV (RFC 4918) at `--target`. A list is
`PROPFIND <folder>` with `Depth: 1`, asking for each member's length, last change and entity tag;
the answer is a `multistatus` the connector reads with the same defused parsing as a document.
A read is `GET <folder><document>`, the document named by its file name in the folder and
nothing else: a name with a slash, a backslash or a leading dot is refused before anything is
asked, so that a call cannot reach outside the folder.

The requesting identity's credential is sent as HTTP authentication: a value of the form
`user:password` as basic authentication, any other as a bearer token.

How the server's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404: a refused request or a missing document; a document that is no invoice | `invalid` |
| 401: the credential is not admitted | `unauthenticated` |
| 403: the credential may not read the folder | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not WebDAV's | `unexpected` |
"""

from __future__ import annotations

import base64
import hashlib
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx

from taktus_connectors.einvoice import standard
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

LIMIT = 100
MAX_LIMIT = 1000
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,199}$")
DAV = "DAV:"
PROPFIND = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<d:propfind xmlns:d="DAV:"><d:prop>'
    b"<d:getcontentlength/><d:getlastmodified/><d:getetag/><d:resourcetype/>"
    b"</d:prop></d:propfind>"
)


@dataclass(frozen=True)
class Config:
    target: str
    """The inbox folder's WebDAV address."""
    timeout: float = 30.0

    @property
    def folder(self) -> str:
        return self.target if self.target.endswith("/") else self.target + "/"


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _authorization(token: str) -> str:
    if ":" in token:
        return "Basic " + base64.b64encode(token.encode("utf-8")).decode("ascii")
    return f"Bearer {token}"


async def _request(
    config: Config, call: Call, method: str, url: str, **kwargs: Any
) -> httpx.Response:
    call.count()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": _authorization(call.token)},
        ) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException as error:
        raise unavailable(f"the inbox did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the inbox could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 207):
        return response
    if status == 401:
        raise TargetError(
            "unauthenticated", "none", False, "the inbox does not admit the credential"
        )
    if status == 403:
        raise TargetError("forbidden", "none", False, "the credential may not read the inbox")
    if status == 429 or status >= 500:
        raise unavailable(f"the inbox answered {status}")
    if status in (400, 404):
        raise invalid(f"the inbox refused the request: {status}")
    raise _unexpected(f"the inbox answered {status}")


def _member(response: ElementTree.Element, folder_path: str) -> Json | None:
    href = response.findtext(f"{{{DAV}}}href")
    if href is None:
        return None
    path = unquote(urlsplit(href.strip()).path)
    if path.rstrip("/") == folder_path.rstrip("/"):
        return None  # the folder itself
    prop = response.find(f"{{{DAV}}}propstat/{{{DAV}}}prop")
    if prop is None:
        return None
    if prop.find(f"{{{DAV}}}resourcetype/{{{DAV}}}collection") is not None:
        return None  # a sub-folder: the inbox is one folder
    length = prop.findtext(f"{{{DAV}}}getcontentlength")
    return {
        "document": path.rstrip("/").rsplit("/", 1)[-1],
        "size": int(length) if length is not None and length.strip().isdigit() else None,
        "modified": (prop.findtext(f"{{{DAV}}}getlastmodified") or "").strip() or None,
        "etag": (prop.findtext(f"{{{DAV}}}getetag") or "").strip() or None,
    }


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    response = await _request(
        config,
        call,
        "PROPFIND",
        config.folder,
        content=PROPFIND,
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    if standard.FORBIDDEN.search(response.content):
        raise _unexpected("the inbox answered with a document type or an entity; refused unparsed")
    try:
        # Defused: a document type or an entity was refused above, before parsing.
        root = ElementTree.fromstring(response.content)  # noqa: S314
    except ElementTree.ParseError as error:
        raise _unexpected("the inbox's answer is not a WebDAV multistatus") from error
    if root.tag != f"{{{DAV}}}multistatus":
        raise _unexpected("the inbox's answer is not a WebDAV multistatus")
    folder_path = urlsplit(config.folder).path
    members = [
        member
        for response_ in root.findall(f"{{{DAV}}}response")
        if (member := _member(response_, folder_path)) is not None
    ]
    members.sort(key=lambda m: (m["modified"] or "", m["document"]))
    output = {"documents": members[:limit], "complete": len(members) <= limit}
    return Outcome(output=output, effect={"kind": "read"})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    name = input.get("document")
    if not isinstance(name, str) or NAME.match(name) is None or ".." in name:
        raise invalid(
            "document must be the name of a file in the inbox folder: letters, digits, dots, "
            "dashes, underscores and spaces, starting with a letter or a digit"
        )
    response = await _request(config, call, "GET", config.folder + name)
    try:
        terms = standard.parse(response.content)
    except standard.NotAnInvoice as error:
        raise invalid(
            f"{name} is not an electronic invoice this connector reads: {error}"
        ) from error
    output = {
        "document": name,
        "digest": "sha256:" + hashlib.sha256(response.content).hexdigest(),
        **terms,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {
    "documents.invoices.list": list_,
    "documents.invoices.read": read,
}
