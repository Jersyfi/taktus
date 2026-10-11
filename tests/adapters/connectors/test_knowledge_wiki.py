"""The wiki connector against the fake of the wiki: `knowledge.pages` as ADR-0065 §4 states it,
where the wiki changes the text it stores (issue #197).

What is proven: a page the connector wrote and nobody touched reads back with the digest of the
text written, although the wiki stored another text; a page edited in the wiki reads with
another digest and the same mark, and a write that expects the old digest ends `conflict` and
writes nothing; a repeat with the same key writes nothing and answers `replayed`; a place maps
onto shelf, book and page, and one the wiki cannot hold is refused as `invalid` before any
request; the credential is read from the file its variable names and from nowhere else; and the
guides, published twice, are written once and then kept.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from taktus.adapters.driven.connectors.bookstack import declaration
from taktus.adapters.driven.connectors.bookstack.server import Config, Connector, build_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driving.cli.guides_command import rendered
from taktus.components.knowledge.application.service import PublishGuides, PublishGuidesHandler
from taktus.components.knowledge.domain.model import Mark
from taktus.ports.worker import CredentialReference

from .conftest import KNOWLEDGE_READ, KNOWLEDGE_WRITE, Wiki

type Json = dict[str, Any]

ROOT = Path(__file__).resolve().parents[3]
PLACE = ["Taktus", "Administration", "Installing"]
BODY = "# Installing\r\n\r\nRun it.   \r\nThen check it.\n\n"
MARK = '{"generator":"taktus.guides/1","guide":"administration","page":"installing"}'

pytestmark = pytest.mark.usefixtures("wiki_credentials")


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def context(
    step: str = "write", key: str | None = None, credential: str | None = KNOWLEDGE_WRITE
) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_guides",
        "run_id": "run_guides",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key or f"taktus:run_guides:{step}:1",
        "credentials": [] if credential is None else [{"name": credential, "injected_as": "env"}],
    }


async def call(wiki: Wiki, name: str, ctx: Json, input: Json) -> tuple[bool, Json]:
    result = await Connector(Config(target=wiki.url, timeout=5.0)).call(name, ctx, input)
    content = result.structured_content
    assert isinstance(content, dict)
    return bool(result.is_error), content


async def write(
    wiki: Wiki,
    body: str = BODY,
    expected: str | None = None,
    key: str | None = None,
    place: list[str] = PLACE,
) -> tuple[bool, Json]:
    return await call(
        wiki,
        declaration.WRITE,
        context(key=key),
        {"place": place, "body": body, "mark": MARK, "expected": expected},
    )


async def read(wiki: Wiki, place: list[str] = PLACE) -> tuple[bool, Json]:
    return await call(wiki, declaration.READ, context("read"), {"place": place})


def test_it_declares_the_three_operations_and_a_marked_write() -> None:
    declared = declaration.capabilities()
    assert declared["capabilities"] == ["knowledge.pages"]
    operations = {op["name"]: op for op in declared["operations"]}
    assert set(operations) == {
        "knowledge.pages.list",
        "knowledge.pages.read",
        "knowledge.pages.write",
    }
    assert operations["knowledge.pages.list"]["effect"] == "read"
    assert operations["knowledge.pages.read"]["effect"] == "read"
    assert operations["knowledge.pages.write"]["effect"] == "write"
    assert operations["knowledge.pages.write"]["idempotency"] == "marked"
    assert declared["credentials"] == [{"name": "KNOWLEDGE_TOKEN", "purpose": "actions"}]


async def test_an_untouched_page_reads_with_the_digest_of_the_text_written(wiki: Wiki) -> None:
    failed, written = await write(wiki)
    assert not failed, written
    assert written["output"] == {"place": PLACE, "digest": digest(BODY)}
    assert written["effect"]["replayed"] is False
    assert written["effect"]["content_digest"] == digest(BODY)

    stored = wiki.page("Installing")["markdown"]
    assert stored != BODY, "the fake changed the text it stored, as a wiki may"

    failed, page = await read(wiki)
    assert not failed, page
    assert page["output"]["digest"] == digest(BODY), "untouched, so not edited by hand"
    assert page["output"]["mark"] == MARK
    assert page["output"]["body"] == stored

    failed, listed = await call(
        wiki, declaration.LIST, context("list"), {"place": ["Taktus", "Administration"]}
    )
    assert not failed, listed
    assert listed["output"]["pages"] == [{"place": PLACE, "digest": digest(BODY), "mark": MARK}]


async def test_a_text_the_wiki_keeps_as_written_needs_no_second_write(wiki: Wiki) -> None:
    body = "# Installing\n\nRun it."
    failed, _ = await write(wiki, body=body)
    assert not failed
    tags = {t["name"]: t["value"] for t in wiki.page("Installing")["tags"]}
    assert tags["taktus-digest"] == tags["taktus-stored"] == digest(body)
    assert wiki.page("Installing")["revision_count"] == 1


async def test_a_hand_edit_reads_with_another_digest_and_the_same_mark(wiki: Wiki) -> None:
    await write(wiki)
    wiki.control("/_fake/edit", {"id": wiki.page("Installing")["id"], "markdown": "Edited."})

    failed, page = await read(wiki)
    assert not failed, page
    assert page["output"]["digest"] == digest("Edited.")
    assert page["output"]["mark"] == MARK
    assert page["output"]["body"] == "Edited."

    revisions = wiki.page("Installing")["revision_count"]
    failed, error = await write(
        wiki, body="# Installing\n\nNew.\n", expected=digest(BODY), key="k" * 20
    )
    assert failed and error["cause"] == "conflict", error
    assert error["retryable"] is False and error["effect"] == "none"
    assert wiki.page("Installing")["markdown"] == "Edited.", "the person's text stands"
    assert wiki.page("Installing")["revision_count"] == revisions


async def test_an_edit_in_the_visual_editor_reads_as_its_text(wiki: Wiki) -> None:
    await write(wiki)
    wiki.control("/_fake/edit", {"id": wiki.page("Installing")["id"], "html": "<p>Visual.</p>"})
    failed, page = await read(wiki)
    assert not failed
    assert page["output"]["body"] == "<p>Visual.</p>"
    assert page["output"]["digest"] == digest("<p>Visual.</p>")
    assert page["output"]["mark"] == MARK


async def test_a_page_is_replaced_where_it_holds_the_expected_text_and_a_persons_tags_stay(
    wiki: Wiki,
) -> None:
    await write(wiki)
    page = wiki.page("Installing")
    wiki.control(
        "/_fake/edit",
        {
            "id": page["id"],
            "markdown": page["markdown"],
            "tags": [*page["tags"], {"name": "audience", "value": "operators"}],
        },
    )
    failed, replaced = await write(
        wiki, body="# Installing\n\nNew.\n", expected=digest(BODY), key="k" * 20
    )
    assert not failed, replaced
    assert replaced["effect"]["records"] == [{"kind": "knowledge.page", "id": str(page["id"])}]
    tags = {t["name"]: t["value"] for t in wiki.page("Installing")["tags"]}
    assert tags["audience"] == "operators"
    failed, again = await read(wiki)
    assert again["output"]["digest"] == digest("# Installing\n\nNew.\n")


async def test_a_repeat_with_the_same_key_writes_nothing(wiki: Wiki) -> None:
    failed, first = await write(wiki, key="taktus:run_guides:write:1")
    assert not failed
    revisions = wiki.page("Installing")["revision_count"]
    failed, again = await write(wiki, key="taktus:run_guides:write:1")
    assert not failed, again
    assert again["effect"]["replayed"] is True
    assert again["effect"]["records"] == first["effect"]["records"]
    assert wiki.page("Installing")["revision_count"] == revisions
    assert wiki.state()["pages"]["Administration"] == 1

    failed, other = await write(wiki, key="taktus:run_guides:write:2")
    assert failed and other["cause"] == "conflict", "a new key expecting no page finds one"


async def test_a_place_maps_onto_shelf_book_and_page(wiki: Wiki) -> None:
    await write(wiki)
    for place in (["Taktus"], ["Taktus", "Administration"], PLACE):
        failed, listed = await call(wiki, declaration.LIST, context("list"), {"place": place})
        assert not failed, listed
        assert [p["place"] for p in listed["output"]["pages"]] == [PLACE]
    failed, listed = await call(
        wiki, declaration.LIST, context("list"), {"place": ["Scratch", "Conformance"]}
    )
    names = [p["place"][-1] for p in listed["output"]["pages"]]
    assert names == ["Seeded page"], "a page inside a chapter has no place"
    failed, listed = await call(wiki, declaration.LIST, context("list"), {"place": ["Nowhere"]})
    assert not failed and listed["output"]["pages"] == []

    failed, error = await read(wiki, ["Scratch", "Conformance", "In a chapter"])
    assert failed and error["cause"] == "not_found"
    failed, error = await write(wiki, place=["Elsewhere", "Administration", "Installing"])
    assert failed and error["cause"] == "not_found", "the book is on another shelf"
    failed, error = await write(wiki, place=["Taktus", "No such book", "Installing"])
    assert failed and error["cause"] == "not_found"
    assert "a person makes shelves and books" in error["detail"]


async def test_a_name_twice_in_one_book_is_ambiguous(wiki: Wiki) -> None:
    wiki.control("/_fake/pages", {"book": "Administration", "name": "Installing"})
    wiki.control("/_fake/pages", {"book": "Administration", "name": "Installing"})
    failed, error = await read(wiki)
    assert failed and error["cause"] == "conflict"
    failed, error = await write(wiki)
    assert failed and error["cause"] == "conflict"
    assert wiki.state()["pages"]["Administration"] == 2


@pytest.mark.parametrize(
    ("operation", "place"),
    [
        (declaration.WRITE, ["Taktus", "Administration", "Chapter", "Installing"]),
        (declaration.WRITE, ["Taktus", "Installing"]),
        (declaration.READ, ["Taktus", "Administration"]),
        (declaration.LIST, []),
        (declaration.LIST, ["Taktus", "Administration", "Installing", "More"]),
        (declaration.WRITE, ["Taktus", "", "Installing"]),
        (declaration.WRITE, ["Taktus", "Administration", " Installing"]),
        (declaration.READ, ["Taktus", "Administration", "Install\ning"]),
        (declaration.WRITE, ["Taktus", "Administration", "x" * 256]),
        (declaration.READ, "Taktus/Administration/Installing"),
    ],
)
async def test_a_place_the_wiki_cannot_hold_is_refused_before_any_request(
    wiki: Wiki, operation: str, place: Any
) -> None:
    before = wiki.state()["requests"]
    input: Json = {"place": place, "body": BODY, "mark": MARK, "expected": None}
    failed, error = await call(wiki, operation, context(), input)
    assert failed and error["cause"] == "invalid", error
    assert "consumption" not in error
    assert wiki.state()["requests"] == before


async def test_the_credential_is_read_from_its_file_and_nowhere_else(
    wiki: Wiki, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed, error = await call(wiki, declaration.READ, context(credential=None), {"place": PLACE})
    assert failed and error["cause"] == "unauthenticated"

    monkeypatch.delenv(f"TAKTUS_CREDENTIAL_{KNOWLEDGE_WRITE}_FILE")
    monkeypatch.setenv(KNOWLEDGE_WRITE, wiki.write_value)
    before = wiki.state()["requests"]
    failed, error = await write(wiki)
    assert failed and error["cause"] == "unauthenticated", (
        "a variable holding the value is not read"
    )
    assert wiki.state()["requests"] == before


async def test_a_token_that_may_only_read_is_forbidden_to_write(wiki: Wiki) -> None:
    failed, error = await call(
        wiki,
        declaration.WRITE,
        context(credential=KNOWLEDGE_READ),
        {"place": PLACE, "body": BODY, "mark": MARK, "expected": None},
    )
    assert failed and error["cause"] == "forbidden", error
    assert error["retryable"] is False


async def test_an_outage_is_unavailable_and_may_be_retried(wiki: Wiki) -> None:
    wiki.control("/_fake/outage", {"on": True})
    try:
        failed, error = await read(wiki)
    finally:
        wiki.control("/_fake/outage", {"on": False})
    assert failed and error["cause"] == "unavailable" and error["retryable"] is True


async def test_no_token_appears_in_an_answer(wiki: Wiki) -> None:
    answers = [await write(wiki), await read(wiki), await write(wiki, key="k" * 20)]
    text = json.dumps(answers)
    assert wiki.write_value not in text
    assert wiki.write_value.split(":")[1] not in text


async def test_the_guides_are_published_once_and_then_kept(wiki: Wiki) -> None:
    """The guides of this repository through the connector, as `taktusctl guides publish`
    would put them into a directory: every page created; published again, every page kept,
    although the wiki changed every text it stored."""
    manifest, source, pages = rendered(ROOT, "HEAD", None)
    handler = PublishGuidesHandler(
        McpActionConnector(build_server(Config(target=wiki.url, timeout=5.0)), timeout=10.0)
    )

    def command(run: str) -> PublishGuides:
        return PublishGuides(
            tenant="default",
            identity="idn_guides",
            run_id=run,
            manifest=manifest,
            manifest_source=source,
            pages=pages,
            credentials=(CredentialReference(name=KNOWLEDGE_WRITE, injected_as="env"),),
        )

    first = await handler.execute(command("guides-first-0001"))
    assert first.counted()["created"] == len(first.pages) == len(pages) + 2
    for page in wiki.pages():
        if page["book_id"] in {p["book_id"] for p in wiki.pages() if p["name"] == "Contents"}:
            tags = {t["name"] for t in page["tags"]}
            assert "taktus-mark-0" in tags
    held = [p for p in wiki.pages() if p["name"] == "Contents"]
    assert len(held) == 2

    again = await handler.execute(command("guides-again-0002"))
    assert again.counted() == {"created": 0, "updated": 0, "kept": len(pages) + 2, "withheld": 0}
    marks = [
        Mark.decode(m)
        for m in [(await read(wiki, ["Taktus", "Administration", "Contents"]))[1]["output"]["mark"]]
    ]
    assert marks[0] is not None and marks[0].guide == "administration"
