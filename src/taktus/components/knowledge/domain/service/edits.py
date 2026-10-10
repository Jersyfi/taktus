"""What the report of a hand edit says: a rule over the page that was kept (UC-13.6, ADR-0066).

A page a person edited in the knowledge system is kept, and its difference from the repository
goes to the person responsible for the documentation. This module says what that report holds:
its identifier, its title, what is needed, the steps and what stands still. The reporting
component delivers it; it composes nothing here and adds nothing.

**One edit, one report.** The identifier is derived from the guide, the page and the digest of
the text that stands. A daily run that finds the same edit again raises the same identifier,
and raising is idempotent by it: the person hears of an edit once. An edit made on top of it is
another text, and another report.
"""

from __future__ import annotations

from taktus.components.knowledge.domain.service.pages import PageState

PREFIX = "guides-"

WHAT = {
    PageState.EDITED: "was edited by hand in the knowledge system",
    PageState.OUTDATED: "was edited by hand in the knowledge system, and the repository has "
    "changed since",
    PageState.FOREIGN: "holds a text Taktus did not write",
}


def report_id(guide: str, page: str, held: str) -> str:
    """The report's identifier: the guide, the page, and twelve hexadecimal digits of the
    digest of the text that stands."""
    return f"{PREFIX}{guide}-{page}-{held.removeprefix('sha256:')[:12]}"


def title(place: tuple[str, ...], state: PageState) -> str:
    return f"The guide page {'/'.join(place)} {WHAT[state]}"


def needed(place: tuple[str, ...]) -> tuple[str, ...]:
    return (
        f"A decision on the edit of {'/'.join(place)}: it becomes a change to the repository, "
        "or the page goes back to the repository's text.",
    )


def steps(difference: str) -> tuple[str, ...]:
    return (
        "The difference, the repository's text against the page as it stands:\n\n"
        f"```diff\n{difference.rstrip()}\n```",
        "To keep the edit: change the files the page names at its end, in a pull request to the "
        "repository. Once it is merged, the next run writes the page from the repository.",
        "To drop the edit: give the page back the repository's text, or delete the page. The "
        "next run writes it from the repository.",
    )


def standing_still(place: tuple[str, ...]) -> tuple[str, ...]:
    return (
        f"The page {'/'.join(place)} is not written from the repository while the edit stands; "
        "the guide's contents page shows it.",
    )
