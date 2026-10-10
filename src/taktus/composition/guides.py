"""The guides as a process of the instance: the loopback connector's `Guides`, wired (ADR-0066).

S-05 of `blueprints/self-operation/` renders the guides from the repository, measures them
against the organisation's knowledge system, publishes them and reports every page a person
edited there (UC-13.6). Its steps reach the repository through `repository.files` and the
knowledge system through `knowledge.pages`, like every other process. What only the instance
can do — render by the knowledge component's rule, measure by it, publish through its use case,
and raise a report through the owner-facing channel — it asks of the loopback connector, and
this module answers. It is wiring: the knowledge and reporting components never import each
other, and they meet here.

**Rendered once, measured once, acted on once.** `render` returns the pages as one document.
`measure` and `publish` both take that document and the same reading of the knowledge system,
which the run took in its own step, so that what the run measured is what it acts on. A write
still names the text it expects to replace: a page a person edits between the reading and the
write is kept.

**A hand edit reaches the person responsible for the documentation**: the tenant's owner-facing
channel, when it carries the role the process names (ADR-0045). A tenant whose channel carries
no such role cannot be told, and the step says so instead of dropping the edit.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from taktus.adapters.driven.connectors.directory import ADAPTER as DIRECTORY
from taktus.adapters.driven.connectors.directory import DirectoryConnector
from taktus.components.knowledge.application.service import (
    CAPABILITY,
    Publication,
    PublishGuides,
    PublishGuidesHandler,
)
from taktus.components.knowledge.domain.model import Manifest, Page, Source
from taktus.components.knowledge.domain.service import edits
from taktus.components.knowledge.domain.service.pages import Held, PageState, measure
from taktus.components.knowledge.domain.service.render import RenderRefused, digest, render
from taktus.components.reporting.application.service import (
    ChannelOf,
    RaiseReport,
    RaiseReportHandler,
    ReportingError,
)
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.run.ports import ConnectorPool
from taktus.ports.clock import Clock
from taktus.ports.connector import ActionConnector, CallContext, Capabilities, Result


def served_directory(directory: Path | None) -> list[tuple[str, ActionConnector]]:
    """The directory connector, where the instance serves `knowledge.pages` over a directory
    (`TAKTUS_KNOWLEDGE_DIRECTORY`); nothing otherwise. It runs inside the instance, as the
    loopback connector does, because a directory is reached through the file system."""
    return [] if directory is None else [(DIRECTORY, DirectoryConnector(directory))]


class InstanceGuides:
    """The `Guides` of the loopback connector, over the knowledge and reporting components."""

    def __init__(
        self,
        connectors: ConnectorPool,
        channel: ChannelOf,
        raising: RaiseReportHandler,
        clock: Clock,
    ) -> None:
        self._connectors = connectors
        self._channel = channel
        self._raising = raising
        self._clock = clock

    async def sources(self, manifest: str) -> dict[str, Any]:
        return {"paths": list(_manifest(manifest).files())}

    async def render(
        self,
        manifest: str,
        manifest_path: str,
        commit: str,
        files: list[Any],
        places: dict[str, Any],
    ) -> dict[str, Any]:
        declared = _manifest(manifest)
        texts: dict[str, str | None] = {}
        for entry in files:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
                raise ValueError("`files` are the repository's reading: each a path and content")
            content = entry.get("content")
            text = (
                content if entry.get("encoding") == "utf-8" and isinstance(content, str) else None
            )
            texts[str(entry["path"])] = text
        configured = {
            str(g): tuple(str(n) for n in _names(g, levels)) for g, levels in places.items()
        }
        try:
            pages = render(declared, texts.get, commit, configured)
        except RenderRefused as refused:
            raise ValueError(f"the guides cannot be rendered: {refused}") from refused
        source = Source(file=manifest_path, digest=digest(manifest))
        return {
            "commit": commit,
            "root": list(_root([page.place[:-1] for page in pages])),
            "pages": len(pages),
            "rendered": {
                "manifest": declared.model_dump(mode="json"),
                "manifest_source": source.model_dump(mode="json"),
                "pages": [page.model_dump(mode="json") for page in pages],
            },
        }

    async def measure(self, rendered: dict[str, Any], held: list[Any]) -> dict[str, Any]:
        manifest, source, pages = _rendered(rendered)
        measured = measure(manifest, source, pages, {h.place: h for h in _held(held)})
        return {
            "pages": [m.model_dump(mode="json") for m in measured],
            "write": sum(1 for m in measured if m.action == "write"),
            "keep": sum(1 for m in measured if m.action == "keep"),
            "withhold": sum(1 for m in measured if m.action == "withhold"),
        }

    async def publish(
        self, context: CallContext, rendered: dict[str, Any], held: list[Any]
    ) -> dict[str, Any]:
        manifest, source, pages = _rendered(rendered)
        resolved = await self._connectors.resolve(CAPABILITY)
        if resolved is None:
            raise ValueError(f"no connector serves {CAPABILITY}: no knowledge system is configured")
        counting = _Counting(resolved.connector)
        publication: Publication = await PublishGuidesHandler(counting).execute(
            PublishGuides(
                tenant=context.tenant,
                identity=context.identity,
                run_id=context.run_id,
                manifest=manifest,
                manifest_source=source,
                pages=pages,
                credentials=context.credentials,
                held=tuple(_held(held)),
            )
        )
        return {
            "commit": publication.commit,
            "pages": [p.model_dump(mode="json") for p in publication.pages],
            **publication.counted(),
            "calls": counting.calls,
        }

    async def report(
        self, tenant: str, publication: dict[str, Any], responsible: str, within_days: int
    ) -> dict[str, Any]:
        kept = [
            page
            for page in publication.get("pages", ())
            if isinstance(page, Mapping)
            and page.get("action") == "withheld"
            and page.get("difference")
            and page.get("held")
        ]
        if not kept:
            return {"reports": [], "raised": 0}
        channel = await self._channel.of(tenant)
        if channel is None or responsible not in channel.roles:
            raise ValueError(
                f"{len(kept)} page(s) edited by hand cannot be reported: no owner-facing channel "
                f"of this tenant carries the role {responsible!r} (`taktusctl owner-channel set`)"
            )
        due = self._clock.now().date() + timedelta(days=within_days)
        raised: list[str] = []
        for page in kept:
            place = tuple(str(name) for name in page["place"])
            state = PageState(str(page["state"]))
            try:
                report = await self._raising.execute(
                    RaiseReport(
                        tenant=tenant,
                        id=edits.report_id(
                            str(page["guide"]), str(page["page"]), str(page["held"])
                        ),
                        kind=ReportKind.NEED,
                        title=edits.title(place, state),
                        needed=edits.needed(place),
                        steps=edits.steps(str(page["difference"])),
                        standing_still=edits.standing_still(place),
                        due=due,
                    )
                )
            except ReportingError as error:
                raise ValueError(
                    f"the edit of {'/'.join(place)} was not reported: {error}"
                ) from error
            raised.append(report.id)
        return {"reports": raised, "raised": len(raised)}


class _Counting:
    """The knowledge system's connector, counting the calls made through it: what a
    publication consumed."""

    def __init__(self, connector: ActionConnector) -> None:
        self._connector = connector
        self.calls = 0

    async def capabilities(self) -> Capabilities:
        return await self._connector.capabilities()

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        self.calls += 1
        return await self._connector.call(operation, context, input)


def _manifest(text: str) -> Manifest:
    try:
        return Manifest.model_validate(yaml.safe_load(text))
    except (yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"the guides' manifest does not hold: {error}") from error


def _names(guide: object, levels: object) -> list[object]:
    if not isinstance(levels, list) or not levels:
        raise ValueError(f"the place configured for {guide!r} is a list of names, one per level")
    return levels


def _root(places: list[tuple[str, ...]]) -> tuple[str, ...]:
    """The longest place every guide lies at or below: where one reading finds them all."""
    if not places:
        return ()
    root = places[0]
    for place in places[1:]:
        common = 0
        while common < min(len(root), len(place)) and root[common] == place[common]:
            common += 1
        root = root[:common]
    return root


def _rendered(rendered: Mapping[str, Any]) -> tuple[Manifest, Source, tuple[Page, ...]]:
    try:
        return (
            Manifest.model_validate(rendered["manifest"]),
            Source.model_validate(rendered["manifest_source"]),
            tuple(Page.model_validate(page) for page in rendered["pages"]),
        )
    except (KeyError, TypeError, ValidationError) as error:
        raise ValueError(f"`rendered` is what the render answered: {error}") from error


def _held(held: list[Any]) -> list[Held]:
    """The knowledge system's reading, as `knowledge.pages.list` answered it."""
    try:
        return [
            Held.model_validate(
                {
                    "place": tuple(entry.get("place") or ()),
                    "digest": entry.get("digest"),
                    "mark": entry.get("mark"),
                }
            )
            for entry in held
        ]
    except (AttributeError, TypeError, ValidationError) as error:
        raise ValueError(f"`held` is the knowledge system's reading: {error}") from error
