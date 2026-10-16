"""P-03 prepares the coding worker's workspace so that the repository's checks run in it (#466).

Twice the instance's run for #256 ended on a red pipeline for a finding its agent could not see:
the workspace had no linter and no test runner. Since version 13 the implementing step names a
command the worker runs before the work, and its frame admits the package index that command
installs from (ADR-0100). Here the bundle is read as shipped: the command, the hosts, and the
acceptance criterion naming only commands the setup installs.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

from taktus.ports.worker import BeforeCommand

ROOT = Path(__file__).resolve().parents[3]
P03 = ROOT / "blueprints/dev-orchestration/processes/P-03-implementation.yaml"
PACKAGE_INDEX = ("pypi.org", "files.pythonhosted.org")


def implement() -> dict[str, Any]:
    bundle = yaml.safe_load(P03.read_text(encoding="utf-8"))
    assert int(bundle["version"]) >= 13, "the workspace setup came with version 13 (ADR-0100)"
    (step,) = [s for s in bundle["steps"] if s["id"] == "implement"]
    work: dict[str, Any] = step["work"]
    return work


def test_the_workspace_is_prepared_from_the_lock_file_before_the_agent_starts() -> None:
    before = BeforeCommand.model_validate(implement()["task"]["before"])
    # The lock file, never a resolution: the agent checks against what the pipeline installs.
    assert before.command == ("uv", "sync", "--all-extras", "--frozen")
    assert before.artifact == "setup"


def test_the_frame_admits_the_package_index_the_lock_file_names_and_no_other_host() -> None:
    hosts = implement()["allowed_hosts"]
    assert hosts == [{"$input": "repository_host"}, *PACKAGE_INDEX]
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    named = set(re.findall(r'(?:registry|url) = "https://([^/"]+)', lock))
    assert named == set(PACKAGE_INDEX), "a host the lock file names that the frame does not"


def test_the_checks_the_agent_is_asked_to_run_are_installed_by_the_setup() -> None:
    acceptance = " ".join(implement()["task"]["acceptance"])
    named = set(re.findall(r"`uv run ([a-z-]+)", acceptance))
    assert named == {"ruff", "mypy", "pytest"}, named
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = {
        re.split(r"[\[<>=!~ ]", r)[0] for r in project["project"]["optional-dependencies"]["dev"]
    }
    assert named <= dev, "the setup installs every extra, and these are among them"
