"""A cap on a process's open work (UC-8.12, ADR-0132 §1 to §2).

A process declares how many of its outcomes of a kind may wait at once. Before a run of it
starts anything, the run counts those open outside, through a connector's read, and the
process's runs in flight; at the cap it waits, booked to `wait.external` with its reason, and
counts again at the cap's next check. The rule reads facts and decides; no model takes part.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from fakes import FakeConnector
from fakes.connector import READ, WRITE
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.model.block import AT_OPEN_WORK_CAP
from taktus.components.run.domain.service import open_work
from taktus.components.run.ports import Cap, CountReading
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .test_connector_steps import CREDENTIALS, ConnectorHarness, call
from .test_engine import BUDGET, TENANT, rule

CHECK = 900.0
OPEN_PRS = {"id": "open-pull-requests"}


class CapsOf:
    def __init__(self, *caps: Cap) -> None:
        self._caps = caps

    async def caps(self, tenant: str, process_version: str) -> tuple[Cap, ...]:
        return self._caps


def pull_requests(cap: int = 2, *, read: bool = True) -> Cap:
    return Cap(
        kind="pull_requests",
        cap=cap,
        reading=CountReading.model_validate(
            {
                "operation": READ,
                "input": OPEN_PRS,
                "credentials": CREDENTIALS,
                "select": "pull_requests",
            }
        )
        if read
        else None,
        check_every_seconds=CHECK,
    )


class CappedHarness(ConnectorHarness):
    def __init__(self, *caps: Cap, connector: FakeConnector | None = None) -> None:
        super().__init__(
            rule("prep", {"rule": "constant", "value": {"title": "a change"}}),
            call("open", WRITE, {"title": {"$from": "prep", "$select": "title"}}, after=("prep",)),
            connector=connector,
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=self.engine._workers,
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            connectors=StaticConnectorPool([("connector.fake", self.connector)]),
            options=self.engine._options,
            open_work=CapsOf(*caps),
        )

    def open_outside(self, count: int) -> None:
        self.connector.reads[OPEN_PRS["id"]] = {"pull_requests": list(range(count))}

    async def facts(self, run: Run, kind: str) -> dict[str, Any]:
        entry = next(e for e in reversed(await self.entries(run)) if e.kind == kind)
        assert entry.content_digest is not None
        content = await self.objects.get(entry.content_digest)
        assert content is not None
        document: dict[str, Any] = json.loads(content)
        return document


async def test_a_cap_of_two_with_two_open_pull_requests_finds_the_third_run_waiting() -> None:
    h = CappedHarness(pull_requests(2))
    h.open_outside(2)
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.PARKED
    assert h.connector.acted == 0, "the run started nothing"
    held = run.step_run("prep")
    assert held.state is StepState.PLANNED
    assert held.block is not None and held.block.next_check_at is not None
    assert held.block.cause == AT_OPEN_WORK_CAP and held.block.account == "wait.external"
    assert held.block.next_check_at - held.block.since == timedelta(seconds=CHECK)
    assert "pull_requests: 2 of 2 (2 open outside, 0 run(s) in flight)" in (run.reason or "")
    # The wait is booked with its reason: the facts the rule read, by digest.
    assert "open_work.capped:prep:capped" in await h.kinds(run)
    facts = await h.facts(run, open_work.CAPPED)
    assert facts["rule"] == "open_work.cap"
    assert facts["kinds"]["pull_requests"] == {
        "kind": "pull_requests",
        "cap": 2,
        "read": 2,
        "in_flight": 0,
    }

    # One closes; at the next check the run is admitted, and its wait ends with its record.
    h.open_outside(1)
    h.clock.current += timedelta(seconds=CHECK)
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    assert h.connector.acted == 1
    kinds = await h.kinds(run)
    assert "open_work.admitted::admitted" in kinds
    assert "step.waited:prep:at_open_work_cap" in kinds
    assert kinds.index("open_work.admitted::admitted") < kinds.index("step.started:prep")
    waited = next(e for e in await h.entries(run) if e.kind == "step.waited")
    assert waited.content_digest is not None
    record = json.loads(await h.objects.get(waited.content_digest) or b"{}")
    assert record["account"] == "wait.external" and record["cause"] == AT_OPEN_WORK_CAP
    assert record["seconds"] >= CHECK
    assert await h.verify()


async def test_a_run_in_flight_counts_until_it_ends() -> None:
    h = CappedHarness(pull_requests(1, read=False))
    first = await h.start(stop_after=1)
    assert first.state is RunState.HALTED and first.cause is Cause.STOP
    second = await h.start()
    assert second.state is RunState.HALTED and second.cause is Cause.PARKED
    assert "pull_requests: 1 of 1 (1 run(s) in flight)" in (second.reason or "")
    first = await h.resume(first)
    assert first.state is RunState.FINISHED
    second = await h.resume(second)
    assert second.state is RunState.FINISHED


async def test_a_run_that_passed_is_not_held_by_itself_when_it_is_recovered() -> None:
    h = CappedHarness(pull_requests(1, read=False))
    run = await h.start(stop_after=1)
    assert run.state is RunState.HALTED
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    assert [k for k in await h.kinds(run) if k.startswith("open_work")] == [
        "open_work.admitted::admitted"
    ]


async def test_a_count_that_cannot_be_read_holds_the_run() -> None:
    h = CappedHarness(pull_requests(5))
    h.connector.unreachable = "the code host did not answer"
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.PARKED
    assert "could not be read" in (run.reason or "")
    assert h.connector.acted == 0


class Held:
    """The tenant's stops of adapters, as the engine reads them (ADR-0138)."""

    def __init__(self, *adapters: str) -> None:
        self._adapters = frozenset(adapters)

    async def held(self, tenant: str) -> frozenset[str]:
        return self._adapters


