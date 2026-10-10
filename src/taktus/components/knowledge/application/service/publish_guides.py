"""Use case: the guides are put into the organisation's knowledge system (UC-13.6, ADR-0065).

The pages arrive rendered from the repository. For each guide the handler reads what the
knowledge system holds at the guide's place, measures every page against it
(`domain/service/pages.py`), writes the pages that are absent or changed, and keeps every page a
person edited there. The contents page of each guide is written last, with every page's state.

A write names the text it expects to replace. The knowledge system refuses it with `conflict`
when the page changed in between, and the page is then measured again and kept: a hand edit made
during the run is not overwritten either.

Every outward act goes through the capability `knowledge.pages` (ADR-0003): which knowledge
system serves it is configuration — a wiki, or a directory of files where the organisation has
none.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field

from taktus.components.knowledge.domain.model.guide import Manifest, Mark, Page, Source
from taktus.components.knowledge.domain.service.pages import (
    WITHHELD,
    WRITTEN,
    Held,
    PageState,
    below,
    contents,
    difference,
    retired,
    state,
)
from taktus.ports.connector import (
    ActionConnector,
    CallContext,
    CallFailed,
    Cause,
    idempotency_key,
)
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Digest, Value

CAPABILITY = "knowledge.pages"
LIST = f"{CAPABILITY}.list"
READ = f"{CAPABILITY}.read"
WRITE = f"{CAPABILITY}.write"


@dataclass(frozen=True)
class PublishGuides:
    tenant: str
    identity: str
    run_id: str
    """Whose attempt the writes are: every write's idempotency key is derived from it and the
    page's place (`taktus.ports.connector.idempotency_key`). One identifier per publication: a
    key is never reused for another text."""
    manifest: Manifest
    manifest_source: Source
    pages: tuple[Page, ...]
    """Every page of every guide, rendered at one commit (`domain/service/render.py`)."""
    credentials: tuple[CredentialReference, ...] = ()
    held: tuple[Held, ...] | None = None
    """One reading of the knowledge system, taken by the run before it measured the pages
    (ADR-0066). The pages are then published against that reading, so that what the run
    measured is what it acts on; a write still names the text it expects, and a page edited
    since the reading is kept. None: the handler reads each guide's place itself."""


class Published(Value):
    guide: str
    page: str
    place: tuple[str, ...]
    state: PageState
    action: Literal["created", "updated", "kept", "withheld"]
    difference: str | None = None
    """For a page kept because a person's text stands: that text against the repository's."""
    held: Digest | None = None
    """For such a page: the digest of the text that stands, which names this edit and no
    other."""


class Publication(Value):
    commit: str
    pages: tuple[Published, ...] = Field(min_length=1)

    @property
    def withheld(self) -> tuple[Published, ...]:
        return tuple(p for p in self.pages if p.action == "withheld")

    def counted(self) -> dict[str, int]:
        """How many pages were created, updated, kept and withheld: what a run reports."""
        actions = ("created", "updated", "kept", "withheld")
        return {action: sum(1 for p in self.pages if p.action == action) for action in actions}


class PublishGuidesHandler:
    def __init__(self, knowledge_system: ActionConnector) -> None:
        self._system = knowledge_system

    async def execute(self, command: PublishGuides) -> Publication:
        commits = {page.commit for page in command.pages}
        if len(commits) != 1:
            raise ValueError("the pages of one publication are rendered at one commit")
        commit = commits.pop()
        published: list[Published] = []
        for guide in command.manifest.guides:
            pages = [page for page in command.pages if page.guide == guide.id]
            if not pages:
                continue
            place = pages[0].place[:-1]
            if command.held is not None:
                held = below({h.place: h for h in command.held}, place)
            else:
                held = await self._held(command, place)
            states: list[PageState] = []
            for page in pages:
                outcome = await self._publish(command, page, held.get(page.place))
                published.append(outcome)
                states.append(outcome.state)
            rendered = {page.place for page in pages} | {(*place, "Contents")}
            gone = sorted(p for p, h in held.items() if retired(guide.id, h, rendered))
            for gone_place in gone:
                mark = Mark.decode(held[gone_place].mark)
                published.append(
                    Published(
                        guide=guide.id,
                        page=mark.page if mark is not None else gone_place[-1],
                        place=gone_place,
                        state=PageState.RETIRED,
                        action="kept",
                    )
                )
            index = contents(
                guide, place, pages, states, command.manifest_source, commit, gone=gone
            )
            published.append(await self._publish(command, index, held.get(index.place)))
        return Publication(commit=commit, pages=tuple(published))

    async def _held(
        self, command: PublishGuides, place: tuple[str, ...]
    ) -> dict[tuple[str, ...], Held]:
        result = await self._system.call(
            LIST, self._context(command, "guides-read", place), {"place": list(place)}
        )
        found: dict[tuple[str, ...], Held] = {}
        for entry in _list(result.output.get("pages")):
            held = Held.model_validate({**entry, "place": tuple(entry.get("place") or ())})
            found[held.place] = held
        return found

    async def _publish(self, command: PublishGuides, page: Page, held: Held | None) -> Published:
        page_state = state(page, held)
        if page_state in WRITTEN:
            try:
                await self._system.call(
                    WRITE,
                    self._context(command, "guides-write", page.place),
                    {
                        "place": list(page.place),
                        "body": page.body,
                        "mark": page.mark().encode(),
                        "expected": held.digest if held is not None else None,
                    },
                )
            except CallFailed as failed:
                if failed.error.cause is not Cause.CONFLICT:
                    raise
                return await self._withheld(command, page)
            action: Literal["created", "updated"] = (
                "created" if page_state is PageState.ABSENT else "updated"
            )
            return _published(page, page_state, action)
        if page_state in WITHHELD:
            return await self._withheld(command, page)
        return _published(page, page_state, "kept")

    async def _withheld(self, command: PublishGuides, page: Page) -> Published:
        """A person's text stands: read it, measure it again, and report its difference."""
        result = await self._system.call(
            READ, self._context(command, "guides-read", page.place), {"place": list(page.place)}
        )
        output = result.output
        held = Held.model_validate(
            {"place": page.place, "digest": output["digest"], "mark": output.get("mark")}
        )
        page_state = state(page, held)
        if page_state not in WITHHELD:
            # Between the list and the write the page became the repository's text again.
            return _published(page, page_state, "kept")
        return _published(
            page,
            page_state,
            "withheld",
            difference=difference(page, str(output["body"]), held.mark),
            held=held.digest,
        )

    @staticmethod
    def _context(command: PublishGuides, step: str, place: Sequence[str]) -> CallContext:
        # A place may hold any character; the step is named by its digest, so that the key the
        # run derives from it keeps to the contract's alphabet.
        step_id = f"{step}-" + hashlib.sha256("/".join(place).encode("utf-8")).hexdigest()[:24]
        return CallContext(
            tenant=command.tenant,
            identity=command.identity,
            run_id=command.run_id,
            step_id=step_id,
            attempt=1,
            idempotency_key=idempotency_key(command.run_id, step_id, 1),
            credentials=command.credentials,
        )


def _published(
    page: Page,
    page_state: PageState,
    action: Literal["created", "updated", "kept", "withheld"],
    *,
    difference: str | None = None,
    held: str | None = None,
) -> Published:
    return Published(
        guide=page.guide,
        page=page.id,
        place=page.place,
        state=page_state,
        action=action,
        difference=difference,
        held=held,
    )


def _list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("the knowledge system's list carries no `pages`")
    return [entry for entry in value if isinstance(entry, Mapping)]
