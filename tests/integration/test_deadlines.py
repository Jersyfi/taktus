"""A deadline survives a restart of the instance (UC-4.17 §2, ADR-0133), against PostgreSQL.

One daemon leads the scheduler and runs the runs. Its schedule trigger starts a case that waits
for a person's answer, and the case's deadline starts with it. The daemon stops before the
deadline falls due, and another daemon starts. At the limit the new leader escalates the case
to its role, once, and never again however long it leads.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from taktus.composition.daemon import Wired
from taktus.shared.v1 import LedgerEntry

from .test_daemon_scaling import rule_only_bundle, until
from .test_time_triggers import (
    SETTLE,
    Daemon,
    ManualClock,
    daemons,
    eventually,
    registered,
    runs_of,
    tenant,
)

__all__ = ["daemons", "tenant"]  # the fixtures, used by name


async def deadline_entries(wired: Wired, tenant: str) -> list[LedgerEntry]:
    async with wired.work.transaction(tenant):
        entries = await wired.ledger.entries(tenant)
    return [e for e in entries if e.kind.startswith("deadline.")]


async def test_a_deadline_started_before_a_restart_escalates_once_at_its_limit(
    daemons: Callable[..., Daemon], tenant: str
) -> None:
    clock = ManualClock(datetime(2026, 10, 21, 10, 30, tzinfo=UTC))
    bundle = rule_only_bundle(0)
    bundle["id"] = f"case-{tenant}"
    bundle["autonomy"] = {"level": 2, "reason": "a person answers", "toward_next": "-"}
    bundle["triggers"] = [{"schedule": "0 11 * * *"}]  # once a day: one case
    bundle["deadlines"] = {
        "first_answer": {
            "from": "run",
            "limit": "1h",
            "until": {"step": "two"},
            "at_limit": {"escalate": "support-lead"},
        }
    }

    first = await daemons("first", clock, TAKTUS_ROLES="scheduler,runner").start()
    await until(lambda: first.leading)
    assert first.wired is not None
    version = await registered(first.wired, tenant, bundle)
    await asyncio.sleep(SETTLE)

    clock.current = datetime(2026, 10, 21, 11, 0, 30, tzinfo=UTC)
    wired = first.wired

    async def started() -> bool:
        return [e.kind for e in await deadline_entries(wired, tenant)] == ["deadline.started"]

    await eventually(started)
    (case,) = await runs_of(wired, tenant, version.ref)
    due = case.created_at + timedelta(hours=1)

    # The instance stops before the limit; another starts and leads.
    await first.halt()
    second = await daemons("second", clock, TAKTUS_ROLES="scheduler,runner").start()
    await until(lambda: second.leading)
    assert second.wired is not None
    wired = second.wired
    clock.current = due - timedelta(seconds=1)
    await asyncio.sleep(SETTLE)
    assert [e.kind for e in await deadline_entries(wired, tenant)] == ["deadline.started"]

    clock.current = due

    async def reached() -> bool:
        return any(e.kind == "deadline.reached" for e in await deadline_entries(wired, tenant))

    await eventually(reached)
    clock.current = due + timedelta(hours=3)
    await asyncio.sleep(SETTLE)
    entries = await deadline_entries(wired, tenant)
    assert [(e.kind, e.outcome) for e in entries] == [
        ("deadline.started", "calendar"),
        ("deadline.reached", "escalate"),
    ], "carried out once"
    escalated = entries[1]
    assert escalated.refs.run_id == case.id and escalated.ts == due, "on time, for its case"
    (listed,) = await wired.decisions.deadlines.listing(tenant, role="support-lead")
    assert listed["run"] == case.id and listed["overdue"] is True
