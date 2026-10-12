"""The workflow that writes a pull request's `## Needed from the owner` holds a write token only
where the branch's author could already change the workflow (DEC-0189 rule 1, issue #314).

The repository is public. A workflow that writes to a pull request and runs the branch's code
must never do so for a fork with a write token."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
OWNER_LIST = WORKFLOWS / "owner-list.yml"


def load(path: Path) -> dict[str, Any]:
    document: dict[Any, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    # YAML 1.1 reads the key `on` as true.
    document["on"] = document.pop(True, document.get("on"))
    return document


def test_it_runs_on_pull_request_and_no_workflow_on_pull_request_target() -> None:
    triggers = load(OWNER_LIST)["on"]
    assert list(triggers) == ["pull_request"], triggers
    for path in WORKFLOWS.glob("*.yml"):
        assert "pull_request_target" not in load(path)["on"], path.name


def test_only_a_branch_of_this_repository_is_written_to() -> None:
    document = load(OWNER_LIST)
    assert document["permissions"] == {}, "nothing granted beyond the one job"
    [job] = document["jobs"].values()
    assert job["if"] == "github.event.pull_request.head.repo.full_name == github.repository"
    assert job["permissions"] == {"contents": "read", "pull-requests": "write"}


def test_the_token_never_reaches_the_branchs_code() -> None:
    [job] = load(OWNER_LIST)["jobs"].values()
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["persist-credentials"] is False
    for step in job["steps"]:
        run = step.get("run", "")
        env = step.get("env", {})
        if "tools/" in run:
            assert "GH_TOKEN" not in env, step["name"]
        if "GH_TOKEN" in env:
            assert "uv run" not in run, step["name"]
        assert "github.event.pull_request.body" not in run, "the description is data"


def test_the_description_check_no_longer_compares_the_owner_section() -> None:
    """The four sections stay checked; the generated list is written, not compared."""
    steps = load(WORKFLOWS / "description.yml")["jobs"]["description"]["steps"]
    runs = " ".join(step.get("run", "") for step in steps)
    assert "tools/check_decisions.py" in runs
    assert "tools/check_status.py" not in runs
