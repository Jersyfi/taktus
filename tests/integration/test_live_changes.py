"""A change of state reaches its reader within 5 seconds, across two processes (ADR-0055 §7).

Two daemons serve the `api` role against one PostgreSQL database, as two replicas would. The
reader opens its stream on the first, over HTTP. The second — which also runs the runner —
records the changes: a step started and completed, a step failed, a run halted, a decision
awaited. Each must arrive within 5 seconds of being recorded. Then again with the notification
dropped: the trigger that sends it is disabled, and the interval read alone must hold the bound.
A reader that reconnects to the other replica with its last position receives every change
after it, once.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, text

from taktus.adapters.driven.postgres.url import for_sqlalchemy
from taktus.components.governance.application.service import ConfigureAnchors
from taktus.components.run.domain.model import RunState
from taktus.composition.daemon import Wired

from .test_daemon_scaling import Instance, instances, rule_only_bundle, submit, until

__all__ = ["instances"]

BOUND_SECONDS = 5.0
NAMED = ("step.started", "step.finished", "run.halted", "decision.raised", "step.anchored")


def tenant() -> str:
    return f"live-{os.getpid()}-{datetime.now(UTC).strftime('%H%M%S%f')}"


class Reading:
    """One stream read over HTTP in the background: every event with the moment it arrived."""

    def __init__(self, url: str, key: str, last: str | None = None) -> None:
        self.url = url
        self.headers = {"Authorization": f"Bearer {key}"}
        if last is not None:
            self.headers["Last-Event-ID"] = last
        self.events: list[tuple[str, dict[str, Any], datetime]] = []
        self.task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Reading:
        self.task = asyncio.create_task(self._read())
        await until(lambda: bool(self.events), seconds=15)
        return self

    async def __aexit__(self, *_: object) -> None:
        assert self.task is not None
        self.task.cancel()

    async def _read(self) -> None:
        async with (
            # No read timeout: a stream is quiet between changes; the test bounds it instead.
            httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None)) as http,
            http.stream("GET", self.url, headers=self.headers) as response,
        ):
            assert response.status_code == 200, await response.aread()
            name = ""
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    name = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    data = json.loads(line.removeprefix("data: "))
                    self.events.append((name, data, datetime.now(UTC)))

    def changes(self) -> list[dict[str, Any]]:
        return [data for name, data, _ in self.events if name == "change"]

    def late(self) -> list[str]:
        """Every change that arrived more than the bound after it was recorded."""
        late = []
        for name, data, arrived in self.events:
            if name != "change":
                continue
            recorded = datetime.fromisoformat(data["recorded_at"])
            if (arrived - recorded).total_seconds() > BOUND_SECONDS:
                late.append(f"{data['kind']} after {(arrived - recorded).total_seconds():.1f}s")
        return late


def bundle(n: int, *, level: int = 3, fail: bool = False, name: str = "live") -> dict[str, Any]:
    document = rule_only_bundle(n)
    document["id"] = f"{name}-{os.getpid()}-{n}"
    document["autonomy"] = {"level": level, "reason": "test", "toward_next": "-"}
    if fail:
        document["steps"][1]["work"] = {"rule": "check", "conditions": [{"value": 1, "equals": 2}]}
    return document


async def reader_key(wired: Wired, chosen: str) -> str:
    _, key = await wired.identities.add(chosen, "idn_reader", (chosen,))
    return key


def url(instance: Instance) -> str:
    return f"http://127.0.0.1:{instance.settings.http_port}/changes"


async def record_the_named_changes(writer: Wired, chosen: str) -> None:
    """Through the second process: a step started and completed, a step failed, a run
    halted, a decision awaited."""
    done = await submit(writer, bundle(1), tenant=chosen)
    failing = await submit(writer, bundle(2, fail=True), tenant=chosen)
    waiting = await submit(writer, bundle(3, level=2), tenant=chosen)
    anchored = bundle(4, name="anchored")
    await writer.decisions.configure.execute(
        ConfigureAnchors(
            tenant=chosen,
            document={
                "anchors": [
                    {
                        "id": "anc-live",
                        "class": "legal",
                        "act": "every act of this process",
                        "applies_to": {"processes": [anchored["id"]]},
                        "decider": {"role": "finance.lead"},
                    },
                    {
                        "id": "anc-correction",
                        "class": "correction",
                        "act": "correct a result that left",
                        "applies_to": {"actions": ["correction.*"]},
                        "decider": {"role": "finance.lead"},
                    },
                ]
            },
            actor="idn_reader",
        )
    )
    held = await submit(writer, anchored, tenant=chosen)

    async def state(run_id: str) -> RunState:
        async with writer.work.transaction(chosen):
            found = await writer.runs.get(chosen, run_id)
        assert found is not None
        return found.state

    states: dict[str, RunState] = {}

    async def settled() -> bool:
        for run in (done, failing, waiting, held):
            states[run.id] = await state(run.id)
        return states[done.id] is RunState.FINISHED and all(
            states[r.id] in (RunState.ESCALATED, RunState.WAITING_HUMAN)
            for r in (failing, waiting, held)
        )

    async with asyncio.timeout(30):
        while not await settled():  # noqa: ASYNC110 — polling another process's state
            await asyncio.sleep(0.1)
    await writer.engine.request_stop(waiting.id, chosen)


@pytest.fixture
def chosen(postgres_url: str) -> str:
    """A tenant of its own, so that the anchors it configures touch no other test."""
    made = tenant()
    engine = create_engine(for_sqlalchemy(postgres_url))
    with engine.begin() as connection:
        connection.execute(text("SELECT set_config('taktus.tenant', :t, true)"), {"t": made})
        connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"), {"t": made}
        )
    engine.dispose()
    return made


async def test_changes_recorded_through_another_process_arrive_within_5_seconds(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with (
        instances("api-a", TAKTUS_ROLES="api", TAKTUS_TENANTS=chosen) as a,
        instances("api-b", TAKTUS_ROLES="api,runner", TAKTUS_TENANTS=chosen) as b,
    ):
        assert a.wired is not None and b.wired is not None
        key = await reader_key(b.wired, chosen)
        async with Reading(url(a), key) as reading:
            await record_the_named_changes(b.wired, chosen)
            await until(lambda: "run.halted" in {c["kind"] for c in reading.changes()}, seconds=10)
            await asyncio.sleep(1)
            kinds = {c["kind"] for c in reading.changes()}
            assert set(NAMED) <= kinds, f"missing {set(NAMED) - kinds}"
            outcomes = {c.get("outcome") for c in reading.changes() if c["kind"] == "step.finished"}
            assert {"succeeded", "failed"} <= outcomes
            assert not reading.late(), reading.late()
            for change in reading.changes():
                assert "actor" not in change and "consumption" not in change


@pytest.fixture
def no_notification(postgres_url: str) -> Callable[[], Any]:
    """Disable the trigger that notifies, for the length of a test; enable it again after."""
    engine = create_engine(for_sqlalchemy(postgres_url))

    def toggle(enabled: bool) -> None:
        with engine.begin() as connection:
            verb = "ENABLE" if enabled else "DISABLE"
            connection.execute(
                text(f"ALTER TABLE ledger_entry {verb} TRIGGER ledger_entry_notifies")
            )

    def dropped() -> Any:
        toggle(False)
        return lambda: toggle(True)

    return dropped


async def test_with_the_notification_dropped_changes_arrive_within_the_same_bound(
    instances: Callable[..., Instance], chosen: str, no_notification: Callable[[], Any]
) -> None:
    async with (
        instances("api-a", TAKTUS_ROLES="api", TAKTUS_TENANTS=chosen) as a,
        instances("api-b", TAKTUS_ROLES="api,runner", TAKTUS_TENANTS=chosen) as b,
    ):
        assert a.wired is not None and b.wired is not None
        key = await reader_key(b.wired, chosen)
        restore = no_notification()
        try:
            async with Reading(url(a), key) as reading:
                await record_the_named_changes(b.wired, chosen)
                await until(
                    lambda: "run.halted" in {c["kind"] for c in reading.changes()}, seconds=10
                )
                await asyncio.sleep(1)
                kinds = {c["kind"] for c in reading.changes()}
                assert set(NAMED) <= kinds, f"missing {set(NAMED) - kinds}"
                assert not reading.late(), reading.late()
        finally:
            restore()


async def test_a_reader_that_reconnects_to_another_replica_misses_nothing_and_sees_nothing_twice(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with (
        instances("api-a", TAKTUS_ROLES="api", TAKTUS_TENANTS=chosen) as a,
        instances("api-b", TAKTUS_ROLES="api,runner", TAKTUS_TENANTS=chosen) as b,
    ):
        assert a.wired is not None and b.wired is not None
        key = await reader_key(b.wired, chosen)
        first = await submit(b.wired, bundle(1), tenant=chosen)
        async with Reading(url(a), key) as reading:
            await until(lambda: any(c["run"] == first.id for c in reading.changes()), seconds=10)
            last = reading.changes()[-1]["position"]
        # Away: more is recorded while nobody reads.
        second = await submit(b.wired, bundle(2), tenant=chosen)
        await until_finished(b.wired, chosen, second.id)
        async with Reading(url(b), key, last=last) as resumed:
            await until(
                lambda: any(
                    c["run"] == second.id and c["kind"] == "run.finished" for c in resumed.changes()
                ),
                seconds=10,
            )
            assert resumed.events[0][0] == "change", "a known position resumes; no snapshot"
            received = [c["position"] for c in resumed.changes()]
            assert len(received) == len(set(received)), "none twice"
            async with b.wired.work.transaction(chosen):
                entries = await b.wired.ledger.entries(chosen)
            after = [e for e in entries if e.seq > next(x.seq for x in entries if x.hash == last)]
            sent = [e.hash for e in after if e.kind in {c["kind"] for c in resumed.changes()}]
            assert received[: len(sent)] == sent, "every change after the position, in order"


async def until_finished(wired: Wired, chosen: str, run_id: str) -> None:
    async def finished() -> bool:
        async with wired.work.transaction(chosen):
            run = await wired.runs.get(chosen, run_id)
        return run is not None and run.state is RunState.FINISHED

    async with asyncio.timeout(30):
        while not await finished():  # noqa: ASYNC110 — polling another process's state
            await asyncio.sleep(0.1)
