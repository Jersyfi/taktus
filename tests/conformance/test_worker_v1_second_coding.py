"""The suite against the second coding worker, in both authentication modes and with every fault.

The worker (`workers/codex/`) is run against its fake agent, which writes the agent's documented
non-interactive stream and its session file and does what its items say, so that the worker's
mechanics — boundaries, tokens per step, the frame, stop and resume, authentication — are proven
without an account and deterministically (#154). The real agent is not exercised here; its live
test is #208, which waits for a credential (NEED-0022) and runs only in the workflow `live`
(DEC-0048).
"""

from __future__ import annotations

from typing import Any

import pytest

from taktus.conformance import Status
from taktus.conformance.client import WorkerClient
from taktus.conformance.rules import CHECKS

from .conftest import (
    HOST,
    SECOND_CODING_WORKER,
    TASK,
    RunningWorker,
    StartWorker,
    coding_faults,
)

type Json = dict[str, Any]
FAULTS = coding_faults(SECOND_CODING_WORKER)
# What the fake agent's responses use, input side, cached tokens included: one response per
# item of its plan of six, and one for its closing message (`workers/codex/fake_agent.py`).
RESPONSE_IN = {n: 1003 + 5100 * n for n in (1, 2, 3, 4, 5, 6, 99)}
REQUIRED_BY_A_CODING_STEP = {"code.read", "code.edit", "code.test", "shell.sandboxed"}


async def one_assignment(
    worker: RunningWorker,
    *,
    assignment_id: str = "asg_second01",
    checkpoint_ref: str | None = None,
    credential: str | None = None,
    limits: Json | None = None,
    allowed_tools: list[str] | None = None,
) -> list[Json]:
    """Post one assignment in a frame that allows everything the worker offers, unless told
    otherwise, and read its stream to the end."""
    async with WorkerClient(worker.endpoint, timeout=90.0, idle_timeout=30.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
        context: Json = {}
        if checkpoint_ref is not None:
            context["checkpoint_ref"] = checkpoint_ref
        accepted = await client.post(
            "/v1/assignments",
            {
                "assignment_id": assignment_id,
                "task": dict(TASK),
                "context": context,
                "frame": {
                    "autonomy_level": 2,
                    "allowed_tools": allowed_tools or list(declared["capabilities"]),
                    "allowed_hosts": [HOST],
                    "max_steps": 40,
                },
                "limits": limits or {"currency": {"usd": 5.0}, "quota": {"units": 50}},
                "credentials": [
                    {"name": credential or worker.credential_name, "injected_as": "env"}
                ],
                "callback": {"events": "sse"},
            },
        )
        assert accepted.status == 201, accepted.text
        stream = await client.stream(assignment_id)
        assert not stream.problems, stream.problems
        return stream.events


async def test_it_offers_what_a_coding_step_requires(
    start_second_coding_worker: StartWorker,
) -> None:
    """A step served by the first coding worker can be served by this one: it declares every
    capability P-03's step `implement` requires."""
    worker = start_second_coding_worker()
    async with WorkerClient(worker.endpoint, timeout=10.0, idle_timeout=10.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
    assert set(declared["capabilities"]) >= REQUIRED_BY_A_CODING_STEP


@pytest.mark.parametrize("auth", ["api-key", "session"])
async def test_the_second_coding_worker_passes_in_both_authentication_modes(
    start_second_coding_worker: StartWorker, auth: str
) -> None:
    worker = start_second_coding_worker(auth=auth)
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}
    runs = {r.purpose: r for r in report.runs}
    assert runs["stopped"].outcome == "stopped" and runs["resumed"].outcome == "succeeded"
    assert runs["tight"].outcome == "stopped", "the fake agent overruns; the limit halts it"
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()
    events = await one_assignment(worker)
    kinds = {e["type"] for e in events}
    assert {"step.started", "tool.called", "consumption.reported", "step.boundary"} <= kinds
    patches = [e for e in events if e["type"] == "artifact.produced" and e["kind"] == "patch"]
    assert patches, "every step that changed the workspace produced its change as a patch"
    if auth == "session":
        reported = [e for e in events if e["type"] == "consumption.reported"]
        assert all(e.get("quota_units") == 1 for e in reported)
    assert events[-1]["outcome"] == "succeeded"


async def test_tokens_come_per_step_and_add_up_to_the_agents_own_total(
    start_second_coding_worker: StartWorker,
) -> None:
    """Every step reports the tokens of the model response that started it, read from the
    agent's session file; the closing message's go to the report step. The sum is what the
    agent reports for its turn, and the tokens are priced by kind for the model that used
    them — the agent reports no money."""
    worker = start_second_coding_worker(auth="api-key")
    events = await one_assignment(worker)
    reported = [e for e in events if e["type"] == "consumption.reported"]
    hosts, *agent, report = reported
    assert hosts["tokens_in"] == 0, "the hosts step asks no model"
    assert [e["tokens_in"] for e in agent] == [RESPONSE_IN[n] for n in range(1, 7)]
    assert report["tokens_in"] == RESPONSE_IN[99]
    assert sum(e["tokens_in"] for e in reported) == sum(RESPONSE_IN.values())
    assert not [e for e in reported if "currency" in e], "money follows from the tokens"
    first = agent[0]["tokens_by_model"]["fake-coding-model"]
    assert first == {"input": 1103, "cache_read": 5000, "cache_write": 0, "output": 41}


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"W-12"}


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_second_coding_worker: StartWorker, fault: str, check: str
) -> None:
    worker = start_second_coding_worker(fault=fault)
    report = await worker.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1


