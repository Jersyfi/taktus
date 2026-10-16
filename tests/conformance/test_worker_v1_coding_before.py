"""A coding worker runs the task's command before the work, and the agent finds what it left (#466).

On 2026-10-16 a P-03 run was given back on a red pipeline for one linter finding its agent could
not see: the workspace had neither the linter nor the tests' runner, and installing them failed
at the unit's proxy. A task now names a command the worker runs in the prepared workspace before
the agent starts (ADR-0100). Here both coding workers run one against the fake agent: it runs
first, what it wrote is the artifact the task names, what it left is not part of the change, and
it is given no credential. A command that fails ends the assignment before the agent starts,
with the reason and the output. That it reaches only the frame's hosts is the unit's proxy's to
enforce; `tests/workers/test_coding_worker_before.py` holds that the command gets the proxy.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from taktus.conformance.client import WorkerClient

from .conftest import HOST, TASK, RunningWorker

type Json = dict[str, Any]
CODING = ["start_coding_worker", "start_second_coding_worker"]

# What a setup does, in miniature: it writes an environment into the workspace, says so on both
# of its outputs, and states what of the worker's environment it was given.
SETUP = """
import json, os, pathlib, sys
pathlib.Path(".venv").mkdir()
pathlib.Path(".venv/installed").write_text("ruff mypy pytest\\n")
print("installed 3 packages", flush=True)
print("a warning on the error output", file=sys.stderr)
print(json.dumps({
    "credential": any("CREDENTIAL" in k or "API_KEY" in k for k in os.environ),
    "cache": os.environ.get("XDG_CACHE_HOME", ""),
}))
"""
FAILING = "import sys; print('no lock file in the workspace'); sys.exit(3)"


def repository(path: Path) -> Path:
    """A repository with one commit and no ignore file, for the workspace to be cloned from."""
    path.mkdir()
    (path / "README.md").write_text("# Upstream\n")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "base"],
    ):
        subprocess.run(command, cwd=path, check=True, capture_output=True)  # noqa: S603
    return path


async def assign(
    worker: RunningWorker, location: Path, before: Json, assignment_id: str
) -> tuple[list[Json], dict[str, bytes]]:
    """The assignment's events, and the bytes of every artifact it announced."""
    async with WorkerClient(worker.endpoint, timeout=90.0, idle_timeout=30.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
        accepted = await client.post(
            "/v1/assignments",
            {
                "assignment_id": assignment_id,
                "task": {**TASK, "before": before},
                "context": {"workspace": {"kind": "git", "location": str(location)}},
                "frame": {
                    "autonomy_level": 2,
                    "allowed_tools": list(declared["capabilities"]),
                    "allowed_hosts": [HOST],
                    "max_steps": 40,
                },
                "limits": {"currency": {"usd": 5.0}, "quota": {"units": 50}},
                "credentials": [{"name": worker.credential_name, "injected_as": "env"}],
                "callback": {"events": "sse"},
            },
        )
        assert accepted.status == 201, accepted.text
        stream = await client.stream(assignment_id)
        assert not stream.problems, stream.problems
        artifacts: dict[str, bytes] = {}
        for event in stream.events:
            if event["type"] == "artifact.produced":
                status, content = await client.get_bytes(str(event["uri"]))
                assert status == 200, event
                artifacts[str(event["artifact_id"])] = content
        return stream.events, artifacts


def started(events: list[Json]) -> list[Json]:
    return [e for e in events if e["type"] == "step.started"]


@pytest.mark.parametrize("starter", CODING)
async def test_the_command_before_the_work_runs_first_and_its_leavings_are_not_the_change(
    request: pytest.FixtureRequest, tmp_path: Path, starter: str
) -> None:
    worker: RunningWorker = request.getfixturevalue(starter)()
    upstream = repository(tmp_path / "upstream")
    before = {"command": [sys.executable, "-c", SETUP], "artifact": "setup"}
    events, artifacts = await assign(worker, upstream, before, "asg_before01")

    assert events[-1]["outcome"] == "succeeded", events[-1].get("reason")
    first, *work = started(events)
    assert first["summary"] == "the command before the work"
    assert work, "the agent worked after the command"
    (setup,) = [
        e for e in events if e["type"] == "artifact.produced" and e["artifact_id"] == "setup"
    ]
    assert setup["step_id"] == first["step_id"] and setup["kind"] == "output"
    # Both of its outputs, in the order written, and nothing of the worker's credential.
    lines = artifacts["setup"].decode().splitlines()
    assert lines[:2] == ["installed 3 packages", "a warning on the error output"], lines
    seen = json.loads(lines[2])
    assert seen["credential"] is False, "the command is given no credential"
    assert seen["cache"].endswith("/cache"), "its caches live under the worker's state"
    # Its money is reported with its step: none, since no model ran in it.
    (consumed,) = [
        e
        for e in events
        if e["type"] == "consumption.reported" and e["step_id"] == first["step_id"]
    ]
    assert consumed.get("tokens_in", 0) == 0 and consumed.get("tokens_out", 0) == 0
    # What it left in the workspace is where the work starts from, not part of the change.
    changeset = json.loads(artifacts["changeset"])
    paths = [entry["path"] for entry in changeset["files"]]
    assert paths and not [p for p in paths if p.startswith(".venv")], paths


@pytest.mark.parametrize("starter", CODING)
async def test_a_failing_command_before_the_work_ends_the_assignment_before_the_agent_starts(
    request: pytest.FixtureRequest, tmp_path: Path, starter: str
) -> None:
    worker: RunningWorker = request.getfixturevalue(starter)()
    upstream = repository(tmp_path / "upstream")
    before = {"command": [sys.executable, "-c", FAILING], "artifact": "setup"}
    events, artifacts = await assign(worker, upstream, before, "asg_before02")

    finished = events[-1]
    assert finished["outcome"] == "failed"
    assert "the command before the work exited with 3" in finished["reason"], finished
    assert "no lock file in the workspace" in finished["reason"], finished
    (only,) = started(events)
    assert only["summary"] == "the command before the work", "the agent never started"
    assert not [e for e in events if e["type"] == "tool.called"], "no call was made"
    assert artifacts["setup"] == b"no lock file in the workspace\n", "its output, kept"


@pytest.mark.parametrize("starter", CODING)
async def test_a_command_before_the_work_that_cannot_start_names_why(
    request: pytest.FixtureRequest, tmp_path: Path, starter: str
) -> None:
    worker: RunningWorker = request.getfixturevalue(starter)()
    upstream = repository(tmp_path / "upstream")
    before = {"command": ["taktus-no-such-program"], "artifact": "setup"}
    events, _ = await assign(worker, upstream, before, "asg_before03")
    finished = events[-1]
    assert finished["outcome"] == "failed"
    assert "the command before the work could not be started" in finished["reason"], finished
