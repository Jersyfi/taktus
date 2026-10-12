"""A coding worker's git reaches its host through the unit's proxy (issue #306).

On a cluster a unit reaches nothing but its egress proxy. The first P-03 run on the installed
instance failed to clone because git, unlike the agent, was started without the proxy variables.
Both coding workers are separate deployables; each is loaded by its path.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKERS = {name: ROOT / "workers" / name / "worker.py" for name in ("claudecode", "codex")}
PROXY = "http://taktus-egress.invalid:3128"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"worker_{name}_proxy", WORKERS[name])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_git_receives_the_proxy_and_nothing_else_new(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = load(name)
    run = object.__new__(worker._Run)
    run.workspace = tmp_path
    for variable in ("HTTPS_PROXY", "https_proxy", "NO_PROXY"):
        monkeypatch.setenv(
            variable, PROXY if "PROXY" in variable.upper() and "NO" not in variable else "localhost"
        )
    monkeypatch.setenv("CODING_AGENT_API_KEY", "made-up")
    seen: dict[str, Any] = {}

    def fake_run(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        seen.update(options["env"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    run._git(["git", "status"])
    assert seen["HTTPS_PROXY"] == PROXY and seen["https_proxy"] == PROXY
    assert seen["NO_PROXY"] == "localhost"
    assert "CODING_AGENT_API_KEY" not in seen