async def test_a_host_is_reached_through_a_command_the_frame_must_allow(
    start_second_coding_worker: StartWorker,
) -> None:
    """The agent asks no permission per call. A command that changes the workspace in a frame
    that allows reading and editing only is refused when it appears; the agent is ended, and
    the workspace is reset to the last boundary, so that the refused command leaves nothing."""
    worker = start_second_coding_worker()
    events = await one_assignment(worker, allowed_tools=["code.read", "code.edit"])
    finished = events[-1]
    assert finished["outcome"] == "failed" and "shell.sandboxed" in finished["reason"]
    refused = [e for e in events if e["type"] == "tool.called" and e.get("refused")]
    assert refused and refused[0]["tool"] == "shell.sandboxed"
    # The hosts step reaches its host through a command: refused before the agent starts.
    assert refused[0].get("host") == HOST


async def test_a_command_outside_the_frame_is_refused_once_the_agent_runs(
    start_second_coding_worker: StartWorker,
) -> None:
    """Without hosts to admit, the first item outside the frame is the agent's own: its third
    item writes a file from a command in a frame that allows reading and editing only."""
    worker = start_second_coding_worker()
    async with WorkerClient(worker.endpoint, timeout=90.0, idle_timeout=30.0) as client:
        accepted = await client.post(
            "/v1/assignments",
            {
                "assignment_id": "asg_second_frame",
                "task": {"goal": "write hello"},
                "context": {},
                "frame": {
                    "autonomy_level": 2,
                    "allowed_tools": ["code.read", "code.edit"],
                    "max_steps": 40,
                },
                "limits": {"currency": {"usd": 5.0}},
                "credentials": [{"name": worker.credential_name, "injected_as": "env"}],
                "callback": {"events": "sse"},
            },
        )
        assert accepted.status == 201, accepted.text
        events = (await client.stream("asg_second_frame")).events
        artifacts = (await client.get("/v1/assignments/asg_second_frame/artifacts")).json or {}
    calls = [e for e in events if e["type"] == "tool.called"]
    assert [c["tool"] for c in calls] == ["code.read", "code.edit", "shell.sandboxed"]
    assert calls[-1]["refused"] is True and not any(c.get("refused") for c in calls[:-1])
    assert events[-1]["outcome"] == "failed"
    patches = [a["id"] for a in artifacts["artifacts"] if a["kind"] == "patch"]
    assert patches == ["change-2"], "the edit is a change; the refused command left none"


