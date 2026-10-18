"""Both coding workers hand the target repository's `AGENTS.md` to their agent (#407, ADR-0113).

Each worker is started as it ships, against its fake agent, and given an assignment whose
workspace is a repository with an `AGENTS.md` at its root. The fake agent writes down the prompt
and the arguments it was started with (`FAKE_AGENT_BRIEF_PATH`). The rules are in the prompt,
before the task. The second coding worker's agent would read the file by itself as well; its
worker turns that reading off, so that the rules arrive once. The edge cases — no file, a link
out of the workspace, the bound, a resumed session — are
`tests/workers/test_coding_worker_rules.py`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from taktus.conformance.client import WorkerClient

from .conftest import RunningWorker, StartWorker

type Json = dict[str, Any]
RULES = "# Rules of the target repository\n\nEvery change carries its test.\n"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@localhost",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@localhost",
}


def repository(at: Path) -> Path:
    """A repository holding an `AGENTS.md`, as a target repository would."""
    at.mkdir()
    (at / "AGENTS.md").write_text(RULES, encoding="utf-8")
    (at / "README.md").write_text("A target repository.\n", encoding="utf-8")
    for command in (["init", "--quiet"], ["add", "-A"], ["commit", "--quiet", "-m", "start"]):
        subprocess.run(  # noqa: S603 — fixed arguments
            ["git", *command],  # noqa: S607 — git on the path
            cwd=at,
            check=True,
            env={"PATH": "/usr/bin:/bin", **GIT_IDENTITY},
        )
    return at


async def one_assignment(worker: RunningWorker, location: Path) -> list[Json]:
    async with WorkerClient(worker.endpoint, timeout=90.0, idle_timeout=30.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
        accepted = await client.post(
            "/v1/assignments",
            {
                "assignment_id": "asg_brief01",
                "task": {"goal": "Add a greeting.", "acceptance": ["hello.txt exists"]},
                "context": {"workspace": {"kind": "git", "location": str(location)}},
                "frame": {
                    "autonomy_level": 2,
                    "allowed_tools": list(declared["capabilities"]),
                    "allowed_hosts": [],
                    "max_steps": 40,
                },
                "limits": {"currency": {"usd": 5.0}, "quota": {"units": 50}},
                "credentials": [{"name": worker.credential_name, "injected_as": "env"}],
                "callback": {"events": "sse"},
            },
        )
        assert accepted.status == 201, accepted.text
        stream = await client.stream("asg_brief01")
        assert not stream.problems, stream.problems
        return stream.events


@pytest.mark.parametrize("starter", ["start_coding_worker", "start_second_coding_worker"])
async def test_the_agent_is_briefed_with_the_target_repository_s_agents_md(
    starter: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    kept = tmp_path / "brief.json"
    start: StartWorker = request.getfixturevalue(starter)
    worker = start(agent_env={"FAKE_AGENT_BRIEF_PATH": str(kept)})
    events = await one_assignment(worker, repository(tmp_path / "target"))
    assert events[-1]["type"] == "assignment.finished", events[-1]
    assert events[-1]["outcome"] == "succeeded", events[-1]
    given = json.loads(kept.read_text(encoding="utf-8"))
    prompt = given["prompt"]
    assert RULES.strip() in prompt
    assert prompt.index(RULES.strip()) < prompt.index("Goal: Add a greeting.")
    if starter == "start_second_coding_worker":
        arguments = given["arguments"]
        assert arguments[arguments.index("project_doc_max_bytes=0") - 1] == "--config"
