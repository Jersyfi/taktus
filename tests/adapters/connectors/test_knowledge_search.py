"""The wiki connector as a knowledge source: `knowledge.documents` against the fake of the wiki
(ADR-0265, UC-5.5 §2).

What is proven: a search answers each page it finds with its identifier, title, the link the
wiki's search gives, the version and the digest of its text, and the text; it keeps only pages,
never the shelves, books and chapters the search also finds; two tokens whose rights in the wiki
differ find different pages for the same query, and a page a token may not view is never
answered to it; a reading of versions answers what the wiki holds now, a page changed since with
its new version and a page deleted or hidden since as absent; an input the wiki cannot be asked
is refused before any request.
"""

from __future__ import annotations

import hashlib
from typing import Any

import httpx
import pytest
from taktus_connectors.bookstack import declaration
from taktus_connectors.bookstack.server import Config, Connector

from .conftest import KNOWLEDGE_READ, KNOWLEDGE_WRITE, Wiki

type Json = dict[str, Any]

pytestmark = pytest.mark.usefixtures("wiki_credentials")


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def context(credential: str) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_asker",
        "run_id": "run_answer",
        "step_id": "search",
        "attempt": 1,
        "idempotency_key": "taktus:run_answer:search:1",
        "credentials": [{"name": credential, "injected_as": "env"}],
    }


async def call(wiki: Wiki, name: str, input: Json, credential: str) -> tuple[bool, Json]:
    result = await Connector(Config(target=wiki.url, timeout=5.0)).call(
        name, context(credential), input
    )
    content = result.structured_content
    assert isinstance(content, dict)
    return bool(result.is_error), content


def fake(wiki: Wiki, path: str, body: Json) -> None:
    httpx.post(f"{wiki.url}/_fake/{path}", json=body, timeout=5.0).raise_for_status()


def seeded(wiki: Wiki) -> None:
    """Two pages on holidays in two books; the read-only token may view one book only."""
    fake(
        wiki,
        "pages",
        {"book": "Administration", "name": "Holidays", "markdown": "Holidays: 30 days."},
    )
    fake(
        wiki,
        "pages",
        {"book": "Using Taktus", "name": "Leave", "markdown": "Holidays are asked in the portal."},
    )
    fake(wiki, "views", {"token": wiki.read_value, "books": ["Using Taktus"]})


def page_id(wiki: Wiki, name: str) -> int:
    return int(next(p for p in wiki.pages() if p["name"] == name)["id"])


async def test_a_search_answers_each_page_with_its_link_version_digest_and_text(
    wiki: Wiki,
) -> None:
    seeded(wiki)
    failed, found = await call(wiki, declaration.SEARCH, {"query": "holidays"}, KNOWLEDGE_WRITE)
    assert not failed, found
    documents = found["output"]["documents"]
    assert [d["title"] for d in documents] == ["Holidays", "Leave"]
    first = documents[0]
    assert first == {
        "document": str(page_id(wiki, "Holidays")),
        "title": "Holidays",
        "url": f"{wiki.url}/books/administration/page/holidays",
        "version": "1",
        "digest": digest("Holidays: 30 days."),
        "body": "Holidays: 30 days.",
    }
    assert found["effect"] == {"kind": "read"}
    assert found["consumption"] == {"quota_units": 3}, "the search, then each page it found"


async def test_a_search_keeps_pages_only(wiki: Wiki) -> None:
    failed, found = await call(
        wiki, declaration.SEARCH, {"query": "administration"}, KNOWLEDGE_WRITE
    )
    assert not failed, found
    assert found["output"]["documents"] == [], "the book of that name is not a document"


async def test_two_tokens_with_different_rights_find_what_the_wiki_shows_each(wiki: Wiki) -> None:
    seeded(wiki)
    _, wide = await call(wiki, declaration.SEARCH, {"query": "holidays"}, KNOWLEDGE_WRITE)
    _, narrow = await call(wiki, declaration.SEARCH, {"query": "holidays"}, KNOWLEDGE_READ)
    assert [d["title"] for d in wide["output"]["documents"]] == ["Holidays", "Leave"]
    assert [d["title"] for d in narrow["output"]["documents"]] == ["Leave"]
    assert "30 days" not in str(narrow), "nothing of the page it may not view reached it"


async def test_versions_say_what_the_wiki_holds_now(wiki: Wiki) -> None:
    seeded(wiki)
    holidays, leave = page_id(wiki, "Holidays"), page_id(wiki, "Leave")
    fake(wiki, "edit", {"id": holidays, "markdown": "Holidays: 28 days."})
    fake(wiki, "delete", {"id": leave})
    failed, held = await call(
        wiki,
        declaration.VERSIONS,
        {"documents": [str(holidays), {"document": str(leave)}]},
        KNOWLEDGE_WRITE,
    )
    assert not failed, held
    assert held["output"]["documents"] == [
        {"document": str(holidays), "version": "2", "digest": digest("Holidays: 28 days.")},
        {"document": str(leave), "absent": True},
    ]


async def test_a_page_hidden_from_the_token_is_absent_to_it(wiki: Wiki) -> None:
    seeded(wiki)
    failed, held = await call(
        wiki,
        declaration.VERSIONS,
        {"documents": [str(page_id(wiki, "Holidays"))]},
        KNOWLEDGE_READ,
    )
    assert not failed, held
    assert held["output"]["documents"] == [
        {"document": str(page_id(wiki, "Holidays")), "absent": True}
    ]


@pytest.mark.parametrize(
    ("name", "input"),
    [
        (declaration.SEARCH, {}),
        (declaration.SEARCH, {"query": "   "}),
        (declaration.SEARCH, {"query": "a\x00b"}),
        (declaration.SEARCH, {"query": "holidays", "count": 0}),
        (declaration.SEARCH, {"query": "holidays", "count": 11}),
        (declaration.VERSIONS, {"documents": []}),
        (declaration.VERSIONS, {"documents": ["page-1"]}),
        (declaration.VERSIONS, {"documents": [str(n) for n in range(11)]}),
    ],
)
async def test_an_input_the_wiki_cannot_be_asked_is_refused_before_any_request(
    wiki: Wiki, name: str, input: Json
) -> None:
    before = wiki.state()["requests"]
    failed, error = await call(wiki, name, input, KNOWLEDGE_WRITE)
    assert failed and error["cause"] == "invalid", error
    assert wiki.state()["requests"] == before
