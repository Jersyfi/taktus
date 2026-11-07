"""The rule `citation`: an answer drawn from knowledge leaves its step only with its sources
(UC-5.5 §2, ADR-0265 §3). Pure: the answer, the documents read and what the source holds now
in, the cited answer out — or `Refused`, naming why.

**What is refused.** An answer that is not a list of statements, or has none. A statement
without text, or one that names no source. A statement that names a document the search did
not read: a model may not cite what the asker never read. A document without a link that opens
it. A reading that is not a list of documents, each with its identifier, link, version and
digest.

**What the result is.** The answer as a person reads it: every statement followed by the
numbers of its sources, then the sources, each with its title, link and version. The numbers
follow the order in which the answer first names a source. Each source carries its
**standing**: `current`, where what the source holds now is the version read; `changed`, where
the source now holds another version, both named; `removed`, where the source no longer shows
the document. What the source holds now is the newest of two observations: the reading of
versions the run made after the answer (`confirmed`), and the index's entry, where the index
observed the document later than that reading did.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from taktus.components.knowledge.domain.model.index import KnowledgeEntry
from taktus.components.knowledge.domain.service.indexing import Held, Read

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
FENCE = re.compile(r"^```[a-z]*\s*|\s*```$")

type Standing = Literal["current", "changed", "removed"]


class Refused(ValueError):
    """The answer cannot leave the step: the reason is the step's."""


@dataclass(frozen=True)
class Statement:
    text: str
    sources: tuple[str, ...]


def readings(documents: Any) -> dict[str, Read]:
    """The documents a search answered, by identifier."""
    if not isinstance(documents, list):
        raise Refused("the documents read are not a list: nothing can be cited")
    found: dict[str, Read] = {}
    for item in documents:
        if not isinstance(item, Mapping):
            raise Refused("a document read is not an object")
        document, url = item.get("document"), item.get("url")
        version, digest = item.get("version"), item.get("digest")
        if not isinstance(document, str) or not document:
            raise Refused("a document read has no identifier")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            raise Refused(f"the document {document!r} has no link that opens it")
        if not isinstance(version, str) or not isinstance(digest, str) or not DIGEST.match(digest):
            raise Refused(f"the document {document!r} has no version and digest")
        title = item.get("title")
        found[document] = Read(
            document, title if isinstance(title, str) else "", url, version, digest
        )
    return found


def held_now(confirmed: Any) -> dict[str, Held]:
    """What a reading of versions found, by identifier; empty where none was made."""
    if confirmed is None:
        return {}
    if not isinstance(confirmed, list):
        raise Refused("the reading of versions is not a list")
    found: dict[str, Held] = {}
    for item in confirmed:
        if not isinstance(item, Mapping) or not isinstance(item.get("document"), str):
            raise Refused("an entry of the reading of versions names no document")
        document = str(item["document"])
        if item.get("absent") is True:
            found[document] = Held(document, None, None)
            continue
        version, digest = item.get("version"), item.get("digest")
        if not isinstance(version, str) or not isinstance(digest, str) or not DIGEST.match(digest):
            raise Refused(f"the reading of versions gives no version and digest of {document!r}")
        found[document] = Held(document, version, digest)
    return found


def statements(answer: Any) -> list[Statement]:
    """The statements of an answer: an object `{"statements": [{"text", "sources"}]}`, or that
    object as the text a model answered, in a code fence or not."""
    if isinstance(answer, str):
        text = FENCE.sub("", answer.strip())
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise Refused("the answer is not a list of statements with their sources")
        try:
            answer = json.loads(text[start : end + 1])
        except ValueError as error:
            raise Refused("the answer is not a list of statements with their sources") from error
    listed = answer.get("statements") if isinstance(answer, Mapping) else None
    if not isinstance(listed, list) or not listed:
        raise Refused("the answer names no statement: an answer without a source does not leave")
    found: list[Statement] = []
    for number, item in enumerate(listed, start=1):
        said = item.get("text") if isinstance(item, Mapping) else None
        sources = item.get("sources") if isinstance(item, Mapping) else None
        if not isinstance(said, str) or not said.strip():
            raise Refused(f"statement {number} has no text")
        if not isinstance(sources, list) or not sources:
            raise Refused(f"statement {number} names no source: {_short(said)}")
        if not all(isinstance(s, str | int) and not isinstance(s, bool) for s in sources):
            raise Refused(f"statement {number} names a source that is not a document")
        found.append(Statement(said.strip(), tuple(dict.fromkeys(str(s) for s in sources))))
    return found


