"""Every ended run measured against its process's objectives, and a failure healed again and
again said (UC-4.6, ADR-0254), over the memory stores.

What is real: registration, the ledger, the owner-facing channel as the composition root wires
it, the governance component's rule, the watch. The runs are their ledger entries, as the engine
writes them: `run.created`, `run.finished` or `run.escalated`, and `step.healed` with the
failure it answered stored by digest.

What is proven: a run that took longer than its process promises, or that brings the share of
finished runs below the promise, is recorded with the objective it missed, and one that kept
both as met, each once; a process without objectives is not measured; the same failure healed
the process's limit of times is recorded once and said to the owner, another failure is
counted apart; the limit is configurable and cannot be switched off.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from fakes.owner_channel import OWNER, TENANT, owner_channel
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryObjectStore, MemoryRepository
from taktus.components.governance.domain.service import objectives as rule
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.components.reporting.domain.model import ReportKind
from taktus.composition.objectives import ObjectivesWatch
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs


def bundle(**more: Any) -> dict[str, Any]:
    return instructed(
        {
            "id": "nightly",
            "version": "1",
            "name": "Nightly",
            "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
            "steps": [
                {
                    "id": "fetch",
                    "method": "rule",
                    "reason": "a fixed value",
                    "rejected": [],
                    "exactness": "exact",
                    "checks": [{"kind": "recomputation"}],
                    "work": {"rule": "constant", "value": 1},
                }
            ],
            **more,
        }
    )


class World:
    def __init__(self) -> None:
        self.given = owner_channel()
        self.persistence = self.given.persistence
        self.clock = self.given.clock
        self.ledger = self.given.identity.ledger
        self.objects = MemoryObjectStore()
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.watch = ObjectivesWatch(
            ledger=self.ledger,
            versions=self.versions,
            objects=self.objects,
            work=self.persistence,
            clock=self.clock,
            channels=self.given.owner.channel,
            raising=self.given.owner.raising,
        )
        self.runs = 0

    async def registered(self, **more: Any) -> World:
        await self.given.configure()
        await RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
        ).execute(RegisterProcessVersion(bundle(**more), tenant=TENANT, by=OWNER))
        return self

    async def record(self, kind: str, run: str | None, **more: Any) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=TENANT, run_id=run, process_version="nightly@1", step_id="fetch"
                    ),
                    **more,
                ),
            )

    async def run(self, *, took: timedelta, finished: bool = True) -> str:
        self.runs += 1
        run_id = f"run_{self.runs}"
        await self.record("run.created", run_id)
        self.clock.current += took
        await self.record(
            "run.finished" if finished else "run.escalated",
            run_id,
            outcome="finished" if finished else "failure",
        )
        return run_id

    async def heal(self, failure: str, attempt: int) -> None:
        self.runs += 1
        stored = json.dumps({"failure": failure, "action": "retry", "attempt": attempt})
        digest = await self.objects.put(stored.encode())
        await self.record("step.healed", f"run_{self.runs}", outcome="retry", content_digest=digest)

    async def outcomes(self, kind: str) -> list[str | None]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.of_kinds(TENANT, (kind,))
        return [e.outcome for e in entries]


async def test_a_run_slower_than_promised_is_recorded_with_the_objective_it_missed() -> None:
    world = await World().registered(slo={"latency": "10m"})
    quick = await world.run(took=timedelta(minutes=2))
    slow = await world.run(took=timedelta(minutes=12))
    done = await world.watch.look(TENANT)
    assert done.measured == ((quick, "met"), (slow, "missed_latency"))
    assert (await world.watch.look(TENANT)).measured == (), "each run once"


async def test_a_share_of_finished_runs_below_the_promise_is_missed_by_the_run_that_lowers_it() -> (
    None
):
    world = await World().registered(slo={"completion": 0.75})
    for _ in range(3):
        await world.run(took=timedelta(minutes=1))
    escalated = await world.run(took=timedelta(minutes=1), finished=False)
    second = await world.run(took=timedelta(minutes=1), finished=False)
    done = dict((await world.watch.look(TENANT)).measured)
    assert done[escalated] == "met", "three of four finished: the share is 0.75"
    assert done[second] == "missed_completion", "three of five finished"


async def test_a_process_without_objectives_is_not_measured() -> None:
    world = await World().registered()
    await world.run(took=timedelta(hours=5))
    assert (await world.watch.look(TENANT)).measured == ()
    assert await world.outcomes("slo.measured") == []


async def test_the_same_failure_healed_three_times_is_said_once_and_another_is_apart() -> None:
    world = await World().registered()
    await world.heal("the service answered 503", 1)
    await world.heal("the service answered 503", 2)
    await world.heal("the disk was full", 1)
    assert (await world.watch.look(TENANT)).recurred == ()
    await world.heal("the service answered 503", 1)
    assert (await world.watch.look(TENANT)).recurred == (("nightly", "fetch"),)
    await world.heal("the service answered 503", 3)
    assert (await world.watch.look(TENANT)).recurred == (), "said once"
    assert await world.outcomes("heal.recurred") == ["proposed"]
    reports = [r for r in await world.given.owner.queries.reports(TENANT)]
    (said,) = [r for r in reports if r.id.startswith("recurred-")]
    assert said.kind is ReportKind.FAILURE and "design fault" in said.title


async def test_the_limit_is_the_processs_and_cannot_be_switched_off() -> None:
    world = await World().registered(heal_limit=1)
    await world.heal("the service answered 503", 1)
    assert (await world.watch.look(TENANT)).recurred == (("nightly", "fetch"),)
    assert parse_bundle(bundle()).heal_limit == rule.HEAL_LIMIT == 3
    for off in (0, -1):
        with pytest.raises(InvalidProcess):
            parse_bundle(bundle(heal_limit=off))
    with pytest.raises(InvalidProcess):
        parse_bundle(bundle(slo={"completion": 1.5}))
