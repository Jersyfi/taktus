"""A coding assignment posted again finds the workspace its earlier attempt left (#280).

In the live run of #74 a coding step failed and was run again: the new assignment failed at once,
because its repository could not be cloned into the workspace the first attempt had left. Here
the same assignment is posted twice to both coding workers, the second time to a worker
restarted on the same state, as a runner that lost the first attempt posts it. The second
attempt starts in a clean workspace and finishes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from taktus.conformance.client import WorkerClient

from .conftest import HOST, TASK, RunningWorker, StartWorker

type Json = dict[str, Any]
ASSIGNMENT = "asg_again01"


def repository(path: Path) -> Path:
    """A repository with one commit, for the workspace to be cloned from."""
    path.mkdir()
    (path / "README.md").write_text("# Upstream\n")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "base"],
    ):
        subprocess.run(command, cwd=path, check=True, capture_output=True)  # noqa: S603
    return path


async def attempt(worker: RunningWorker, location: Path) -> list[Json]:
    async with WorkerClient(worker.endpoint, timeout=90.0, idle_timeout=30.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
        accepted = await client.post(
            "/v1/assignments",
            {
                "assignment_id": ASSIGNMENT,
                "task": dict(TASK),
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
        stream = await client.stream(ASSIGNMENT)
        assert not stream.problems, stream.problems
        return stream.events


@pytest.mark.parametrize("starter", ["start_coding_worker", "start_second_coding_worker"])
async def test_an_assignment_posted_again_starts_in_a_clean_workspace_and_finishes(
    request: pytest.FixtureRequest, tmp_path: Path, starter: str
) -> None:
    start: StartWorker = request.getfixturevalue(starter)
    upstream = repository(tmp_path / "upstream")
    first = start()
    assert (await attempt(first, upstream))[-1]["outcome"] == "succeeded"
    first.process.terminate()
    first.process.wait(timeout=10)

    again = start()  # the same state directory: the first attempt's workspace is still there
    events = await attempt(again, upstream)
    finished = events[-1]
    assert finished["outcome"] == "succeeded", finished.get("reason")
    patches = [e for e in events if e["type"] == "artifact.produced" and e["kind"] == "patch"]
    assert patches, "the second attempt did its work, not only started"
