"""The session hook refuses `gh pr ready` unless `make verify` stamped the pushed head
(ADR-0096 §4, #390). Run against a throwaway repository with a remote of its own."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "ready-needs-verify.sh"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 — git with arguments this test assembles
        ["git", "-c", "user.name=t", "-c", "user.email=t@localhost", *args],  # noqa: S607
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--quiet", "--bare", str(remote))
    work = tmp_path / "work"
    git(tmp_path, "clone", "--quiet", str(remote), str(work))
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    git(work, "add", "a.txt")
    git(work, "commit", "--quiet", "-m", "a")
    git(work, "push", "--quiet", "-u", "origin", "HEAD")
    return work


def hook(cwd: Path, command: str) -> subprocess.CompletedProcess[str]:
    call = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(  # noqa: S603 — our own script
        [str(HOOK)], cwd=cwd, input=call, capture_output=True, text=True, check=False
    )


def stamp(clone: Path) -> None:
    (clone / ".git" / "taktus-verified").write_text(git(clone, "rev-parse", "HEAD") + "\n")


def test_any_other_command_passes(clone: Path) -> None:
    assert hook(clone, "gh pr view 12").returncode == 0


def test_ready_without_a_stamp_is_refused(clone: Path) -> None:
    refused = hook(clone, "gh pr ready 12")
    assert refused.returncode == 2 and "make verify" in refused.stderr


def test_ready_with_the_stamp_of_the_pushed_head_passes(clone: Path) -> None:
    stamp(clone)
    assert hook(clone, "gh pr ready").returncode == 0


def test_ready_with_a_stamp_of_an_older_head_is_refused(clone: Path) -> None:
    stamp(clone)
    (clone / "b.txt").write_text("b\n", encoding="utf-8")
    git(clone, "add", "b.txt")
    git(clone, "commit", "--quiet", "-m", "b")
    assert hook(clone, "gh pr ready").returncode == 2


def test_ready_before_the_verified_head_is_pushed_is_refused(clone: Path) -> None:
    (clone / "b.txt").write_text("b\n", encoding="utf-8")
    git(clone, "add", "b.txt")
    git(clone, "commit", "--quiet", "-m", "b")
    stamp(clone)
    refused = hook(clone, "gh pr ready")
    assert refused.returncode == 2 and "push first" in refused.stderr


def test_turning_a_pull_request_back_into_a_draft_passes(clone: Path) -> None:
    assert hook(clone, "gh pr ready 12 --undo").returncode == 0
