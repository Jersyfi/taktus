"""The task's command after the work reads the artifact its `input` names on its standard input
(ADR-0101), and nothing without one. Both coding workers are separate deployables; each is
loaded by its path."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKERS = {name: ROOT / "workers" / name / "worker.py" for name in ("claudecode", "codex")}


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"worker_{name}_after_input", WORKERS[name])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_the_command_reads_what_it_is_given_and_nothing_otherwise(
    name: str, tmp_path: Path
) -> None:
    worker = load(name)
    summary = "## What this is about\n\nA greeting, … and more.\n".encode()
    assert worker.run_after(("cat",), tmp_path, summary) == (summary, None)
    assert worker.run_after(("cat",), tmp_path) == (b"", None)


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_a_command_that_fails_names_the_end_of_its_error_output(
    name: str, tmp_path: Path
) -> None:
    worker = load(name)
    argv = (sys.executable, "-c", "import sys; sys.stderr.write('the check fails'); sys.exit(1)")
    output, failure = worker.run_after(argv, tmp_path, b"anything")
    assert output == b""
    assert failure == "the command after the work exited with 1: the check fails"
