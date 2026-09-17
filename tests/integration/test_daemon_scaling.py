"""Horizontal scaling, proven rather than claimed (ADR-0002, ADR-0013 A).

Two daemons run in this process against one PostgreSQL database, as two containers would.
Runners: every submitted run is executed exactly once, and both took part. Schedulers: exactly
one leads; when it stops, the other takes over.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import RegisterProcessVersion
from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.daemon import Wired, serve
from taktus.composition.settings import Settings, load
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo

from .conftest import free_port
from .test_first_slice import EXAMPLE

TENANT = "default"


def settings(postgres_url: str, tmp_path: Path, **environment: str) -> Settings:
    return load(
        EnvironmentConfiguration(
            {
                "TAKTUS_DATABASE_URL": postgres_url,
                "TAKTUS_STATE_DIR": str(tmp_path / "state"),
                "TAKTUS_POLL_SECONDS": "0.05",
                "TAKTUS_LEASE_SECONDS": "5",
                **environment,
            }
        ),
        default_instance="test",
    )


class Instance:
    """One daemon, served in a task of this process."""

    def __init__(self, configured: Settings) -> None:
        self.settings = configured
        self.stop = asyncio.Event()
        self.wired: Wired | None = None
        self.task: asyncio.Task[int] | None = None

    async def __aenter__(self) -> Instance:
        started = asyncio.Event()

        def on_wired(wired: Wired) -> None:
            self.wired = wired
            started.set()

        self.task = asyncio.create_task(
            serve(self.settings, stop=self.stop, on_wired=on_wired), name=self.settings.instance
        )
        await asyncio.wait_for(started.wait(), timeout=30)
        return self

    async def __aexit__(self, *_: object) -> None:
        self.stop.set()
        assert self.task is not None
        assert await asyncio.wait_for(self.task, timeout=30) == 0

    @property
    def leading(self) -> bool:
        return self.wired is not None and self.wired.leading


@pytest.fixture
async def instances(postgres_url: str, tmp_path: Path) -> AsyncIterator[Callable[..., Instance]]:
    made: list[Instance] = []

    def make(name: str, **environment: str) -> Instance:
        instance = Instance(
            settings(
                postgres_url,
                tmp_path,
                TAKTUS_INSTANCE=name,
                TAKTUS_HTTP_PORT=str(free_port()),
                **environment,
            )
        )
        made.append(instance)
        return instance

    yield make
    for instance in made:
        if instance.task is not None and not instance.task.done():
            instance.stop.set()
            await asyncio.wait_for(instance.task, timeout=30)


def rule_only_bundle(n: int) -> dict[str, Any]:
    """The shipped example without its worker steps: rules alone, which need no worker."""
    with EXAMPLE.open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    document["id"] = f"scaling-{os.getpid()}-{n}"
    document["limits"] = {"compute": {"seconds": 5, "resource_class": "cpu.small"}}
    document["steps"] = [
        {
            "id": "one",
            "method": "rule",
            "reason": "r",
            "rejected": [],
            "exactness": "exact",
            "work": {"rule": "constant", "value": {"n": n}},
        },
        {
            "id": "two",
            "method": "rule",
            "reason": "r",
            "rejected": [],
            "exactness": "exact",
            "depends_on": ["one"],
            "work": {"rule": "constant", "value": {"m": n}},
        },
    ]
    return document


async def submit(wired: Wired, document: dict[str, Any]) -> Run:
    version = await wired.register_version.execute(RegisterProcessVersion(document, tenant=TENANT))
    command = Command(
        id=wired.ids.new("cmd"),
        channel="channel.cli",
        identity="idn_test",
        org_path=(TENANT,),
        intent=Intent(raw="run"),
        reply_to=ReplyTo(channel="channel.cli", address="test"),
        received_at=wired.clock.now(),
    )
    plan = await wired.commission.execute(
        CommissionPlan(
            command=command,
            tenant=TENANT,
            goal="g",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    return await wired.engine.submit(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(dict(version.limits or {})),
            process_version=version.ref,
            actor="idn_test",
            tenant=TENANT,
        )
    )


async def until(condition: Callable[[], bool], *, seconds: float = 30) -> None:
    async with asyncio.timeout(seconds):
        while not condition():  # noqa: ASYNC110 — polling another process's state
            await asyncio.sleep(0.05)


async def test_two_runners_execute_every_run_exactly_once(
    instances: Callable[..., Instance],
) -> None:
    async with (
        instances("runner-a", TAKTUS_ROLES="runner") as a,
        instances("runner-b", TAKTUS_ROLES="runner") as b,
    ):
        assert a.wired is not None and b.wired is not None
        runs = [await submit(a.wired, rule_only_bundle(n)) for n in range(12)]
        assert all(r.state is RunState.PLANNED for r in runs)
        runner_a, runner_b = a.wired.runner, b.wired.runner
        assert runner_a is not None and runner_b is not None
        await until(lambda: len(runner_a.outcomes) + len(runner_b.outcomes) == len(runs))
        assert runner_a.outcomes and runner_b.outcomes, "the load was spread over both"
        executed = [o.job.id for o in (*runner_a.outcomes, *runner_b.outcomes)]
        assert len(executed) == len(set(executed)) == len(runs), "each run claimed once"
        for run in runs:
            async with a.wired.work.transaction(TENANT):
                stored = await a.wired.runs.get(TENANT, run.id)
                entries = await a.wired.ledger.entries(TENANT, run.id)
            assert stored is not None and stored.state is RunState.FINISHED
            kinds = [e.kind for e in entries]
            assert kinds.count("run.started") == 1 and kinds.count("run.finished") == 1
            assert kinds.count("step.started") == 2, "every step ran once, on one runner"
        async with a.wired.work.transaction(TENANT):
            assert (await a.wired.ledger.verify(TENANT)).intact


async def test_two_schedulers_elect_one_leader_and_the_survivor_takes_over(
    instances: Callable[..., Instance],
) -> None:
    async with instances("scheduler-a", TAKTUS_ROLES="scheduler") as a:
        await until(lambda: a.leading)
        async with instances("scheduler-b", TAKTUS_ROLES="scheduler") as b:
            await asyncio.sleep(0.5)
            assert a.leading and not b.leading, "exactly one leads; the second waits"
            a.stop.set()
            assert a.task is not None
            assert await asyncio.wait_for(a.task, timeout=30) == 0
            await until(lambda: b.leading)
            assert not a.leading
