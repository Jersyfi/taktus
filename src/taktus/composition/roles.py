"""The four roles as coroutines over the wired services (docs/architecture/project-structure.md
§5). Each takes a `stop` event and returns once it has wound down.

- `runner` executes runs it claims from the queue — the run component's `Runner`; stopping
  it is the shutdown of ADR-0005: no new claim, the running step reaches its boundary, the
  claim is released.
- `scheduler` is singular: it leads through the leadership port, and while it leads it ticks.
  A second instance keeps trying and takes over when the leader's lead is gone. The daemon's
  tick fires the time triggers that are due (`triggers.py`, ADR-0035) and makes the capacity
  report (`capacity.py`); deadlines and budget windows arrive with governance.
- `automation` is singular too: it leads under its own name, and while it leads it reacts to
  the events the intake kept, through the outbox (`reactions.py`, ADR-0048).
- `api` is the HTTP surface and is started by the daemon itself, not here: every process
  serves health and readiness whatever its roles, and the `api` role adds the rest.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from taktus.components.run.application.service import Runner
from taktus.ports.clock import Clock
from taktus.ports.leadership import Leadership

SCHEDULER = "scheduler"
AUTOMATION = "automation"

log = structlog.get_logger("taktusd")


async def run_runner(runner: Runner, stop: asyncio.Event) -> None:
    """Runs until `stop`; then no new claim, and every run lands at its boundary."""
    loop = asyncio.create_task(runner.run(), name="runner")
    await stop.wait()
    log.info("runner stopping", executing=runner.executing)
    await runner.stop()
    await loop
    log.info("runner stopped", outcomes=len(runner.outcomes))


async def run_scheduler(
    leadership: Leadership,
    clock: Clock,
    stop: asyncio.Event,
    *,
    poll_seconds: float,
    tick: Callable[[], Awaitable[None]] | None = None,
    on_lead: Callable[[bool], None] | None = None,
) -> None:
    """Try to lead; while leading, tick every `poll_seconds` as long as the lead is held; on
    losing it, step down and try again. `on_lead(True|False)` reports transitions to whoever
    watches (the test, the readiness page)."""
    while not stop.is_set():
        lead = await leadership.try_lead(SCHEDULER)
        if lead is None:
            await _pause(clock, stop, poll_seconds)
            continue
        log.info("scheduler leading")
        if on_lead is not None:
            on_lead(True)
        try:
            while not stop.is_set():
                if not await lead.held():
                    log.warning("scheduler lost the lead")
                    break
                if tick is not None:
                    await tick()
                else:
                    log.debug("scheduler tick", scheduled=0)
                await _pause(clock, stop, poll_seconds)
        finally:
            if on_lead is not None:
                on_lead(False)
            await lead.release()
            log.info("scheduler stepped down")


async def run_automation(
    leadership: Leadership,
    clock: Clock,
    stop: asyncio.Event,
    *,
    poll_seconds: float,
    tick: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Lead under the name `automation`, as the scheduler leads under its own; while leading,
    react to the events the intake kept every `poll_seconds` (ADR-0048 §3). A second instance
    keeps trying and takes over when the leader's lead is gone."""
    log.info("automation started")
    while not stop.is_set():
        lead = await leadership.try_lead(AUTOMATION)
        if lead is None:
            await _pause(clock, stop, poll_seconds)
            continue
        log.info("automation leading")
        try:
            while not stop.is_set():
                if not await lead.held():
                    log.warning("automation lost the lead")
                    break
                if tick is not None:
                    await tick()
                await _pause(clock, stop, poll_seconds)
        finally:
            await lead.release()
            log.info("automation stepped down")
    log.info("automation stopped")


async def _pause(clock: Clock, stop: asyncio.Event, seconds: float) -> None:
    """Sleep through the clock, but wake at once when `stop` is set."""
    sleeper = asyncio.ensure_future(clock.sleep(seconds))
    waker = asyncio.ensure_future(stop.wait())
    _, pending = await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
