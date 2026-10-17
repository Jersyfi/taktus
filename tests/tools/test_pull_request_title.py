"""A pull request's title is in the Conventional Commits form, for every author (issue #472).

The title becomes the commit on `main` when the pull request is squash-merged (CLAUDE.md §9).
`tools/check_decisions.py --pr-title` fails one without the form, whoever wrote it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above


def failures(title: str) -> list[str]:
    report = check_decisions.Report()
    check_decisions.check_title(title, report)
    return report.failures


@pytest.mark.parametrize(
    "title",
    [
        "feat(process): P-03 asks its agent for make check (v15, #493) (#495)",
        "fix: the coding worker counts its output tokens (#373)",
        "docs(research): the replay after #392, as a tool",
        "build(deps): bump mako from 1.4.1 to 1.4.2",
        "refactor!: the run reads its steps once",
        'Revert "feat(run): steps gain a rule (#12)"',
    ],
)
def test_a_title_in_the_form_passes(title: str) -> None:
    assert failures(title) == []


@pytest.mark.parametrize(
    "title",
    [
        "A pull request P-03 opens repeats its sections and carries a closing section (#463)",
        "make gate-adrs fails a reference to an ADR that does not exist (#470)",
        "feature: a type the repository does not use",
        "Fix: a type in capitals",
        "fix:no space after the colon",
        "fix(The Run): a scope with capitals and a space",
        'Revert "a sentence without a type"',
        "",
    ],
)
def test_a_title_without_the_form_fails(title: str) -> None:
    assert failures(title), title


def test_the_title_is_checked_for_a_dependency_bot_too(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Bumps mako.", encoding="utf-8")
    argv = ["--pr-body", str(body), "--author", "dependabot[bot]", "--pr-title"]
    assert check_decisions.main([*argv, "Bump mako from 1.4.1 to 1.4.2"]) == 1
    assert check_decisions.main([*argv, "build(deps): bump mako from 1.4.1 to 1.4.2"]) == 0
