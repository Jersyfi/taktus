"""A stop that meets an agent which has just exited is not a failure (#640, W-14).

The coding workers end the agent with `os.killpg` after `poll()` said it still runs. When the
agent exits between the two, its group's only member is a zombie not yet reaped, and macOS
answers the signal with EPERM, not ESRCH: `PermissionError(1, 'Operation not permitted')`. The
worker took that for a fault, and W-14's tight run ended `failed` instead of `stopped` under the
parallel load of `make verify`, where the window between the two calls is widest. Here the
window is held open on purpose: the agent has exited and is not reaped when the stop arrives.
Linux signals a zombie's group without an error, so there the test passes either way.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

WORKERS = Path(__file__).resolve().parents[2] / "workers"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"worker_{name}_stop", WORKERS / name / "worker.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("worker", ["claudecode", "codex"])
@pytest.mark.parametrize("force", [False, True])
def test_the_agent_exited_between_poll_and_signal_is_nothing_to_stop(
    worker: str, force: bool
) -> None:
    end = load(worker)._end
    agent = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True, text=True)
    # Wait until it has exited, without reaping it: it stays a zombie leading its group.
    os.waitid(os.P_PID, agent.pid, os.WEXITED | os.WNOWAIT)
    # The moment before the exit, as `poll()` saw it.
    agent.poll = lambda: None  # type: ignore[method-assign]
    try:
        end(agent, force=force)  # raised PermissionError on macOS before #640
    finally:
        os.waitpid(agent.pid, 0)
