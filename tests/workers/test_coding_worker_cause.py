"""A coding assignment that fails says why (#375), and how long it may go on (DEC-0193).

The agent's last line is a result. One that ends on the agent's own limit of turns carries an
error subtype and no text, and the worker read only the text and the error stream: the run on
the instance of 2026-10-13 failed with "the agent exited with 1". The worker is a separate
deployable, loaded by its path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

WORKER = Path(__file__).resolve().parents[2] / "workers" / "claudecode" / "worker.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("worker_claudecode_cause", WORKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_an_error_result_without_text_names_its_subtype_and_turns() -> None:
    cause = load()._cause_of(
        {"type": "result", "subtype": "error_max_turns", "is_error": True, "num_turns": 41},
        "",
        1,
    )
    assert cause == "the agent ended with error_max_turns after 41 turn(s)"


def test_a_result_text_and_the_error_stream_still_come_first_and_last() -> None:
    worker = load()
    assert worker._cause_of({"result": "it broke", "is_error": True}, "", 1) == "it broke"
    assert worker._cause_of({}, "fatal: no such file\n", 2) == "fatal: no such file"
    assert worker._cause_of({}, "", 1) == "the agent exited with 1"
    assert (
        worker._cause_of({"subtype": "error_during_execution", "is_error": True}, "boom\n", 1)
        == "the agent ended with error_during_execution: boom"
    )


def test_the_limit_of_turns_is_read_from_the_units_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator raises the agent's limit of turns for a cluster unit through the unit's
    settings (ADR-0090), as the project's instance does (DEC-0193). The flag still wins."""
    worker = load()
    monkeypatch.setenv("CODING_AGENT_AUTH", "api-key")
    monkeypatch.delenv("CODING_AGENT_MAX_TURNS", raising=False)
    assert worker.parse_args([]).max_turns == 50
    monkeypatch.setenv("CODING_AGENT_MAX_TURNS", "150")
    assert worker.parse_args([]).max_turns == 150
    assert worker.parse_args(["--max-turns", "20"]).max_turns == 20


def test_the_agent_is_offered_only_the_tools_its_frame_allows() -> None:
    """A tool offered and then refused ends the assignment (W-07): three runs on the instance
    ended on a web fetch they were offered and not allowed (#424)."""
    from types import SimpleNamespace

    worker = load()
    run = object.__new__(worker._Run)
    run.frame = {
        "allowed_tools": ["code.read", "code.edit", "code.test", "shell.sandboxed"],
        "allowed_hosts": ["github.com"],
    }
    run.fault = None
    run.body = {"context": {}}
    run.worker = SimpleNamespace(
        agent_command=["claude"], options=SimpleNamespace(max_turns=150, model=None)
    )
    run.a = SimpleNamespace(session_id="s-1")
    run._prompt = lambda resuming: "the task"
    arguments = run._agent_arguments()
    offered = arguments[arguments.index("--tools") + 1].split(",")
    allowed = arguments[arguments.index("--allowedTools") + 1].split(",")
    assert "WebFetch" not in offered
    assert offered == allowed


def test_the_worker_states_the_reach_it_offers() -> None:
    """`reach.stated` reads the offer in the contract's terms (ADR-0098): a `Bash` call is
    `shell.sandboxed`, or `code.test` where the frame allows it; with no fetch offered, the
    only hosts a call can name are the task's, which the worker holds against the frame
    itself; with a fetch offered, the hosts are bounded at the call and not stated."""
    worker = load()
    run = object.__new__(worker._Run)
    run.fault = None
    run.body = {"task": {"goal": "g"}, "context": {}}
    run.frame = {"allowed_tools": ["code.read", "code.test"], "allowed_hosts": ["repo.example"]}
    assert run._reach() == {
        "type": "reach.stated",
        "tools": ["code.read", "code.test", "shell.sandboxed"],
        "hosts": [],
    }
    run.body = {"task": {"goal": "g", "inputs": {"hosts": ["repo.example"]}}, "context": {}}
    assert run._reach()["tools"] == ["code.read", "code.test", "shell.sandboxed", "web.fetch"]
    assert run._reach()["hosts"] == ["repo.example"]
    run.frame = {"allowed_tools": ["code.read", "web.fetch"], "allowed_hosts": ["repo.example"]}
    assert run._reach() == {"type": "reach.stated", "tools": ["code.read", "web.fetch"]}


@pytest.mark.parametrize("spelled", ["bash", "BASH", "Bash"])
def test_a_tool_is_known_whatever_the_case_the_agent_spells_it_in(spelled: str) -> None:
    """#394: an agent called `bash`, and the assignment ended as if it had called a tool outside
    the frame. The name is read without regard to case, and the frame is still what decides."""
    worker = load()
    assert worker.KNOWN_TOOLS[spelled.lower()] == "Bash"
    run = object.__new__(worker._Run)
    run.frame = {"allowed_tools": ["code.read", "code.edit", "code.test", "shell.sandboxed"]}
    tool = worker.KNOWN_TOOLS.get(spelled.lower(), spelled)
    assert run._capability_of(tool, {"command": "ls"}) == "shell.sandboxed"
    assert run._capability_of(tool, {"command": "make test"}) == "code.test"
    assert worker.KNOWN_TOOLS.get("websearch", "WebSearch") == "WebSearch", "an unknown tool stays"
