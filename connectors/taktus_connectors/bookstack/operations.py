"""What each operation does: how a place maps onto the wiki, how a repeat is recognised, and how
a page Taktus wrote keeps the digest of what it wrote.

**A place is three names: shelf, book, page.** The wiki structures pages that way, and a guide's
place in the manifest is a shelf and a book (`docs/guides/guides.yaml`), its pages the third
level. A list takes a place of one, two or three names: a shelf, a book of it, or one page. A
read and a write take exactly three. A name is matched exactly, as written. A place the wiki
cannot hold — more than three names, fewer than the operation needs, an empty name, one with
spaces at either end (the wiki trims them, so it would never match), a control character, or
more than 255 characters — is refused as `invalid` before any request. Two shelves of one name,
two books of one name on a shelf or two pages of one name in a book make a place ambiguous; the
call ends `conflict` and changes nothing. A page inside a chapter has no place, because a place
has no level for a chapter: it is not listed, read or written. Shelves and books are made by a
person in the wiki (NEED-0021); a write into a shelf or book that does not exist ends
`not_found`.

**What is kept beside a page: its tags.** The wiki keeps a list of tags, names and values, on
every page and returns them unchanged. A write puts four kinds there, every name beginning with
`taktus-`: the idempotency key (`taktus-key-N`), the mark (`taktus-mark-N`), the digest of the
text written (`taktus-digest`) and the digest of the text as the wiki stored it
(`taktus-stored`). The key and the mark are split into numbered parts of at most `CHUNK`
characters, each part URL-safe base64, because a tag's value is short and may be trimmed. A
person's own tags on the page are kept as they are.

**The digest of a page Taktus wrote and nobody touched is the digest of what it wrote.** A wiki
may change the text it stores — line endings, spaces at the end of a line, the last newline. The
connector therefore reads the text back from the wiki's answer to the write. Where it differs
from what was written, the digest of the stored text goes into `taktus-stored`, in one more
write of the tags alone. On reading, a page whose stored text still hashes to `taktus-stored`
was not touched since: its digest is `taktus-digest`, the digest of what was written. A page
whose text hashes to anything else was edited, and its digest is that of the text as it stands.
The mark stays what it was, so the page is measured `edited` (ADR-0065 §5). The text of a page
is its Markdown; a page whose Markdown is empty, because a person edited it in the visual editor,
is read as its HTML.

**A write that expects a digest.** The connector reads the page, compares its digest with
`expected`, and writes. The wiki has no conditional write, so this is two moves: a person who
saves the page between the read and the write loses that save. The window is the length of one
request.

**A repeat** is a write whose key the page already carries in its tags, with the digest of the
same text. It writes nothing and answers `replayed`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from taktus_connectors.bookstack.api import Api, TargetError
from taktus_connectors.bookstack.declaration import (
    LIST,
    MAX_BOOKS,
    MAX_LISTINGS,
    MAX_PAGES,
    PAGE,
    READ,
    WRITE,
)

type Json = dict[str, Any]

PREFIX = "taktus-"
KEY = f"{PREFIX}key-"
MARK = f"{PREFIX}mark-"
WRITTEN = f"{PREFIX}digest"
STORED = f"{PREFIX}stored"
CHUNK = 160
"""The longest value of one tag the connector writes."""
MAX_NAME = 255
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
RECORD = "knowledge.page"


@dataclass(frozen=True)
class Outcome:
    output: Json
    effect: Json


def invalid(detail: str) -> TargetError:
    return TargetError("invalid", "none", False, detail)


def conflict(detail: str) -> TargetError:
    return TargetError("conflict", "none", False, detail)


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- the place ----------------------------------------------------------------------------------


def place_of(input: Json, *, shortest: int, longest: int = 3) -> tuple[str, ...]:
    """The place, or `invalid` before any request when the wiki cannot hold it."""
    place = input.get("place")
    if not isinstance(place, list) or not all(isinstance(name, str) for name in place):
        raise invalid("`place` is a list of names: shelf, book, page")
    if not shortest <= len(place) <= longest:
        wanted = "three names" if shortest == 3 else f"{shortest} to {longest} names"
        raise invalid(
            f"`place` has {len(place)} name(s); the wiki holds a place of {wanted}: "
            "shelf, book, page"
        )
    for name in place:
        if not name or name != name.strip():
            raise invalid(f"{name!r} cannot be a name in the wiki: empty, or spaces at an end")
        if CONTROL.search(name) or len(name) > MAX_NAME:
            raise invalid(
                f"{name[:40]!r} cannot be a name in the wiki: a control character, or more "
                f"than {MAX_NAME} characters"
            )
    return tuple(place)


def _one(found: list[Json], what: str) -> Json | None:
    if len(found) > 1:
        raise conflict(f"{len(found)} {what}: the place is ambiguous")
    return found[0] if found else None


async def shelf_named(api: Api, name: str) -> Json | None:
    """The shelf of this name, with its books, or None."""
    listed = await api.get("shelves", {"filter[name]": name, "count": PAGE})
    found = [s for s in listed.get("data") or [] if isinstance(s, dict) and s.get("name") == name]
    shelf = _one(found, f"shelves are named {name!r}")
    if shelf is None:
        return None
    return await api.get(f"shelves/{int(shelf['id'])}")


def books_of(shelf: Json, name: str | None = None) -> list[Json]:
    books = [b for b in shelf.get("books") or [] if isinstance(b, dict)]
    if name is None:
        return books
    found = [b for b in books if b.get("name") == name]
    one = _one(found, f"books on the shelf {shelf.get('name')!r} are named {name!r}")
    return [] if one is None else [one]


async def pages_of(api: Api, book: Json) -> list[Json]:
    """The pages directly in a book — not in a chapter, not a draft — as the wiki lists them."""
    found: list[Json] = []
    for listing in range(MAX_LISTINGS):
        answer = await api.get(
            "pages",
            {"filter[book_id]": int(book["id"]), "count": PAGE, "offset": listing * PAGE},
        )
        data = [p for p in answer.get("data") or [] if isinstance(p, dict)]
        found.extend(data)
        total = answer.get("total")
        if len(data) < PAGE or (isinstance(total, int) and len(found) >= total):
            return [p for p in found if not p.get("chapter_id") and not p.get("draft")]
    raise invalid(
        f"the book {book.get('name')!r} lists more than {MAX_LISTINGS * PAGE} pages; "
        "the connector does not read it"
    )


def page_named(pages: list[Json], book: Json, name: str) -> Json | None:
    found = [p for p in pages if p.get("name") == name]
    return _one(found, f"pages of the book {book.get('name')!r} are named {name!r}")


async def located(api: Api, place: tuple[str, ...]) -> tuple[Json | None, Json | None]:
    """The book and the page entry of a place of three names; None where either is missing."""
    shelf = await shelf_named(api, place[0])
    if shelf is None:
        return None, None
    books = books_of(shelf, place[1])
    if not books:
        return None, None
    book = books[0]
    return book, page_named(await pages_of(api, book), book, place[2])


# --- what is kept beside a page -----------------------------------------------------------------


@dataclass(frozen=True)
class Kept:
    key: str | None
    mark: str | None
    written: str | None
    stored: str | None


def _encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode(value: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _parts(prefix: str, value: str) -> list[Json]:
    encoded = _encode(value)
    chunks = [encoded[i : i + CHUNK] for i in range(0, len(encoded), CHUNK)] or [""]
    return [{"name": f"{prefix}{index}", "value": chunk} for index, chunk in enumerate(chunks)]


def _joined(tags: dict[str, str], prefix: str) -> str | None:
    parts: list[str] = []
    while f"{prefix}{len(parts)}" in tags:
        parts.append(tags[f"{prefix}{len(parts)}"])
    return _decode("".join(parts)) if parts else None


def tags_of(page: Json) -> list[Json]:
    return [
        {"name": str(t.get("name", "")), "value": str(t.get("value") or "")}
        for t in page.get("tags") or []
        if isinstance(t, dict)
    ]


def kept_of(page: Json) -> Kept:
    tags = {t["name"]: t["value"] for t in tags_of(page) if t["name"].startswith(PREFIX)}
    return Kept(
        key=_joined(tags, KEY),
        mark=_joined(tags, MARK),
        written=tags.get(WRITTEN) or None,
        stored=tags.get(STORED) or None,
    )


def ours(key: str, mark: str, written: str, stored: str) -> list[Json]:
    return [
        *_parts(KEY, key),
        *_parts(MARK, mark),
        {"name": WRITTEN, "value": written},
        {"name": STORED, "value": stored},
    ]


def theirs(page: Json | None) -> list[Json]:
    """A person's own tags on the page, kept through every write."""
    if page is None:
        return []
    return [t for t in tags_of(page) if not t["name"].startswith(PREFIX)]


