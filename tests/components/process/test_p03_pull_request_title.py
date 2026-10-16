"""The title of a pull request P-03 opens is in the Conventional Commits form (issue #472).

The title becomes the commit on `main` when the pull request is squash-merged. #463 and #470
reached `main` as the issue's sentence, without a type. Here the bundle's own steps compose the
title, its own check holds it to the form, and the repository's title check reads it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.components.run.domain.model import CheckRule, CommitTitleRule, RuleFailed
from taktus.components.run.domain.service import rules

ROOT = Path(__file__).resolve().parents[3]
P03 = ROOT / "blueprints/dev-orchestration/processes/P-03-implementation.yaml"
sys.path.insert(0, str(ROOT / "tools"))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above


def work(step_id: str) -> dict[str, Any]:
    bundle = yaml.safe_load(P03.read_text(encoding="utf-8"))
    (step,) = [s for s in bundle["steps"] if s["id"] == step_id]
    work: dict[str, Any] = step["work"]
    return work


def title(sentence: str, number: int, labels: Any, files: Any, summary: Any) -> str:
    """The title as the steps `pull-request-title` and `pull-request-title-form` give it."""
    rule = CommitTitleRule.model_validate(work("pull-request-title"))
    composed: str = rules.commit_title(rule, sentence, number, labels, files, summary)["title"]
    rules.check(CheckRule.model_validate(work("pull-request-title-form")), [composed])
    return composed


def held(text: str) -> bool:
    report = check_decisions.Report()
    check_decisions.check_title(text, report)
    return not report.failures


@pytest.mark.parametrize(
    ("sentence", "number", "labels", "files", "summary", "expected"),
    [
        (
            "A pull request P-03 opens repeats its sections and carries a closing section",
            463,
            ["priority:high", "ready", "to-taktus"],
            [{"path": "blueprints/dev-orchestration/processes/P-03-implementation.yaml"}],
            "<!-- commit-type: fix(process) -->\n## What this is about\n\nSaid.",
            "fix(process): a pull request P-03 opens repeats its sections and carries a closing "
            "section (#463)",
        ),
        (
            "make gate-adrs fails a reference to an ADR that does not exist",
            470,
            ["type:fix"],
            [{"path": "tools/check_adrs.py"}],
            "## What this is about",
            "fix: make gate-adrs fails a reference to an ADR that does not exist (#470)",
        ),
        (
            "The removal test is explained",
            9,
            [],
            [[{"path": "docs/architecture/methods.md"}], ["docs/old.md"]],
            "<!-- commit-type: feat -->",
            "docs: the removal test is explained (#9)",
        ),
    ],
)
def test_the_title_is_in_the_form_and_the_repositorys_check_holds_it(
    sentence: str, number: int, labels: Any, files: Any, summary: Any, expected: str
) -> None:
    composed = title(sentence, number, labels, files, summary)
    assert composed == expected
    assert held(composed)


def test_a_title_without_a_type_is_not_opened() -> None:
    with pytest.raises(RuleFailed, match="no type for the title"):
        title("Do it", 1, ["ready"], [{"path": "src/a.py"}], "## What this is about")
    with pytest.raises(RuleFailed):
        rules.check(CheckRule.model_validate(work("pull-request-title-form")), ["Do it (#1)"])


def test_the_bundle_and_the_repositorys_check_name_the_same_types() -> None:
    assert tuple(work("pull-request-title")["types"]) == check_decisions.COMMIT_TYPES
    pattern = work("pull-request-title-form")["conditions"][0]["matches"]
    assert "|".join(check_decisions.COMMIT_TYPES) in pattern


def test_the_pull_request_is_opened_with_the_checked_title() -> None:
    opened = work("open-pr")
    assert opened["input"]["title"] == {"$from": "pull-request-title", "$select": "title"}
    bundle = yaml.safe_load(P03.read_text(encoding="utf-8"))
    (step,) = [s for s in bundle["steps"] if s["id"] == "open-pr"]
    assert "pull-request-title-form" in step["depends_on"]
