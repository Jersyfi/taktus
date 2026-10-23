"""The reference worker's steering and handover, through the core's worker client (ADR-0139).

A message sent while a step runs is received at that step's boundary, and the command of the
next step has it. A handover on one instance is continued on a second instance that has a state
directory of its own: everything the continuation needs is in the document, which is the part
of W-20 a suite talking to one endpoint cannot show. What the worker refuses reaches the core as
a refusal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes.ports import free_port

from taktus.adapters.driven.workers.http import HttpWorker
from taktus.ports.worker import (
    Assignment,
    Callback,
    ComputeLimit,
    Context,
    Frame,
    Handover,
    HandoverRefused,
    HandoverRequest,
    Limits,
    SteeringMessage,
    SteeringRefused,
    Task,
    Workspace,
)

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"


@pytest.fixture
def start(tmp_path: Path) -> Iterator[object]:
    processes: list[subprocess.Popen[bytes]] = []

    def run(name: str, step_seconds: float = 0.4) -> str:
        port = free_port()
        log = (tmp_path / f"{name}.log").open("wb")
        process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
            [
                sys.executable,
                str(WORKER),
                "--port",
                str(port),
                "--state-dir",
                str(tmp_path / f"state-{name}"),
                "--step-seconds",
                str(step_seconds),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=dict(os.environ),
        )
        processes.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{endpoint}/v1/health", timeout=1.0).status_code == 200:
                    return endpoint
            except httpx.HTTPError:
                time.sleep(0.1)
        raise RuntimeError(f"the worker {name} did not become ready")

    yield run
    for process in processes:
        process.terminate()
        process.wait(timeout=10)


def assignment(
    assignment_id: str, commands: list[str] | None = None, handover: Handover | None = None
) -> Assignment:
    return Assignment(
        assignment_id=assignment_id,
        task=Task(
            goal="run the commands",
            acceptance=("every command exits with 0",),
            inputs={"commands": commands} if commands is not None else {},
        ),
        context=Context(workspace=Workspace(kind="none"), handover=handover),
        frame=Frame(autonomy_level=2, allowed_tools=("shell.script",), max_steps=10),
        limits=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
        callback=Callback(events="sse"),
    )


async def test_a_message_reaches_the_step_after_the_boundary(start: object) -> None:
    endpoint = start("steered")  # type: ignore[operator]
    message = SteeringMessage(message_id="msg_conf_steer1", text="use the second endpoint")
    commands = ["true", 'printf "%s" "$TAKTUS_STEERING"']
    async with HttpWorker(endpoint) as worker:
        await worker.assign(assignment("asg_steered01", commands))
        events = []
        async for event in worker.events("asg_steered01"):
            events.append(event)
            if event.type == "step.started" and event.step_id == "cmd-1":
                accepted = await worker.steer("asg_steered01", message)
                assert accepted.status in ("running", "accepted")
                await worker.steer("asg_steered01", message)  # again: received once
        received = [e for e in events if e.type == "message.received"]
        assert [(e.message_id, e.step_id) for e in received] == [("msg_conf_steer1", "cmd-1")]
        kinds = [e.type for e in events]
        assert kinds.index("message.received") > kinds.index("step.boundary")
        output = next(
            e for e in events if e.type == "artifact.produced" and e.artifact_id == "output-2"
        )
        content = await worker.artifact_bytes("asg_steered01", output.artifact())
        assert json.loads(content) == ["use the second endpoint"], "the next step has it"


async def test_a_handover_is_continued_by_another_instance(start: object) -> None:
    first = start("first")  # type: ignore[operator]
    second = start("second")  # type: ignore[operator]
    async with HttpWorker(first) as a, HttpWorker(second) as b:
        await a.assign(assignment("asg_handed01"))
        events = []
        async for event in a.events("asg_handed01"):
            events.append(event)
            if event.type == "step.started" and event.step_id == "inspect":
                state = await a.hand_over("asg_handed01", HandoverRequest(reason="elsewhere"))
                assert state.status == "stopping"
        finished = events[-1]
        assert finished.type == "assignment.finished" and finished.outcome == "stopped"
        assert finished.handover == "handover"
        artifact = next(
            e for e in events if e.type == "artifact.produced" and e.kind == "handover.state"
        )
        document = Handover.model_validate_json(
            await a.artifact_bytes("asg_handed01", artifact.artifact())
        )
        assert document.checkpoint_ref == finished.checkpoint_ref
        assert [s.step_id for s in document.steps] == ["inspect"]
        assert "Remaining: prepare, run, report" in document.summary

        await b.assign(assignment("asg_continued01", handover=document))
        continued = [e async for e in b.events("asg_continued01")]
        assert continued[-1].type == "assignment.finished"
        assert continued[-1].outcome == "succeeded", continued[-1]
        started = [e.step_id for e in continued if e.type == "step.started"]
        assert started == ["prepare", "run", "report"], "nothing done is done again"


async def test_what_the_worker_refuses_reaches_the_core_as_a_refusal(start: object) -> None:
    endpoint = start("refusing", step_seconds=0.05)  # type: ignore[operator]
    message = SteeringMessage(message_id="msg_conf_late01", text="too late")
    async with HttpWorker(endpoint) as worker:
        with pytest.raises(SteeringRefused):
            await worker.steer("asg_nobody01", message)
        with pytest.raises(HandoverRefused):
            await worker.hand_over("asg_nobody01", HandoverRequest())
        await worker.assign(assignment("asg_finished01"))
        _ = [e async for e in worker.events("asg_finished01")]
        with pytest.raises(SteeringRefused, match="409"):
            await worker.steer("asg_finished01", message)
