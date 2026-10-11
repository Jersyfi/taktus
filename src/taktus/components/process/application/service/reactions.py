"""Use case of the automation role: which processes an event starts, and with which inputs
(ADR-0048).

The automation role asks, for one event, which active versions of the tenant's processes react
to it. Each process answers with at most one trigger — the first whose kind is the event's and
whose filter holds — so that one event starts a process once (§5). An event received before a
process's active version was registered starts nothing there (§6). Starting the runs is not this
component's: the composition root hands each reaction to the command and run components
(`composition/reactions.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from taktus.components.process.domain.model import Event, Process, ProcessVersion, Trigger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


@dataclass(frozen=True)
class FindReactions:
    tenant: Tenant
    event: Event


@dataclass(frozen=True)
class Reaction:
    """One process an event starts: its active version, the trigger that matched, the inputs
    the run is given."""

    version: ProcessVersion
    trigger: Trigger
    inputs: dict[str, Any]


@dataclass(frozen=True)
class Reactions:
    started: list[Reaction] = field(default_factory=list)
    passed_over: list[str] = field(default_factory=list)
    """Processes whose trigger matched and which the event does not start, each with why: for
    whoever reads the log."""


@dataclass(frozen=True)
class FindTriage:
    """The triage a channel names, asked for one contribution received at `received_at`
    (ADR-0088)."""

    tenant: Tenant
    process: str
    received_at: datetime


@dataclass(frozen=True)
class Triage:
    """The triage's active version and the identity that registered it, whom the run acts for;
    or, in `waits`, why it does not start now, and in `passed_over`, why it never starts for
    this contribution."""

    version: ProcessVersion | None = None
    by: str | None = None
    waits: str | None = None
    passed_over: str | None = None


class ReactionsHandler:
    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._work = work

    async def find(self, query: FindReactions) -> Reactions:
        event = query.event
        found = Reactions()
        async with self._work.transaction(query.tenant):
            for process in await self._processes.list(query.tenant):
                if process.active_version is None:
                    continue
                ref = f"{process.id}@{process.active_version}"
                version = await self._versions.get(query.tenant, ref)
                if version is None:
                    continue
                trigger = version.reacting_to(event)
                if trigger is None:
                    continue
                if process.activated_at is None:
                    found.passed_over.append(
                        f"{ref}: registered before versions recorded when they became active; "
                        "register it again for its event triggers to start it"
                    )
                    continue
                if event.received_at < process.activated_at:
                    found.passed_over.append(
                        f"{ref}: the event was received before the version became active"
                    )
                    continue
                found.started.append(
                    Reaction(
                        version=version, trigger=trigger, inputs=version.given_by(trigger, event)
                    )
                )
        return found

    async def triage(self, query: FindTriage) -> Triage:
        """The version a contribution starts, by the process the channel names — no trigger
        is matched (UC-4.14 stands) — and whom it acts for. A process without an active
        version, or registered by nobody, makes the contribution wait; a contribution received
        before the version became active starts nothing (ADR-0048 §6)."""
        async with self._work.transaction(query.tenant):
            process = await self._processes.get(query.tenant, query.process)
            if process is None or process.active_version is None:
                return Triage(waits=f"no version of {query.process!r} is active")
            ref = f"{process.id}@{process.active_version}"
            version = await self._versions.get(query.tenant, ref)
        if version is None:
            return Triage(waits=f"{ref} is not registered")
        if process.activated_by is None:
            return Triage(waits=f"{ref} was registered by no identity; nothing acts without one")
        if process.activated_at is None or query.received_at < process.activated_at:
            return Triage(passed_over=f"{ref}: the contribution was received before it was active")
        return Triage(version=version, by=process.activated_by)
