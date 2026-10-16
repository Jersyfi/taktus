"""The task's command before the work reaches the network through the unit's proxy, and only so.

On a cluster a unit reaches nothing but its egress proxy, which admits the frame's hosts and the
worker's service hosts (ADR-0089). A command before the work that installs a project's tools
must therefore be given the proxy, as git is (#306), or it reaches nothing; and it is given no
credential, so that nothing it fetches can act as the worker (ADR-0100). Both coding workers are
separate deployables; each is loaded by its path.
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
PROXY = "http://taktus:token@taktus-egress.invalid:3128"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"worker_{name}_before", WORKERS[name])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_the_command_receives_the_proxy_and_its_cache_and_no_credential(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = load(name)
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("https_proxy", PROXY)
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("CODING_AGENT_API_KEY", "made-up")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE", "/run/made-up")
    seen: dict[str, Any] = {}

    def fake_run(command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        seen.update(options)
        return subprocess.CompletedProcess(command, 0, b"installed\n", None)

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    output, failure = worker.run_before(("uv", "sync"), tmp_path, tmp_path / "state")
    assert (output, failure) == (b"installed\n", None)
    env = seen["env"]
    assert env["HTTPS_PROXY"] == PROXY and env["https_proxy"] == PROXY
    assert env["NO_PROXY"] == "localhost"
    assert env["XDG_CACHE_HOME"] == str(tmp_path / "state" / "cache")
    assert not [k for k in env if "API_KEY" in k or "CREDENTIAL" in k], sorted(env)
    assert seen["cwd"] == tmp_path and seen["stderr"] == subprocess.STDOUT
    assert seen["timeout"] == worker.BEFORE_TIMEOUT


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_a_command_that_outlasts_its_bound_fails_with_what_it_wrote(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = load(name)

    def fake_run(command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(command, options["timeout"], output=b"Resolved 101\n")

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    output, failure = worker.run_before(("uv", "sync"), tmp_path, tmp_path / "state")
    assert output == b"Resolved 101\n"
    assert failure == f"the command before the work exceeded {worker.BEFORE_TIMEOUT}s"