async def test_a_stopped_connector_is_not_called_for_a_count_and_the_run_waits() -> None:
    """A stop of the cap's connector keeps the count from being read through it (ADR-0138,
    amendment): the count is unread, and the run waits at the cap, as for any unread count."""
    h = CappedHarness(pull_requests(5))
    h.engine._stops = Held("connector.fake")  # type: ignore[assignment]
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.PARKED
    assert "connector.fake is stopped" in (run.reason or "")
    assert h.connector.calls == [], "nothing was called"


async def test_a_rehearsal_is_neither_capped_nor_counted() -> None:
    h = CappedHarness(pull_requests(1))
    h.open_outside(3)
    run = await h.engine.start(
        StartRun(
            plan=h.plan(),
            work=h.work,
            budget=BUDGET,
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
            rehearsal=True,
        )
    )
    assert run.cause is not Cause.PARKED
    assert not [k for k in await h.kinds(run) if k.startswith("open_work")]


async def test_the_runs_in_flight_projection_equals_the_full_computation() -> None:
    h = CappedHarness(pull_requests(3, read=False))
    first = await h.start(stop_after=1)
    await h.start()
    await h.resume(first)
    async with h.persistence.transaction(TENANT):
        entries = await h.ledger.entries(TENANT)
        projected = await h.ledger.project(TENANT, open_work.IN_FLIGHT)
        rebuilt = await h.ledger.rebuilt(TENANT, open_work.IN_FLIGHT)
    assert projected == rebuilt == open_work.in_flight(entries)
    assert projected.of("p") == frozenset()


def test_a_reading_counts_a_list_or_a_number_and_nothing_else() -> None:
    assert open_work.counted_from({"items": [1, 2, 3]}, "items") == 3
    assert open_work.counted_from({"total": 4}, "total") == 4
    assert open_work.counted_from([1], None) == 1
    for output, select in (({"total": "4"}, "total"), ({"x": 1}, "items"), ({"t": True}, "t")):
        try:
            open_work.counted_from(output, select)
        except ValueError:
            continue
        raise AssertionError(f"{output!r} at {select!r} counted")


async def test_a_run_that_passed_while_another_counted_is_counted_by_it() -> None:
    """Another runner's run of the process passes between this run's first read of the runs in
    flight and its own entry: under the tenant's ledger lock the run reads them again, counts
    once more, and finds the cap reached."""
    h = CappedHarness(pull_requests(2))
    h.open_outside(1)
    reading = h.connector.call

    async def passing_meanwhile(operation: str, context: Any, input: Any) -> Any:
        if operation == READ:
            async with h.persistence.transaction(TENANT):
                await h.ledger.record(
                    TENANT,
                    Fact(
                        kind=open_work.ADMITTED,
                        refs=LedgerRefs(tenant=TENANT, process_version="p@1", run_id="run_other"),
                        outcome="admitted",
                    ),
                )
        return await reading(operation, context, input)

    h.connector.call = passing_meanwhile  # type: ignore[method-assign]
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.PARKED
    assert "pull_requests: 2 of 2 (1 open outside, 1 run(s) in flight)" in (run.reason or "")
    assert not [k for k in await h.kinds(run) if k.startswith("open_work.admitted")]
