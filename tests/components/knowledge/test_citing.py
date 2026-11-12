"""The rule `citation` (UC-5.5 §2, ADR-0265 §3): every statement drawn from knowledge names the
source it came from, with a link that opens it; an answer without a source does not leave the
step; and an answer never cites a version the source no longer holds without saying so."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from taktus.components.knowledge.domain.model import KnowledgeEntry
from taktus.components.knowledge.domain.service import indexing
from taktus.components.knowledge.domain.service.citing import Refused, cite

CAPABILITY = "knowledge.documents"
READ_AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
CONFIRMED_AT = READ_AT + timedelta(seconds=30)


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def document(id: str, title: str, text: str, version: str = "1") -> dict[str, Any]:
    return {
        "document": id,
        "title": title,
        "url": f"https://wiki.example/books/hr/page/{title.lower()}",
        "version": version,
        "digest": digest(text),
        "body": text,
    }


DOCUMENTS = [
    document("12", "Holidays", "Holidays: 30 days."),
    document("14", "Leave", "Holidays are asked in the portal."),
]


def answer(*statements: tuple[str, list[Any]]) -> str:
    return json.dumps({"statements": [{"text": t, "sources": s} for t, s in statements]})


def cited(
    said: Any,
    confirmed: Any = None,
    entries: dict[str, KnowledgeEntry] | None = None,
    documents: Any = DOCUMENTS,
) -> dict[str, Any]:
    return cite(
        said,
        documents,
        confirmed,
        capability=CAPABILITY,
        read_at=READ_AT,
        confirmed_at=None if confirmed is None else CONFIRMED_AT,
        entries=entries or {},
    )


def test_every_statement_names_its_sources_with_the_link_that_opens_them() -> None:
    result = cited(
        answer(
            ("Every employee has 30 days.", ["12"]), ("They are asked in the portal.", [14, "12"])
        )
    )
    assert result["statements"] == [
        {"text": "Every employee has 30 days.", "sources": [1]},
        {"text": "They are asked in the portal.", "sources": [2, 1]},
    ]
    assert [(s["number"], s["document"], s["standing"]) for s in result["sources"]] == [
        (1, "12", "current"),
        (2, "14", "current"),
    ]
    assert result["sources"][0]["url"] == "https://wiki.example/books/hr/page/holidays"
    assert result["sources"][0]["capability"] == CAPABILITY
    assert result["answer"] == (
        "Every employee has 30 days. [1]\n"
        "They are asked in the portal. [2][1]\n"
        "\n"
        "Sources:\n"
        "[1] [Holidays](https://wiki.example/books/hr/page/holidays), version 1\n"
        "[2] [Leave](https://wiki.example/books/hr/page/leave), version 1"
    )


def test_a_document_read_and_not_cited_is_not_a_source() -> None:
    result = cited(answer(("Every employee has 30 days.", ["12"])))
    assert [s["document"] for s in result["sources"]] == ["12"]


def test_the_model_s_answer_may_come_in_a_code_fence() -> None:
    fenced = "```json\n" + answer(("Every employee has 30 days.", ["12"])) + "\n```"
    assert cited(fenced)["statements"] == [{"text": "Every employee has 30 days.", "sources": [1]}]


@pytest.mark.parametrize(
    ("said", "reason"),
    [
        ("Every employee has 30 days.", "not a list of statements"),
        ('{"statements": []}', "names no statement"),
        (answer(("Every employee has 30 days.", [])), "statement 1 names no source"),
        (answer(("", ["12"])), "statement 1 has no text"),
        (answer(("Fine.", ["12"]), ("Invented.", ["99"])), "statement 2 names the document '99'"),
        (answer(("Fine.", [True])), "not a document"),
    ],
)
def test_an_answer_without_a_source_does_not_leave(said: str, reason: str) -> None:
    with pytest.raises(Refused, match=reason):
        cited(said)


def test_a_document_without_a_link_cannot_be_cited() -> None:
    linkless = [{**DOCUMENTS[0], "url": ""}]
    with pytest.raises(Refused, match="no link that opens it"):
        cited(answer(("Every employee has 30 days.", ["12"])), documents=linkless)


def test_a_version_changed_since_the_reading_is_named_with_both_versions() -> None:
    result = cited(
        answer(("Every employee has 30 days.", ["12"])),
        confirmed=[{"document": "12", "version": "2", "digest": digest("Holidays: 28 days.")}],
    )
    (source,) = result["sources"]
    assert source["standing"] == "changed"
    assert source["version"] == "1", "the version the statement rests on"
    assert source["note"].startswith(
        "the source now holds version 2; this answer rests on version 1"
    )
    assert "— changed: the source now holds version 2" in result["answer"]


def test_a_document_the_source_no_longer_shows_is_named_removed() -> None:
    result = cited(
        answer(("Every employee has 30 days.", ["12"])),
        confirmed=[{"document": "12", "absent": True}],
    )
    (source,) = result["sources"]
    assert source["standing"] == "removed"
    assert "— removed: the source no longer shows this document" in result["answer"]


def test_the_index_s_later_observation_is_said_too() -> None:
    """The run read version 1 and confirmed it; the index observed version 3 after that —
    another reading since, as a run resumed after a halt would meet."""
    found = indexing.Read("12", "Holidays", DOCUMENTS[0]["url"], "1", DOCUMENTS[0]["digest"])
    entry = indexing.read(
        None, tenant="t", capability=CAPABILITY, found=found, at=READ_AT - timedelta(days=1)
    )
    later = indexing.held(
        entry,
        indexing.Held("12", "3", digest("Holidays: 25 days.")),
        CONFIRMED_AT + timedelta(hours=1),
    )
    result = cited(
        answer(("Every employee has 30 days.", ["12"])),
        confirmed=[{"document": "12", "version": "1", "digest": DOCUMENTS[0]["digest"]}],
        entries={"12": later},
    )
    assert result["sources"][0]["standing"] == "changed"
    assert "version 3" in result["sources"][0]["note"]


def test_an_older_index_observation_changes_nothing() -> None:
    found = indexing.Read("12", "Holidays", DOCUMENTS[0]["url"], "0", digest("old"))
    older = indexing.read(
        None, tenant="t", capability=CAPABILITY, found=found, at=READ_AT - timedelta(days=1)
    )
    result = cited(answer(("Every employee has 30 days.", ["12"])), entries={"12": older})
    assert result["sources"][0]["standing"] == "current"
