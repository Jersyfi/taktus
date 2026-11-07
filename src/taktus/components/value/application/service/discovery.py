"""Processes nobody wrote down, through five stages in order (UC-9.4, ADR-0245 §2).

Each stage is a ledger entry `discovery.<stage>` naming the record by digest of its identifier;
a stage is refused unless the one before it is reached. `discovery.decided` carries the person
who decided in `refs.actor`, and Taktus never records it. A pattern found in a person's own
tools or requests is that person's until they agree; nobody else reads it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from taktus.components.value.domain.model import DiscoveredProcess, DiscoveryRefused
from taktus.components.value.domain.model.discovery import AUTOMATION_LEVELS, Stage, next_after
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

TAKTUS = "taktus"
"""The identity Taktus acts as; it may never decide (UC-9.4 §2)."""


def _digest(id: str) -> str:
    return "sha256:" + hashlib.sha256(id.encode("utf-8")).hexdigest()


class Discoveries:
    def __init__(
        self,
        found: Repository[DiscoveredProcess],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        identifiers: Identifiers,
    ) -> None:
        self._found = found
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._identifiers = identifiers

    async def visible(
        self,
        tenant: Tenant,
        *,
        title: str,
        origin: str,
        found: str,
        reader: str | None = None,
        by: str | None = None,
    ) -> DiscoveredProcess:
        """The first stage: made visible. A pattern in a person's own tools or requests names
        that person as its reader."""
        record = DiscoveredProcess.model_validate(
            {
                "id": self._identifiers.new("dsc"),
                "tenant": tenant,
                "title": title,
                "origin": origin,
                "found": found,
                "reader": reader,
                "at": self._clock.now(),
            }
        )
        async with self._work.transaction(tenant):
            await self._found.put(tenant, record)
            await self._record(tenant, record, "visible", by)
        return record

    async def of(self, tenant: Tenant, reader: str) -> list[DiscoveredProcess]:
        """What `reader` may see: the organisation's, and the patterns found for them."""
        async with self._work.transaction(tenant):
            held = await self._found.list(tenant)
        return [d for d in held if d.reader is None or d.reader == reader]

    async def get(self, tenant: Tenant, id: str, reader: str) -> DiscoveredProcess:
        async with self._work.transaction(tenant):
            record = await self._found.get(tenant, id)
        if record is None or (record.reader is not None and record.reader != reader):
            raise DiscoveryRefused("unknown", f"no discovered process {id!r}")
        return record

    async def agree(self, tenant: Tenant, id: str, reader: str) -> DiscoveredProcess:
        """The person a pattern was found for agrees: it becomes the organisation's procedure,
        and their name is no longer on it."""
        record = await self.get(tenant, id, reader)
        if record.reader != reader:
            raise DiscoveryRefused("not_yours", "only the person it was found for agrees")
        changed = record.model_copy(update={"reader": None})
        async with self._work.transaction(tenant):
            await self._found.put(tenant, changed)
        return changed

    async def advance(
        self, tenant: Tenant, id: str, stage: Stage, by: str, **given: Any
    ) -> DiscoveredProcess:
        record = await self.get(tenant, id, by)
        if record.reader is not None:
            raise DiscoveryRefused(
                "not_agreed", "a pattern stays its finder's until they agree to share it"
            )
        if next_after(record.stage) != stage:
            raise DiscoveryRefused(
                "out_of_order", f"{stage} needs the stage after {record.stage} to be next"
            )
        update: dict[str, Any] = {"stage": stage}
        if stage == "documented":
            if not given.get("description") or not given.get("owner_role"):
                raise DiscoveryRefused("incomplete", "documented needs a description and an owner")
            update |= {"description": given["description"], "owner_role": given["owner_role"]}
        elif stage == "valued":
            if given.get("minutes_by_hand") is None or given.get("cases_per_month") is None:
                raise DiscoveryRefused(
                    "incomplete", "valued needs the minutes by hand and the cases a month"
                )
            update["minutes_by_hand"] = float(given["minutes_by_hand"])
            update["cases_per_month"] = float(given["cases_per_month"])
        elif stage == "decided":
            if by == TAKTUS:
                raise DiscoveryRefused("not_a_person", "Taktus never decides to automate")
            if given.get("decision") not in ("automate", "keep"):
                raise DiscoveryRefused("incomplete", "decided needs automate or keep")
            update["decision"] = given["decision"]
        elif stage == "automated":
            if record.decision != "automate":
                raise DiscoveryRefused("not_decided", "a person decided to keep it by hand")
            if given.get("level") not in AUTOMATION_LEVELS:
                raise DiscoveryRefused("level", "a discovered process enters at level 1 or 2")
            if not given.get("instructions"):
                raise DiscoveryRefused(
                    "instructions", "a discovered process carries takeover instructions"
                )
            update["process_id"] = given["process_id"]
        changed = DiscoveredProcess.model_validate({**record.model_dump(), **update})
        async with self._work.transaction(tenant):
            await self._found.put(tenant, changed)
            await self._record(tenant, changed, stage, by)
        return changed

    async def _record(
        self, tenant: Tenant, record: DiscoveredProcess, stage: Stage, by: str | None
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=f"discovery.{stage}",
                refs=LedgerRefs(tenant=tenant, actor=by if stage == "decided" else None),
                outcome=record.decision if stage == "decided" else stage,
                content_digest=_digest(record.id),
            ),
        )


def stages_recorded(entries: Sequence[Any], id: str) -> list[str]:
    """The stages the ledger holds for a discovered process, in order."""
    mark = _digest(id)
    return [
        e.kind.removeprefix("discovery.")
        for e in entries
        if e.kind.startswith("discovery.") and e.content_digest == mark
    ]
