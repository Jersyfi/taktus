"""What the scheduler remembers of one schedule trigger, and the firing it decides (ADR-0035)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.components.process.domain.model.process import ProcessVersion, Trigger
from taktus.components.process.domain.service import schedule
from taktus.shared.v1 import Value


class TriggerState(Value):
    """One schedule trigger of one process, as the scheduler has seen it. The repository key
    is `<process>:<trigger key>`.

    `armed_at` is when the scheduler first saw the trigger: no slot before it fires, so that a
    process registered on a Wednesday does not run for the Monday before. `fired_slot` is the
    latest slot a firing was completed for, and `runs` the runs that firing started."""

    id: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    schedule: str = Field(min_length=1)
    armed_at: datetime
    fired_slot: datetime | None = None
    fired_at: datetime | None = None
    runs: tuple[str, ...] = ()

    @staticmethod
    def key(process_id: str, trigger: Trigger) -> str:
        return f"{process_id}:{trigger.key}"

    def due(self, now: datetime) -> datetime | None:
        """The slot to fire for now, or None. It is the latest slot at or before `now`, if
        that slot is after the trigger was armed and after the slot it last fired for. Slots
        missed in between are not fired one by one: the latest stands for them."""
        slot = schedule.parse(self.schedule).latest(now)
        if slot is None or slot <= self.armed_at:
            return None
        if self.fired_slot is not None and slot <= self.fired_slot:
            return None
        return slot

    def fired(self, slot: datetime, at: datetime, runs: tuple[str, ...]) -> TriggerState:
        return self.model_copy(update={"fired_slot": slot, "fired_at": at, "runs": runs})


class Firing(Value):
    """A schedule trigger that is due: which version it fires, for which slot, and the state
    to record once its runs are started."""

    version: ProcessVersion
    trigger: Trigger
    slot: datetime
    state: TriggerState

    def run_id(self, tenant: str, item: Any = None) -> str:
        """The identifier of the run this firing starts for `item` (None without `each`).
        Derived, never drawn: a scheduler that fires the same slot again — after a restart,
        or a second leader for a moment — names the same run, and the run engine refuses to
        create a run that exists."""
        document = {
            "tenant": tenant,
            "trigger": self.state.id,
            "slot": self.slot.isoformat(),
            "item": item,
        }
        canonical = json.dumps(document, ensure_ascii=False, sort_keys=True)
        return "run_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]

    def triggered(self, item: Any = None) -> dict[str, Any]:
        """What the run records as the trigger that started it."""
        document: dict[str, Any] = {
            "kind": "schedule",
            "trigger": self.state.id,
            "schedule": self.state.schedule,
            "slot": self.slot.isoformat(),
        }
        if self.trigger.each is not None:
            document["item"] = item
        return document
