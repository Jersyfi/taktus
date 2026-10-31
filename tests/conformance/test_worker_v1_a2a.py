"""The suite against the A2A binding, honest and with every fault (ADR-0172, #349, UC-14.5).

The binding (`workers/a2a/`) is run against the reference agent (`tests/fakes/a2a_agent.py`), a
small server of the agent-to-agent protocol served in this process that knows nothing of
Taktus: a task changes its status every `TURN_SECONDS` and completes after three turns. The
binding's estimate is two turns of `agent.remote`, below the three a task takes, so that the
suite's `tight` run shows the halt at a limit (W-14). The agent's host is the one host the main
run's frame allows; the narrowed run withdraws it (W-13). The agent's token is the credential
the suite references, and it reaches the agent only in its header (W-08). No real agent is
exercised.
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
from architecture.test_core_is_technology_free import PRODUCT
from fakes.a2a_agent import QUESTION, ReferenceAgent
from fakes.ports import free_port

from taktus.conformance import Status
from taktus.conformance.client import WorkerClient
from taktus.conformance.rules import CHECKS

from .conftest import ROOT, RunningWorker, StartWorker, _list_faults, stop_all, wait_ready

type Json = dict[str, Any]
BINDING = ROOT / "workers" / "a2a" / "worker.py"
CREDENTIAL = "A2A_AGENT_TOKEN"
CAPABILITY = "report.draft"
TASK: dict[str, object] = {
    "goal": "Conformance run of the A2A binding: draft a report.",
    "acceptance": ["a report exists"],
}
FAULTS = _list_faults([sys.executable, str(BINDING), "--list-faults"])
NOT_OFFERED = {"W-20", "W-21"}


# A turn of the reference agent. Short, because the suite runs a dozen assignments for every
# fault and UC-14.5 names every fault, so `make gate-usecases` runs them all; at 0.3 s the
# self-test of that gate outran its 20 minutes. The binding reads the task four times a turn,
# so every status change is seen, and estimates two turns of the three a task takes.
TURN_SECONDS = 0.1
POLL_SECONDS = TURN_SECONDS / 4
ESTIMATE_SECONDS = 2 * TURN_SECONDS


@pytest.fixture
def start_binding(tmp_path: Path) -> Iterator[StartWorker]:
    started: list[subprocess.Popen[bytes]] = []
    agents: list[ReferenceAgent] = []

    def start(*, fault: str | None = None, stores: str = "eu", **agent: Any) -> RunningWorker:
        value = "conf-" + secrets.token_hex(12)
        agent.setdefault("turn_seconds", TURN_SECONDS)
        reference = ReferenceAgent(token=value, **agent).start()
        agents.append(reference)
        port = free_port()
        log = tmp_path / f"a2a-{fault or 'honest'}-{len(agents)}.log"
        args = [
            sys.executable,
            str(BINDING),
            "--port",
            str(port),
            "--agent",
            reference.url,
            "--capability",
            CAPABILITY,
            "--stores",
            stores,
            "--state-dir",
            str(tmp_path / f"a2a-state-{fault or 'honest'}-{len(agents)}"),
            "--estimate-seconds",
            str(ESTIMATE_SECONDS),
            "--estimate-turns",
            "3",
            "--poll-seconds",
            str(POLL_SECONDS),
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
        wait_ready(process, f"{endpoint}/v1/health", log, "A2A binding")
        return RunningWorker(
            endpoint,
            log,
            value,
            process,
            credential_name=CREDENTIAL,
            task=dict(TASK),
            hosts=(reference.host,),
        )

    start.agents = agents  # type: ignore[attr-defined]
    yield start
    stop_all(started)
    for each in agents:
        each.stop()


def assignment(assignment_id: str, hosts: list[str], **task: Any) -> Json:
    return {
        "assignment_id": assignment_id,
        "task": {**TASK, **task},
        "context": {},
        "frame": {
            "autonomy_level": 2,
            "allowed_tools": [CAPABILITY],
            "allowed_hosts": hosts,
            "max_steps": 20,
        },
        "limits": {"compute": {"seconds": 60, "resource_class": "agent.remote"}},
        "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
        "callback": {"events": "sse"},
    }


async def test_the_binding_passes_the_suite_against_the_reference_agent(
    start_binding: StartWorker,
) -> None:
    worker = start_binding()
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert statuses.pop("W-21") is Status.PENDING, "reached at an endpoint"
    assert set(statuses.values()) == {Status.PASSED}
    runs = {r.purpose: r for r in report.runs}
    assert runs["stopped"].outcome == "stopped" and runs["resumed"].outcome == "succeeded"
    assert runs["tight"].outcome == "stopped", "a task takes longer than the binding estimates"
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()
    (agent,) = start_binding.agents  # type: ignore[attr-defined]
    assert agent.received, "the suite's assignments reached the agent"
    assert all(worker.credential_value not in str(m) for m in agent.received)


async def test_it_declares_the_operators_capability_location_and_compute(
    start_binding: StartWorker,
) -> None:
    """Principle 11 and ADR-0003: the binding declares the location its operator gave it, the
    capability its operator named by function, and the one quantity it measures."""
    worker = start_binding(stores="elsewhere")
    async with WorkerClient(worker.endpoint, timeout=10.0, idle_timeout=10.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
    assert declared["data_location"] == "elsewhere"
    assert declared["capabilities"] == [CAPABILITY]
    assert declared["consumption"] == {"kinds": ["compute"], "resource_classes": ["agent.remote"]}
    assert declared["supports"]["steering"] is True
    assert declared["supports"]["handover"] is False


async def test_a_turn_per_status_and_the_agents_artifact(start_binding: StartWorker) -> None:
    worker = start_binding()
    (agent,) = start_binding.agents  # type: ignore[attr-defined]
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        accepted = await client.post("/v1/assignments", assignment("asg_a2a01", [agent.host]))
        assert accepted.status == 201, accepted.text
        stream = await client.stream("asg_a2a01")
        listed = (await client.get("/v1/assignments/asg_a2a01/artifacts")).json or {}
        report = await client.get("/v1/assignments/asg_a2a01/artifacts/agent-report")
    events = stream.events
    started = [e["step_id"] for e in events if e["type"] == "step.started"]
    assert started == ["send", "turn-1", "turn-2", "turn-3", "fetch"]
    seconds = [e["compute_seconds"] for e in events if e["type"] == "consumption.reported"]
    assert len(seconds) == 5 and sum(seconds[1:4]) >= 2 * TURN_SECONDS, seconds
    kinds = {a["id"]: a["kind"] for a in listed["artifacts"]}
    assert kinds == {"agent-task": "a2a.task", "agent-report": "agent.output", "summary": "report"}
    assert report.text == f"Report on: {TASK['goal']}"
    assert events[-1]["outcome"] == "succeeded"
    (sent,) = agent.received
    assert sent["parts"][0]["text"].startswith(str(TASK["goal"]))
    assert "taskId" not in sent


async def test_a_frame_without_the_agents_host_sends_nothing(start_binding: StartWorker) -> None:
    worker = start_binding()
    (agent,) = start_binding.agents  # type: ignore[attr-defined]
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        await client.post("/v1/assignments", assignment("asg_a2a02", []))
        events = (await client.stream("asg_a2a02")).events
    refused = [e for e in events if e["type"] == "tool.called" and e.get("refused")]
    assert refused and refused[0]["host"] == agent.host
    assert events[-1]["outcome"] == "failed"
    assert agent.received == []


async def test_an_estimate_above_the_limit_sends_nothing(start_binding: StartWorker) -> None:
    worker = start_binding()
    (agent,) = start_binding.agents  # type: ignore[attr-defined]
    body = assignment("asg_a2a03", [agent.host])
    body["limits"] = {
        "compute": {"seconds": ESTIMATE_SECONDS / 2, "resource_class": "agent.remote"}
    }
    money = assignment("asg_a2a04", [agent.host])
    money["limits"] = {"currency": {"eur": 5.0}}
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        await client.post("/v1/assignments", body)
        await client.post("/v1/assignments", money)
        over = (await client.stream("asg_a2a03")).events
        unheld = (await client.stream("asg_a2a04")).events
    assert [e["type"] for e in over] == ["assignment.finished"]
    assert over[0]["outcome"] == "rejected" and "exceeds the limit" in over[0]["reason"]
    assert unheld[0]["outcome"] == "rejected" and "agent.remote" in unheld[0]["reason"]
    assert agent.received == []


async def test_an_agent_that_asks_for_input_is_answered_by_steering(
    start_binding: StartWorker,
) -> None:
    """The agent's `input-required` is a turn whose question is in the stream; a person's
    message, received at the next boundary, goes into the agent's task, and the task goes on."""
    worker = start_binding(ask_input=True)
    (agent,) = start_binding.agents  # type: ignore[attr-defined]
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        await client.post("/v1/assignments", assignment("asg_a2a05", [agent.host]))

        async def answer(event: Json) -> None:
            if event.get("type") == "step.progress" and QUESTION in str(event.get("message")):
                posted = await client.post(
                    "/v1/assignments/asg_a2a05/messages",
                    {"message_id": "msg_audience", "text": "For the board."},
                )
                assert posted.status == 202, posted.text

        stream = await client.stream("asg_a2a05", on_event=answer)
        report = await client.get("/v1/assignments/asg_a2a05/artifacts/agent-report")
    events = stream.events
    asked = next(e for e in events if QUESTION in str(e.get("message", "")))
    received = next(e for e in events if e["type"] == "message.received")
    assert received["message_id"] == "msg_audience"
    assert asked["seq"] < received["seq"]
    assert events[-1]["outcome"] == "succeeded"
    further = [m for m in agent.received if m.get("taskId")]
    assert [m["messageId"] for m in further] == ["msg_audience"]
    assert "For the board." in report.text


