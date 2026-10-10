"""A guide beyond the repository, and a page of it (UC-13.6, ADR-0065).

The repository declares its guides in a manifest: each guide has a reader, the place it is put
in a knowledge system, and pages. A page is made of parts, and every part is a file of the
repository or one section of it. Nothing else goes into a page, so that a page says what the
repository says and nothing more.

A rendered page carries what it was generated from: the commit, and every source with the
digest of the text taken from it. Its content is what it says with the commit left aside: a
commit that changes nothing a page says leaves the page as it is, and the page still names the
commit it was generated at. The mark is what Taktus keeps beside a page it wrote in a knowledge
system: which page it is, the commit, the digest of the text it wrote and of its content. A page
whose text no longer hashes to its mark was edited by hand there.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from taktus.shared.v1 import Digest, Value

SLUG = r"^[a-z][a-z0-9-]*$"
COMMIT = r"^[0-9a-f]{7,64}$"

CONTENTS = "contents"
"""The page of every guide that lists its other pages with their state. No page of the
manifest may take the identifier."""

GENERATOR: Literal["taktus.guides/1"] = "taktus.guides/1"


class Part(Value):
    """A file of the repository, or one section of it named by its heading."""

    file: str = Field(min_length=1, pattern=r"^[^/\\][^\\]*$")
    section: str | None = Field(default=None, min_length=1)
    heading: str | None = Field(default=None, min_length=1)
    """The heading the section takes in the page, where its own would mislead a reader who
    does not see the file it came from; its own where none is given."""

    @model_validator(mode="after")
    def _inside_the_repository(self) -> Part:
        if ".." in self.file.split("/"):
            raise ValueError(f"part {self.file!r} leaves the repository")
        if self.heading is not None and self.section is None:
            raise ValueError(f"part {self.file!r}: only a section takes another heading")
        return self


class PageSpec(Value):
    id: str = Field(pattern=SLUG)
    title: str = Field(min_length=1, max_length=120)
    parts: tuple[Part, ...] = Field(min_length=1)


class Guide(Value):
    id: str = Field(pattern=SLUG)
    title: str = Field(min_length=1, max_length=120)
    reader: str = Field(min_length=1)
    """Who the guide is for, in one phrase; the contents page says it."""
    place: tuple[str, ...] = Field(min_length=1)
    """Where the guide goes in a knowledge system, unless the organisation configures another
    place: one name per level."""
    pages: tuple[PageSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _pages_are_distinct(self) -> Guide:
        ids = [page.id for page in self.pages]
        if len(set(ids)) != len(ids):
            raise ValueError(f"guide {self.id!r} declares a page twice")
        if CONTENTS in ids:
            raise ValueError(f"guide {self.id!r}: the page {CONTENTS!r} is generated")
        titles = [page.title for page in self.pages]
        if len(set(titles)) != len(titles) or "Contents" in titles:
            raise ValueError(f"guide {self.id!r}: two pages would take the same place")
        return self


class Manifest(Value):
    guides: tuple[Guide, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _guides_are_distinct(self) -> Manifest:
        ids = [guide.id for guide in self.guides]
        if len(set(ids)) != len(ids):
            raise ValueError("a guide is declared twice")
        places = [guide.place for guide in self.guides]
        if len(set(places)) != len(places):
            raise ValueError("two guides take the same place")
        return self

    def guide(self, id: str) -> Guide:
        for guide in self.guides:
            if guide.id == id:
                return guide
        raise KeyError(id)

    def files(self) -> tuple[str, ...]:
        """Every file a page takes a part from, once each, sorted: what a run reads at the
        commit it renders (ADR-0066)."""
        return tuple(
            sorted(
                {part.file for guide in self.guides for page in guide.pages for part in page.parts}
            )
        )


class Source(Value):
    """One part of a page as it was taken: the file, the section, and the digest of the text."""

    file: str = Field(min_length=1)
    section: str | None = None
    digest: Digest


class Page(Value):
    """A page as the repository says it at one commit."""

    guide: str = Field(pattern=SLUG)
    id: str = Field(pattern=SLUG)
    title: str = Field(min_length=1)
    place: tuple[str, ...] = Field(min_length=2)
    body: str = Field(min_length=1)
    commit: str = Field(pattern=COMMIT)
    sources: tuple[Source, ...] = Field(min_length=1)
    digest: Digest
    """Of the body, as UTF-8."""
    content: Digest
    """Of what the page says with the commit left aside: its title, its parts and its sources."""

    def mark(self) -> Mark:
        return Mark(
            generator=GENERATOR,
            guide=self.guide,
            page=self.id,
            commit=self.commit,
            digest=self.digest,
            content=self.content,
        )


class Mark(Value):
    """What Taktus keeps beside a page it wrote, so that the next run can tell its own text
    from a hand edit. A knowledge system keeps it as it was given and returns it unchanged."""

    generator: Literal["taktus.guides/1"]
    guide: str = Field(pattern=SLUG)
    page: str = Field(pattern=SLUG)
    commit: str = Field(pattern=COMMIT)
    digest: Digest
    content: Digest

    def encode(self) -> str:
        return json.dumps(self.document(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, text: str | None) -> Mark | None:
        """The mark, or None where the text is none, or not one Taktus wrote."""
        if not text:
            return None
        try:
            return cls.model_validate(json.loads(text))
        except (ValueError, ValidationError):
            return None
