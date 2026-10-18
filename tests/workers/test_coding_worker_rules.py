"""The coding workers hand the target repository's `AGENTS.md` to their agent (#407, ADR-0113).

`AGENTS.md` is the open convention's file of a repository's rules for coding agents. Each coding
worker reads it at the root of the workspace and puts it into the agent's brief, before the task,
once per session. A link that leads out of the workspace is never followed, and a file beyond the
bound is cut with a line that says so. The first coding worker's agent reads its own file by
itself; where that file imports `AGENTS.md`, the brief does not carry it a second time. Both
coding workers are separate deployables; each is loaded by its path. That the agent receives the
brief through the worker's HTTP interface is `tests/conformance/test_coding_workers_brief.py`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKERS = {name: ROOT / "workers" / name / "worker.py" for name in ("claudecode", "codex")}
RULES = "# Rules\n\nRun `make check` before every commit.\n"
TASK: dict[str, Any] = {"goal": "Add a greeting.", "acceptance": ["hello.txt exists"]}


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"worker_{name}_rules", WORKERS[name])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prompt_of(worker: ModuleType, workspace: Path, *, resuming: bool = False) -> str:
    """The prompt an assignment in `workspace` gives the agent, built as the run builds it."""
    run = worker._Run.__new__(worker._Run)
    run.body = {"task": dict(TASK)}
    run.workspace = workspace
    prompt: str = run._prompt(resuming)
    return prompt


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_the_brief_carries_agents_md_before_the_task(name: str, tmp_path: Path) -> None:
    worker = load(name)
    (tmp_path / "AGENTS.md").write_text(RULES, encoding="utf-8")
    prompt = prompt_of(worker, tmp_path)
    assert RULES.strip() in prompt
    assert prompt.index("--- AGENTS.md ---") < prompt.index(RULES.strip()) < prompt.index("Goal:")
    assert "the lines above win" in prompt, "the worker's instructions outrank the repository's"


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_a_repository_without_agents_md_gets_the_brief_it_had(name: str, tmp_path: Path) -> None:
    worker = load(name)
    prompt = prompt_of(worker, tmp_path)
    assert "AGENTS.md" not in prompt
    assert prompt.startswith("You are an execution unit of an orchestrator.")
    assert prompt.endswith("Acceptance:\n- hello.txt exists")
    (tmp_path / "AGENTS.md").write_text("\n  \n", encoding="utf-8")
    assert "AGENTS.md" not in prompt_of(worker, tmp_path), "an empty file carries no rule"


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_a_resumed_session_is_not_given_the_rules_again(name: str, tmp_path: Path) -> None:
    """The session holds them from its first prompt; the agent re-reads its context at every
    call, so a second copy would be paid for at every call (#511)."""
    worker = load(name)
    (tmp_path / "AGENTS.md").write_text(RULES, encoding="utf-8")
    prompt = prompt_of(worker, tmp_path, resuming=True)
    assert prompt.startswith("Continue the task from where you stopped")
    assert RULES.strip() not in prompt


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_a_link_out_of_the_workspace_is_not_followed(name: str, tmp_path: Path) -> None:
    worker = load(name)
    secret = tmp_path / "credential"
    secret.write_text("made-up-credential-value", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").symlink_to(secret)
    assert worker.repository_rules(workspace) is None
    assert "made-up-credential-value" not in prompt_of(worker, workspace)
    # A link inside the workspace is the repository's own file and is read.
    (workspace / "docs").mkdir()
    (workspace / "docs" / "rules.md").write_text(RULES, encoding="utf-8")
    (workspace / "AGENTS.md").unlink()
    (workspace / "AGENTS.md").symlink_to(workspace / "docs" / "rules.md")
    assert worker.repository_rules(workspace) == RULES.strip()


@pytest.mark.parametrize("name", sorted(WORKERS))
def test_a_file_beyond_the_bound_is_cut_with_a_line_that_says_so(name: str, tmp_path: Path) -> None:
    worker = load(name)
    (tmp_path / "AGENTS.md").write_text("x" * (worker.RULES_LIMIT + 500), encoding="utf-8")
    rules = worker.repository_rules(tmp_path)
    assert rules is not None
    assert rules.startswith("x" * worker.RULES_LIMIT)
    assert rules.endswith("read the rest there.]")
    assert "x" * (worker.RULES_LIMIT + 1) not in rules


@pytest.mark.parametrize(
    ("own", "carried"),
    [
        ("# Rules of this agent\n\n@AGENTS.md\n", False),
        ("Read @AGENTS.md first.\n", True),
        ("# Rules of this agent\n\nKeep it short.\n", True),
    ],
)
def test_the_first_agent_is_not_given_what_its_own_file_imports(
    own: str, carried: bool, tmp_path: Path
) -> None:
    """The first coding worker's agent reads `CLAUDE.md` by itself and resolves a line
    `@AGENTS.md` in it. The brief then leaves `AGENTS.md` out; a mention that is not such a
    line imports nothing, and the brief carries it."""
    worker = load("claudecode")
    (tmp_path / "AGENTS.md").write_text(RULES, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(own, encoding="utf-8")
    assert (RULES.strip() in prompt_of(worker, tmp_path)) is carried


def test_this_repository_s_agents_md_points_to_its_doctrine_and_is_handed_over() -> None:
    """This repository keeps its doctrine in `CLAUDE.md`; `AGENTS.md` points to it and carries
    no rule of its own (CLAUDE.md §9, ADR-0113 §5). Both workers hand the pointer over: the first
    one's agent reads the doctrine by itself, the second one's through the pointer."""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "[`CLAUDE.md`](CLAUDE.md)" in text
    assert len(text.splitlines()) <= 10, "a pointer, not a second doctrine"
    for name in sorted(WORKERS):
        assert load(name).repository_rules(ROOT) == text.strip()
    assert load("claudecode").agent_reads_rules(ROOT) is False