async def test_an_agent_that_answers_at_once_finishes_without_a_task(
    start_binding: StartWorker,
) -> None:
    worker = start_binding(answer_at_once=True)
    (agent,) = start_binding.agents  # type: ignore[attr-defined]
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        await client.post("/v1/assignments", assignment("asg_a2a06", [agent.host]))
        events = (await client.stream("asg_a2a06")).events
        answer = await client.get("/v1/assignments/asg_a2a06/artifacts/agent-answer")
    assert [e["step_id"] for e in events if e["type"] == "step.started"] == ["send", "fetch"]
    assert events[-1]["outcome"] == "succeeded"
    assert answer.text.startswith("Answer to: ")
    assert agent.tasks == {}


async def test_a_task_the_agent_fails_fails_the_assignment(start_binding: StartWorker) -> None:
    worker = start_binding(fail_tasks=True)
    (agent,) = start_binding.agents  # type: ignore[attr-defined]
    async with WorkerClient(worker.endpoint, timeout=30.0, idle_timeout=10.0) as client:
        await client.post("/v1/assignments", assignment("asg_a2a07", [agent.host]))
        events = (await client.stream("asg_a2a07")).events
    finished = events[-1]
    assert finished["outcome"] == "failed"
    assert "the agent's task ended failed" in finished["reason"]


@pytest.mark.parametrize("missing", ["--stores", "--capability"])
def test_a_binding_whose_operator_states_nothing_does_not_start(missing: str) -> None:
    """Nothing is assumed: without the location or the capability the binding exits before it
    listens, naming what is missing."""
    given = {"--agent": "http://127.0.0.1:9", "--stores": "eu", "--capability": CAPABILITY}
    del given[missing]
    args = [part for pair in given.items() for part in pair]
    done = subprocess.run(  # noqa: S603 — our own script, fixed arguments
        [sys.executable, str(BINDING), *args], capture_output=True, text=True, timeout=30
    )
    assert done.returncode == 2
    assert f"{missing} is required" in done.stderr


def test_no_product_name_in_the_binding_or_the_reference_agent() -> None:
    for path in [*sorted((ROOT / "workers" / "a2a").iterdir()), ROOT / "tests/fakes/a2a_agent.py"]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = PRODUCT.search(line)
            assert match is None, f"{path.name}:{number}: product name {match.group(0)!r}"


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"W-12", *NOT_OFFERED}


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_binding: StartWorker, fault: str, check: str
) -> None:
    worker = start_binding(fault=fault)
    report = await worker.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
