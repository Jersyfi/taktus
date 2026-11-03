"""The suite against the factory worker, honest and with every fault (ADR-0157, #411).

The worker (`workers/factory/`) is run against a stand-in for a software factory
(`tests/fakes/factory_service.py`), served in this process: a task completes a stage every
0.3 s at 0.5 eur a stage, three stages in all. The worker's estimate is 1.2 eur, below the
1.5 eur a task costs, so that the suite's `tight` run shows the halt at a limit (W-14). The
factory's host is the one host the main run's frame allows; the narrowed run withdraws it
(W-13). The factory's token is the credential the suite references, and it reaches the factory
only in its header (W-08). No real factory is exercised here.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes.factory_service import FakeFactory
from fakes.ports import free_port

from taktus.conformance import Status
from taktus.conformance.client import WorkerClient
from taktus.conformance.rules import CHECKS

from .conftest import ROOT, RunningWorker, StartWorker, _list_faults, stop_all, wait_ready

type Json = dict[str, Any]
FACTORY_WORKER = ROOT / "workers" / "factory" / "worker.py"
CREDENTIAL = "FACTORY_TOKEN"
TASK: dict[str, object] = {
    "goal": "Conformance run of the factory worker: implement a greeting.",
    "acceptance": ["hello.txt exists"],
}
FAULTS = _list_faults([sys.executable, str(FACTORY_WORKER), "--list-faults"])
NOT_OFFERED = {"W-19", "W-20", "W-21"}


@pytest.fixture
def start_factory_worker(tmp_path: Path) -> Iterator[StartWorker]:
    started: list[subprocess.Popen[bytes]] = []
    factories: list[FakeFactory] = []

    def start(*, fault: str | None = None, stores: str = "eu") -> RunningWorker:
        value = "conf-" + secrets.token_hex(12)
        factory = FakeFactory(token=value).start()
        factories.append(factory)
        port = free_port()
        log = tmp_path / f"factory-{fault or 'honest'}.log"
        args = [
            sys.executable,
            str(FACTORY_WORKER),
            "--port",
            str(port),
            "--factory",
            factory.url,
            "--stores",
            stores,
            "--state-dir",
            str(tmp_path / f"factory-state-{fault or 'honest'}"),
            "--estimate-amount",
            "1.2",
            "--estimate-stages",
            "3",
            "--estimate-seconds",
            "2",
            "--poll-seconds",
            "0.05",
        ]
        if fault:
            args += ["--fault", fault]
        with log.open("wb") as handle:
            process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                args,
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, CREDENTIAL: value},
            )
        started.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        wait_ready(process, f"{endpoint}/v1/health", log, "factory worker")
        return RunningWorker(
            endpoint,
            log,
            value,
            process,
            credential_name=CREDENTIAL,
            task=dict(TASK),
            hosts=(factory.host,),
        )

    start.factories = factories  # type: ignore[attr-defined]
    yield start
    stop_all(started)
    for factory in factories:
        factory.stop()


async def test_the_factory_worker_passes_the_suite(start_factory_worker: StartWorker) -> None:
    worker = start_factory_worker()
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert statuses.pop("W-21") is Status.PENDING, "reached at an endpoint"
    assert set(statuses.values()) == {Status.PASSED}
    runs = {r.purpose: r for r in report.runs}
    assert runs["stopped"].outcome == "stopped" and runs["resumed"].outcome == "succeeded"
    assert runs["tight"].outcome == "stopped", "a task costs more than the worker estimates"
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()
    (factory,) = start_factory_worker.factories  # type: ignore[attr-defined]
    assert factory.submissions, "the suite's assignments reached the factory"
    assert all(worker.credential_value not in str(s) for s in factory.submissions)


async def test_it_declares_where_the_factory_stores_and_one_capability(
    start_factory_worker: StartWorker,
) -> None:
    """Principle 11: the worker declares the location its operator gave it, and offers the
    whole change as one capability, named by function."""
    worker = start_factory_worker(stores="elsewhere")
    async with WorkerClient(worker.endpoint, timeout=10.0, idle_timeout=10.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
    assert declared["data_location"] == "elsewhere"
    assert declared["capabilities"] == ["change.implement"]


async def test_the_change_arrives_as_the_coding_workers_publish_it(
    start_factory_worker: StartWorker,
) -> None:
    """One step per stage the factory reports, its cost per step, and the change as the
    `changeset` and `summary` a coding worker publishes."""
    worker = start_factory_worker()
    (factory,) = start_factory_worker.factories  # type: ignore[attr-defined]
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        accepted = await client.post(
            "/v1/assignments",
            {
                "assignment_id": "asg_factory01",
                "task": dict(TASK),
                "context": {},
                "frame": {
                    "autonomy_level": 2,
                    "allowed_tools": ["change.implement"],
                    "allowed_hosts": [factory.host],
                    "max_steps": 20,
                },
                "limits": {"currency": {"eur": 5.0}},
                "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
                "callback": {"events": "sse"},
            },
        )
        assert accepted.status == 201, accepted.text
        stream = await client.stream("asg_factory01")
        artifacts = (await client.get("/v1/assignments/asg_factory01/artifacts")).json or {}
    events = stream.events
    started = [e["step_id"] for e in events if e["type"] == "step.started"]
    assert started == ["submit", "stage-1", "stage-2", "stage-3", "fetch"]
    costs = [e["currency"]["eur"] for e in events if e["type"] == "consumption.reported"]
    assert costs == [0.0, 0.5, 0.5, 0.5, 0.0]
    kinds = {a["id"]: a["kind"] for a in artifacts["artifacts"]}
    assert kinds == {
        "submission": "factory.submission",
        "summary": "report",
        "changeset": "changeset",
    }
    assert events[-1]["outcome"] == "succeeded"
    (submitted,) = factory.submissions
    assert submitted["title"] == TASK["goal"] and submitted["reference"] == "asg_factory01"


async def test_a_frame_without_the_factory_s_host_sends_nothing(
    start_factory_worker: StartWorker,
) -> None:
    worker = start_factory_worker()
    (factory,) = start_factory_worker.factories  # type: ignore[attr-defined]
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        await client.post(
            "/v1/assignments",
            {
                "assignment_id": "asg_factory02",
                "task": dict(TASK),
                "context": {},
                "frame": {
                    "autonomy_level": 2,
                    "allowed_tools": ["change.implement"],
                    "max_steps": 20,
                },
                "limits": {"currency": {"eur": 5.0}},
                "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
                "callback": {"events": "sse"},
            },
        )
        events = (await client.stream("asg_factory02")).events
    refused = [e for e in events if e["type"] == "tool.called" and e.get("refused")]
    assert refused and refused[0]["host"] == factory.host
    assert events[-1]["outcome"] == "failed"
    assert factory.submissions == []


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"W-12", *NOT_OFFERED}


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_factory_worker: StartWorker, fault: str, check: str
) -> None:
    worker = start_factory_worker(fault=fault)
    report = await worker.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