def text_of(page: Json) -> str:
    markdown = page.get("markdown")
    if isinstance(markdown, str) and markdown:
        return markdown
    html = page.get("html")
    return html if isinstance(html, str) else ""


def digest_of(page: Json) -> str:
    """The digest of what was written where the stored text is untouched since; else the
    digest of the text as it stands."""
    actual = digest(text_of(page))
    kept = kept_of(page)
    if kept.written and kept.stored == actual:
        return kept.written
    return actual


# --- the operations -----------------------------------------------------------------------------


async def list_pages(api: Api, input: Json, key: str) -> Outcome:
    place = place_of(input, shortest=1)
    shelf = await shelf_named(api, place[0])
    found: list[tuple[tuple[str, ...], Json]] = []
    if shelf is not None:
        books = books_of(shelf, place[1] if len(place) > 1 else None)
        if len(books) > MAX_BOOKS:
            raise invalid(f"the shelf {place[0]!r} holds more than {MAX_BOOKS} books; name a book")
        for book in books:
            pages = await pages_of(api, book)
            if len(place) == 3:
                one = page_named(pages, book, place[2])
                pages = [] if one is None else [one]
            for entry in pages:
                found.append(((place[0], str(book.get("name")), str(entry.get("name"))), entry))
            if len(found) > MAX_PAGES:
                raise invalid(
                    f"more than {MAX_PAGES} pages lie at or below {'/'.join(place)}; "
                    "name a deeper place"
                )
    listed = []
    for at, entry in found:
        page = await api.get(f"pages/{int(entry['id'])}")
        listed.append({"place": list(at), "digest": digest_of(page), "mark": kept_of(page).mark})
    return Outcome({"pages": listed}, {"kind": "read"})


