"""How a reading of a source moves the index (ADR-0265 §4). Pure: an entry and an observation
in, the entry as it now stands out.

Three observations exist. A **read** found the document, with its title, link, version and
digest. A **held** observation found the version and digest the source holds now. An **absent**
one found that the source no longer shows the document.

The newest observation stands. One older than what the entry already holds changes nothing: a
run resumed after a day carries a reading of the day before, and the index has observed since.
A newer version or digest replaces the current one, which moves into `earlier`. An absent
observation marks the entry not held and keeps its last version, so that a citation of it can
name what was removed. A document read again after is held again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from taktus.components.knowledge.domain.model.index import KnowledgeEntry, Observed, entry_id


@dataclass(frozen=True)
class Read:
    """A document as a search of its source answered it; its text is not kept here."""

    document: str
    title: str
    url: str
    version: str
    digest: str


@dataclass(frozen=True)
class Held:
    """What the source held of a document when its versions were read: a version and a digest,
    or nothing (`absent`)."""

    document: str
    version: str | None
    digest: str | None

    @property
    def absent(self) -> bool:
        return self.version is None


def read(
    entry: KnowledgeEntry | None, *, tenant: str, capability: str, found: Read, at: datetime
) -> KnowledgeEntry:
    """The entry after a search found the document."""
    if entry is None:
        return KnowledgeEntry(
            id=entry_id(capability, found.document),
            tenant=tenant,
            created_at=at,
            capability=capability,
            identifier=found.document,
            title=found.title,
            url=found.url,
            version=found.version,
            digest=found.digest,
            observed_at=at,
        )
    if at < entry.observed_at:
        return entry
    moved = _moved(entry, found.version, found.digest)
    return entry.model_copy(
        update={
            "title": found.title,
            "url": found.url,
            "version": found.version,
            "digest": found.digest,
            "observed_at": at,
            "held": True,
            "earlier": moved,
        }
    )


def held(entry: KnowledgeEntry, now: Held, at: datetime) -> KnowledgeEntry:
    """The entry after a reading of versions found what the source holds now."""
    if at < entry.observed_at:
        return entry
    if now.version is None or now.digest is None:
        return entry.model_copy(update={"observed_at": at, "held": False})
    return entry.model_copy(
        update={
            "version": now.version,
            "digest": now.digest,
            "observed_at": at,
            "held": True,
            "earlier": _moved(entry, now.version, now.digest),
        }
    )


def _moved(entry: KnowledgeEntry, version: str, digest: str) -> tuple[Observed, ...]:
    if (version, digest) == (entry.version, entry.digest):
        return entry.earlier
    return (
        *entry.earlier,
        Observed(version=entry.version, digest=entry.digest, at=entry.observed_at),
    )