def standing(
    found: Read,
    confirmed: Held | None,
    confirmed_at: datetime | None,
    entry: KnowledgeEntry | None,
    read_at: datetime,
) -> tuple[Standing, str | None]:
    """Whether the version read still holds, and what to say where it does not."""
    version, digest, absent, at = found.version, found.digest, False, read_at
    if confirmed is not None and confirmed_at is not None:
        version, digest, absent, at = (
            confirmed.version or found.version,
            confirmed.digest or found.digest,
            confirmed.absent,
            confirmed_at,
        )
    if entry is not None and entry.observed_at > at:
        version, digest, absent, at = entry.version, entry.digest, not entry.held, entry.observed_at
    when = at.isoformat(timespec="seconds")
    if absent:
        return "removed", f"the source no longer shows this document (observed {when})"
    if (version, digest) != (found.version, found.digest):
        return "changed", (
            f"the source now holds version {version}; this answer rests on version "
            f"{found.version} (observed {when})"
        )
    return "current", None


def cite(
    answer: Any,
    documents: Any,
    confirmed: Any,
    *,
    capability: str,
    read_at: datetime,
    confirmed_at: datetime | None,
    entries: Mapping[str, KnowledgeEntry],
) -> dict[str, Any]:
    """The answer with its sources, or `Refused`."""
    read = readings(documents)
    now = held_now(confirmed)
    said = statements(answer)
    numbers: dict[str, int] = {}
    for number, statement in enumerate(said, start=1):
        for document in statement.sources:
            if document not in read:
                raise Refused(
                    f"statement {number} names the document {document!r}, which the search did "
                    "not read: only what the asker read is cited"
                )
            numbers.setdefault(document, len(numbers) + 1)
    sources: list[dict[str, Any]] = []
    for document, number in numbers.items():
        found = read[document]
        is_now, note = standing(
            found, now.get(document), confirmed_at, entries.get(document), read_at
        )
        source: dict[str, Any] = {
            "number": number,
            "capability": capability,
            "document": document,
            "title": found.title,
            "url": found.url,
            "version": found.version,
            "digest": found.digest,
            "standing": is_now,
        }
        if note is not None:
            source["note"] = note
        sources.append(source)
    cited = [{"text": s.text, "sources": [numbers[d] for d in s.sources]} for s in said]
    return {
        "answer": rendered(cited, sources),
        "statements": cited,
        "sources": sources,
        "read_at": read_at.isoformat(timespec="seconds"),
    }


def rendered(cited: Sequence[Mapping[str, Any]], sources: Sequence[Mapping[str, Any]]) -> str:
    """The answer as a person reads it, in Markdown: each statement with the numbers of its
    sources, then the sources with their links."""
    lines = [f"{s['text']} " + "".join(f"[{n}]" for n in s["sources"]) for s in cited]
    lines += ["", "Sources:"]
    for source in sources:
        title = source["title"] or source["document"]
        line = f"[{source['number']}] [{title}]({source['url']}), version {source['version']}"
        if source["standing"] != "current":
            line += f" — {source['standing']}: {source['note']}"
        lines.append(line)
    return "\n".join(lines)


def _short(text: str) -> str:
    return text if len(text) <= 80 else text[:77] + "…"