async def read_page(api: Api, input: Json, key: str) -> Outcome:
    place = place_of(input, shortest=3)
    _, entry = await located(api, place)
    if entry is None:
        raise TargetError("not_found", "none", False, f"no page at {'/'.join(place)}")
    page = await api.get(f"pages/{int(entry['id'])}")
    output = {
        "place": list(place),
        "body": text_of(page),
        "digest": digest_of(page),
        "mark": kept_of(page).mark,
    }
    return Outcome(output, {"kind": "read"})


async def write_page(api: Api, input: Json, key: str) -> Outcome:
    place = place_of(input, shortest=3)
    body = input.get("body")
    mark = input.get("mark")
    expected = input.get("expected")
    if not isinstance(body, str) or not body:
        raise invalid("`body` is the page's text")
    if not isinstance(mark, str):
        raise invalid("`mark` is the text kept beside the page")
    if expected is not None and not isinstance(expected, str):
        raise invalid("`expected` is the digest of the page replaced, or null")
    written = digest(body)
    book, entry = await located(api, place)
    if book is None:
        raise TargetError(
            "not_found",
            "none",
            False,
            f"no book {place[1]!r} on a shelf {place[0]!r}: a person makes shelves and books "
            "in the wiki, the connector only pages",
        )
    held: Json | None = None
    if entry is not None:
        held = await api.get(f"pages/{int(entry['id'])}")
        standing = digest_of(held)
        if kept_of(held).key == key and standing == written:
            return _written(place, held, written, replayed=True)
        if expected is None:
            raise conflict(f"a page is at {'/'.join(place)} already")
        if standing != expected:
            raise conflict(f"the page at {'/'.join(place)} changed")
    elif expected is not None:
        raise conflict(f"no page is at {'/'.join(place)} any more")
    others = theirs(held)
    tags = [*others, *ours(key, mark, written, written)]
    if held is None:
        page = await api.post(
            "pages", {"book_id": int(book["id"]), "name": place[2], "markdown": body, "tags": tags}
        )
    else:
        page = await api.put(f"pages/{int(held['id'])}", {"markdown": body, "tags": tags})
    if "id" not in page:
        raise TargetError("unknown", "unknown", False, "the wiki answered the write with no page")
    if not isinstance(page.get("markdown"), str):
        page = await api.get(f"pages/{int(page['id'])}")
    stored = digest(text_of(page))
    if stored != written:
        # The wiki changed the text it stored: keep the digest of what it holds beside it, so
        # that the untouched page still reads with the digest of what was written.
        await api.put(
            f"pages/{int(page['id'])}", {"tags": [*others, *ours(key, mark, written, stored)]}
        )
    return _written(place, page, written, replayed=False)


def _written(place: tuple[str, ...], page: Json, written: str, *, replayed: bool) -> Outcome:
    effect = {
        "kind": "write",
        "replayed": replayed,
        "records": [{"kind": RECORD, "id": str(page["id"])}],
        "content_digest": written,
    }
    return Outcome({"place": list(place), "digest": written}, effect)


type Operation = Callable[[Api, Json, str], Awaitable[Outcome]]

OPERATIONS: dict[str, Operation] = {
    LIST: list_pages,
    READ: read_page,
    WRITE: write_page,
}
