"""The watch over expected runs in the daemon, against PostgreSQL (ADR-0107, UC-4.16).

One daemon leads the scheduler and runs the runs. Two processes expect a run every hour. The
first is fired by its schedule trigger and its run executes. The scheduler is stopped for the
second: it declares the hourly expectation and has no trigger, so nothing ever fires it. After
the slot and the tenant's grace period, exactly one incident is raised, for the second.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from taktus.adapters.driven.postgres import PostgresRepository
from taktus.components.governance.domain.model import Incident, IncidentKind
from taktus.composition.daemon import Wired

from .test_daemon_scaling import rule_only_bundle, until
from .test_time_triggers import (
    SETTLE,
    Daemon,
    ManualClock,
    _armed,
    daemons,
    eventually,
    registered,
    tenant,
)

__all__ = ["daemons", "tenant"]  # the fixtures, used by name


async def incidents(wired: Wired, tenant: str) -> list[Incident]:
    repository = PostgresRepository(wired.persistence, Incident)
    async with wired.work.transaction(tenant):
        return list(await repository.list(tenant))


async def ended(wired: Wired, tenant: str) -> list[str]:
    async with wired.work.transaction(tenant):
        entries = await wired.ledger.entries(tenant)
    return [e.outcome or "" for e in entries if e.kind == "run.ended"]


async def test_the_scheduler_stopped_for_one_process_raises_exactly_one_incident(
    daemons: Callable[..., Daemon], tenant: str
) -> None:
    clock = ManualClock(datetime(2026, 10, 18, 10, 30, tzinfo=UTC))
    fired = rule_only_bundle(0)
    fired["id"] = f"fired-{tenant}"
    fired["triggers"] = [{"schedule": "hourly"}]
    stopped = rule_only_bundle(1)
    stopped["id"] = f"stopped-{tenant}"
    stopped["expect"] = {"schedule": "hourly"}

    daemon = await daemons("watcher", clock, TAKTUS_ROLES="scheduler,runner").start()
    await until(lambda: daemon.leading)
    assert daemon.wired is not None
    wired = daemon.wired
    await registered(wired, tenant, fired)
    await registered(wired, tenant, stopped)
    # The fired process's trigger arms when the scheduler first sees it, at the time it sees
    # it: the clock moves to the slot only once it has, or the slot is never due.
    await eventually(lambda: _armed(wired, tenant))

    clock.current = datetime(2026, 10, 18, 11, 0, 30, tzinfo=UTC)
    await eventually(lambda: _ended(wired, tenant))
    clock.current = datetime(2026, 10, 18, 11, 14, 0, tzinfo=UTC)
    await asyncio.sleep(SETTLE)
    assert await incidents(wired, tenant) == [], "the grace period has not passed"

    clock.current = datetime(2026, 10, 18, 11, 16, 0, tzinfo=UTC)
    await eventually(lambda: _raised(wired, tenant))
    clock.current = datetime(2026, 10, 18, 11, 18, 0, tzinfo=UTC)
    await asyncio.sleep(SETTLE)
    (incident,) = await incidents(wired, tenant)
    assert incident.kind is IncidentKind.MISSING
    assert incident.process_version == f"stopped-{tenant}@{stopped['version']}"
    assert incident.expected_at == datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
    assert incident.last_run is None, "no run of it ever happened"
    assert await ended(wired, tenant) == ["ok"], "the fired process's run ended, with its outcome"


async def _ended(wired: Wired, tenant: str) -> bool:
    return bool(await ended(wired, tenant))


async def _raised(wired: Wired, tenant: str) -> bool:
    return bool(await incidents(wired, tenant))
