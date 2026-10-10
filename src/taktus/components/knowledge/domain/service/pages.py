"""What a page in a knowledge system is, measured against the repository: a rule (ADR-0065).

Seven states. Two are written, five are not:

- `absent`: no page is at the place. It is written.
- `current`: the page Taktus wrote is there unchanged, and the repository says the same. Nothing
  happens.
- `changed`: the page Taktus wrote is there unchanged, and the repository says something else
  now. It is written.
- `edited`: the page Taktus wrote was edited by hand, and the repository still says what was
  written. It is kept, and its difference is reported.
- `outdated`: the page Taktus wrote was edited by hand, and the repository says something else
  now. It is kept, its difference is reported, and the contents page shows it out of date.
- `foreign`: a page is at the place that Taktus did not write. It is kept, and its difference is
  reported.
- `retired`: a page Taktus wrote for the guide that the repository no longer declares. It is
  kept, because nothing is deleted without asking, and the contents page says so.

A page is never overwritten unless it holds exactly the text Taktus last wrote there. The
contents page of a guide lists every page with its state, so that a page that was not
regenerated is shown as out of date where a reader of the guide looks.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence
from enum import StrEnum

from pydantic import Field

from taktus.components.knowledge.domain.model.guide import (
    CONTENTS,
    Guide,
    Mark,
    Page,
    Source,
)
from taktus.components.knowledge.domain.service.render import closing, content, digest
from taktus.shared.v1 import Digest, Value


class PageState(StrEnum):
    ABSENT = "absent"
    CURRENT = "current"
    CHANGED = "changed"
    EDITED = "edited"
    OUTDATED = "outdated"
    FOREIGN = "foreign"
    RETIRED = "retired"


WRITTEN = frozenset({PageState.ABSENT, PageState.CHANGED})
"""The states in which the repository's text replaces what the knowledge system holds."""

WITHHELD = frozenset({PageState.EDITED, PageState.OUTDATED, PageState.FOREIGN})
"""The states in which a person's text stands and its difference is reported."""


class Held(Value):
    """A page as the knowledge system holds it: the digest of its text and the mark beside it."""

    place: tuple[str, ...] = Field(min_length=1)
    digest: Digest
    mark: str | None = None


def state(page: Page, held: Held | None) -> PageState:
    if held is None:
        return PageState.ABSENT
    mark = Mark.decode(held.mark)
    if mark is None or (mark.guide, mark.page) != (page.guide, page.id):
        return PageState.FOREIGN
    if held.digest != mark.digest:
        return PageState.EDITED if mark.content == page.content else PageState.OUTDATED
    return PageState.CURRENT if mark.content == page.content else PageState.CHANGED


def difference(page: Page, held_text: str, held_mark: str | None = None) -> str:
    """The text in the knowledge system against the repository's, as a unified diff: what a
    person changed there, for whoever is responsible for the documentation. Where the page
    names an earlier commit than the repository's, the closing block is compared as if it named
    the same, so that the difference shows what the person changed and not the commit."""
    mark = Mark.decode(held_mark)
    said = page.body if mark is None else page.body.replace(page.commit, mark.commit)
    where = "/".join(page.place)
    return "".join(
        difflib.unified_diff(
            said.splitlines(keepends=True),
            held_text.splitlines(keepends=True),
            fromfile=f"repository at {page.commit}: {where}",
            tofile=f"knowledge system: {where}",
        )
    )


DESCRIBED = {
    PageState.ABSENT: "current",
    PageState.CURRENT: "current",
    PageState.CHANGED: "current",
    PageState.EDITED: "edited by hand; it differs from the repository",
    PageState.OUTDATED: "out of date: edited by hand, and the repository has changed since; "
    "the page does not show what the repository says now",
    PageState.FOREIGN: "not written by Taktus: a page of the same name was there; it does not "
    "show what the repository says",
    PageState.RETIRED: "no longer part of this guide: the repository does not say it any more",
}


def retired(guide: str, held: Held, rendered: set[tuple[str, ...]]) -> bool:
    """A page Taktus wrote for this guide at a place no rendered page takes any more."""
    mark = Mark.decode(held.mark)
    return mark is not None and mark.guide == guide and held.place not in rendered


def contents(
    guide: Guide,
    place: tuple[str, ...],
    pages: Sequence[Page],
    states: Sequence[PageState],
    manifest: Source,
    commit: str,
    gone: Sequence[tuple[str, ...]] = (),
) -> Page:
    """The contents page of one guide: who it is for, and every page with its state. Its
    source is the manifest; it is written by the same rules as every other page."""
    lines = [f"# {guide.title}", "", f"For {guide.reader}.", "", "## Pages", ""]
    for page, page_state in zip(pages, states, strict=True):
        lines.append(f"- {page.title} — {DESCRIBED[page_state]}")
    for place_gone in gone:
        lines.append(f"- {place_gone[-1]} — {DESCRIBED[PageState.RETIRED]}")
    lines.append("")
    said = "\n".join(lines) + "\n"
    body = said + closing([manifest], commit)
    return Page(
        guide=guide.id,
        id=CONTENTS,
        title="Contents",
        place=(*place, "Contents"),
        body=body,
        commit=commit,
        sources=(manifest,),
        digest=digest(body),
        content=content(said, (manifest,)),
    )
