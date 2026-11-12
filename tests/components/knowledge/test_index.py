"""The index of what was read (UC-5.5 §2, ADR-0265 §4): references and digests, never a copy;
a source document changed or removed is reflected in it; and the handler records every reading,
also where the answer is refused."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from taktus.adapters.driven.memory import MemoryPersistence, MemoryRepository
from taktus.components.knowledge.application.service import CiteAnswer, CiteAnswerHandler
from taktus.components.knowledge.domain.model import KnowledgeEntry, entry_id
from taktus.components.knowledge.domain.service import indexing
from taktus.components.knowledge.domain.service.citing import Refused

CAPABILITY = "knowledge.documents"
AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
URL = "https://wiki.example/books/hr/page/holidays"


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def found(version: str, text: str) -> indexing.Read:
    return indexing.Read("12", "Holidays", URL, version, digest(text))


def test_a_first_reading_makes_an_entry_of_references_and_a_digest() -> None:
    entry = indexing.read(None, tenant="t", capability=CAPABILITY, found=found("1", "a"), at=AT)
    assert entry.id == entry_id(CAPABILITY, "12")
    assert (entry.identifier, entry.url, entry.version, entry.digest) == (
        "12",
        URL,
        "1",
        digest("a"),
    )
    assert entry.held and entry.earlier == ()
    assert set(KnowledgeEntry.model_fields) == {
        "id",
        "tenant",
        "created_at",
        "capability",
        "identifier",
        "title",
        "url",
        "version",
        "digest",
        "observed_at",
        "held",
        "earlier",
    }, "nothing of the text: the source stays the record"


def test_a_changed_document_moves_its_old_version_into_the_history() -> None:
    first = indexing.read(None, tenant="t", capability=CAPABILITY, found=found("1", "a"), at=AT)
    later = indexing.read(
        first, tenant="t", capability=CAPABILITY, found=found("2", "b"), at=AT + timedelta(days=1)
    )
    assert (later.version, later.digest) == ("2", digest("b"))
    assert [(o.version, o.digest, o.at) for o in later.earlier] == [("1", digest("a"), AT)]
    again = indexing.read(
        later, tenant="t", capability=CAPABILITY, found=found("2", "b"), at=AT + timedelta(days=2)
    )
    assert again.earlier == later.earlier and again.observed_at == AT + timedelta(days=2)


def test_a_removed_document_is_marked_and_keeps_its_last_version() -> None:
    first = indexing.read(None, tenant="t", capability=CAPABILITY, found=found("1", "a"), at=AT)
    gone = indexing.held(first, indexing.Held("12", None, None), AT + timedelta(hours=1))
    assert not gone.held and gone.version == "1"
    back = indexing.read(
        gone, tenant="t", capability=CAPABILITY, found=found("1", "a"), at=AT + timedelta(hours=2)
    )
    assert back.held


def test_an_older_observation_changes_nothing() -> None:
    first = indexing.read(
        None, tenant="t", capability=CAPABILITY, found=found("2", "b"), at=AT + timedelta(days=1)
    )
    assert (
        indexing.read(first, tenant="t", capability=CAPABILITY, found=found("1", "a"), at=AT)
        == first
    )
    assert indexing.held(first, indexing.Held("12", None, None), AT) == first


def documents(version: str, text: str) -> list[dict[str, str]]:
    return [
        {
            "document": "12",
            "title": "Holidays",
            "url": URL,
            "version": version,
            "digest": digest(text),
            "body": text,
        }
    ]


async def test_the_handler_records_what_was_read_and_what_the_source_holds_now() -> None:
    persistence = MemoryPersistence()
    entries = MemoryRepository(persistence, KnowledgeEntry)
    handler = CiteAnswerHandler(entries, persistence)
    said = json.dumps({"statements": [{"text": "30 days.", "sources": ["12"]}]})
    cited = await handler.execute(
        CiteAnswer(
            tenant="t",
            capability=CAPABILITY,
            answer=said,
            documents=documents("1", "30 days"),
            confirmed=[{"document": "12", "version": "2", "digest": digest("28 days")}],
            read_at=AT,
            confirmed_at=AT + timedelta(seconds=5),
        )
    )
    assert cited["sources"][0]["standing"] == "changed"
    async with persistence.transaction("t"):
        (entry,) = await entries.list("t")
    assert entry.version == "2" and [o.version for o in entry.earlier] == ["1"]
    assert "30 days" not in json.dumps(entry.document()), "the index keeps no text"


async def test_a_refused_answer_still_teaches_the_index_what_was_read() -> None:
    persistence = MemoryPersistence()
    entries = MemoryRepository(persistence, KnowledgeEntry)
    handler = CiteAnswerHandler(entries, persistence)
    with pytest.raises(Refused, match="names no source"):
        await handler.execute(
            CiteAnswer(
                tenant="t",
                capability=CAPABILITY,
                answer=json.dumps({"statements": [{"text": "30 days.", "sources": []}]}),
                documents=documents("1", "30 days"),
                confirmed=None,
                read_at=AT,
                confirmed_at=None,
            )
        )
    async with persistence.transaction("t"):
        (entry,) = await entries.list("t")
    assert entry.version == "1"
