"""A coding assignment that fails says why (#375).

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