async def test_a_login_that_expires_mid_run_halts_at_the_boundary(
    start_second_coding_worker: StartWorker,
) -> None:
    """The agent's login stops working after its second item: the assignment ends `stopped`
    at the last boundary with the cause, and the resumed one continues the same thread from
    there once the login works again. Not an abort, not a silent retry."""
    worker = start_second_coding_worker(auth="session", agent_env={"FAKE_AGENT_EXPIRE_AFTER": "2"})
    events = await one_assignment(worker)
    finished = events[-1]
    assert finished["type"] == "assignment.finished" and finished["outcome"] == "stopped"
    assert "authentication" in finished["reason"] and "expired" in finished["reason"].lower()
    boundaries = [e for e in events if e["type"] == "step.boundary"]
    assert boundaries and boundaries[-1]["checkpoint_ref"] == finished["checkpoint_ref"]
    starts = [e for e in events if e["type"] == "step.started"]
    assert len(starts) == 3, "the hosts step and two items, then the login expired"
    resumed = await one_assignment(
        worker, assignment_id="asg_second_resume01", checkpoint_ref=finished["checkpoint_ref"]
    )
    assert resumed[-1]["outcome"] == "succeeded"
    before = {e["artifact_id"] for e in events if e["type"] == "artifact.produced"}
    after = {e["artifact_id"] for e in resumed if e["type"] == "artifact.produced"}
    assert before and not before & after
    reported = [e for e in resumed if e["type"] == "consumption.reported"]
    assert [e["tokens_in"] for e in reported[:2]] == [0, RESPONSE_IN[3]], (
        "the hosts step again, then the resumed thread at its third item"
    )


async def test_an_exhausted_window_blocks_at_the_boundary(
    start_second_coding_worker: StartWorker,
) -> None:
    worker = start_second_coding_worker(auth="session", agent_env={"FAKE_AGENT_WINDOW_AFTER": "1"})
    events = await one_assignment(worker)
    finished = events[-1]
    assert finished["outcome"] == "stopped" and "window" in finished["reason"]


async def test_an_assignment_that_does_not_name_the_credential_is_rejected_before_it_starts(
    start_second_coding_worker: StartWorker,
) -> None:
    worker = start_second_coding_worker(auth="api-key")
    events = await one_assignment(worker, credential="SOMETHING_ELSE")
    assert events[-1]["outcome"] == "rejected"
    assert "CODING_AGENT_API_KEY" in events[-1]["reason"]
    assert len(events) == 1


async def test_a_token_limit_halts_at_the_boundary_and_the_resume_continues(
    start_second_coding_worker: StartWorker,
) -> None:
    """The reservation is the worker's hard ceiling, in tokens per step. Under a limit equal to
    the estimate, 60 000, the worker ends the agent at the first boundary where the running
    total has reached it, and finishes `stopped` with the checkpoint and `limit`. The resumed
    assignment continues the same thread and repeats nothing."""
    worker = start_second_coding_worker(auth="api-key")
    limits: Json = {"currency": {"usd": 5.0}, "tokens": {"in": 60000}}
    events = await one_assignment(worker, limits=limits)
    finished = events[-1]
    assert finished["outcome"] == "stopped" and finished["limit"] == "tokens", finished
    boundaries = [e for e in events if e["type"] == "step.boundary"]
    assert boundaries[-1]["checkpoint_ref"] == finished["checkpoint_ref"]
    assert boundaries[-1]["seq"] == finished["seq"] - 1, "no step started after the boundary"
    reported = [e for e in events if e["type"] == "consumption.reported"]
    used = sum(e.get("tokens_in", 0) for e in reported)
    assert used >= 60000
    assert used - reported[-1]["tokens_in"] < 60000, "the limit was reached with the last step"
    resumed = await one_assignment(
        worker, assignment_id="asg_second_resume02", checkpoint_ref=finished["checkpoint_ref"]
    )
    assert resumed[-1]["outcome"] == "succeeded"
    before = {e["artifact_id"] for e in events if e["type"] == "artifact.produced"}
    after = {e["artifact_id"] for e in resumed if e["type"] == "artifact.produced"}
    assert before and not before & after
