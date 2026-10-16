"""The rule `commit_title` (ADR-0101): a title in the Conventional Commits form from a sentence,
its type from the sentence, a label, the files changed or a proposal, in that order. The rule
knows no repository: the types, the patterns and the files' rules are the bundle's."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from taktus.components.run.domain.model import CommitTitleRule, RuleFailed
from taktus.components.run.domain.service import rules

RULE = CommitTitleRule.model_validate(
    {
        "rule": "commit_title",
        "title": None,
        "number": None,
        "types": ["docs", "feat", "fix", "test"],
        "label_pattern": r"^type:(?P<type>[a-z]+)$",
        "by_files": [
            {"pattern": "^docs/", "type": "docs"},
            {"pattern": "^tests/", "type": "test"},
        ],
        "proposed": r"<!--\s*kind:\s*(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9-]+)\))?\s*-->",
    }
)


def titled(
    title: str,
    labels: Any = None,
    files: Any = None,
    proposal: Any = None,
    rule: CommitTitleRule = RULE,
) -> dict[str, Any]:
    return rules.commit_title(rule, title, 7, labels, files, proposal)


def test_a_sentence_takes_the_proposed_type_and_reads_as_a_summary() -> None:
    result = titled(
        "A pull request opens repeats its sections.",
        files=[{"path": "src/a.py"}],
        proposal="<!-- kind: fix(process) -->\n## What this is about",
    )
    assert result == {
        "title": "fix(process): a pull request opens repeats its sections (#7)",
        "type": "fix",
        "scope": "process",
        "source": "proposal",
    }


def test_an_abbreviation_keeps_its_capitals() -> None:
    assert titled("CI fails", proposal="<!-- kind: fix -->")["title"] == "fix: CI fails (#7)"
    assert titled("P-03 opens", proposal="<!-- kind: feat -->")["title"] == "feat: P-03 opens (#7)"
    assert titled("make gate-adrs fails", proposal="<!-- kind: fix -->")["title"] == (
        "fix: make gate-adrs fails (#7)"
    )


def test_a_sentence_already_in_the_form_keeps_its_type_and_scope() -> None:
    result = titled(
        "feat(run)!: steps gain a rule", labels=["type:fix"], proposal="<!-- kind: docs -->"
    )
    assert result["title"] == "feat(run)!: steps gain a rule (#7)"
    assert result["source"] == "title"


def test_a_label_decides_before_the_files_and_the_proposal() -> None:
    result = titled(
        "Correct the greeting",
        labels=["ready", "type:fix"],
        files=[{"path": "docs/a.md"}],
        proposal="<!-- kind: feat(greeting) -->",
    )
    assert result["title"] == "fix(greeting): correct the greeting (#7)"
    assert result["source"] == "labels"


def test_the_files_decide_where_every_one_matches_an_entry() -> None:
    files = [[{"path": "docs/a.md"}, {"path": "docs/b/c.md"}], ["docs/gone.md"]]
    result = titled("Explain the frame", files=files, proposal="<!-- kind: feat -->")
    assert (result["type"], result["source"]) == ("docs", "files")
    mixed = [{"path": "docs/a.md"}, {"path": "tests/test_a.py"}]
    assert titled("Explain", files=mixed, proposal="<!-- kind: feat -->")["type"] == "feat"


def test_a_label_outside_the_types_is_no_type() -> None:
    result = titled("Do it", labels=["type:wish"], proposal="<!-- kind: feat -->")
    assert result["source"] == "proposal"


def test_two_labels_naming_different_types_fail_the_step() -> None:
    with pytest.raises(RuleFailed, match="more than one type: feat, fix"):
        titled("Do it", labels=["type:fix", "type:feat"])


@pytest.mark.parametrize(
    "proposal", [None, "", "no comment here", "<!-- kind: wish -->", {"type": "feat"}]
)
def test_no_type_from_any_source_fails_the_step(proposal: Any) -> None:
    with pytest.raises(RuleFailed, match="no type for the title"):
        titled("Do it", labels=["ready"], files=[{"path": "src/a.py"}], proposal=proposal)


def test_a_scope_that_is_not_lower_case_words_is_dropped() -> None:
    assert titled("feat(The Run): x")["title"] == "feat: x (#7)"


@pytest.mark.parametrize("title", ["", "   ", None, 3])
def test_a_title_that_is_no_sentence_fails_the_step(title: Any) -> None:
    with pytest.raises(RuleFailed, match="not a sentence"):
        rules.commit_title(RULE, title, 7, None, None, "<!-- kind: feat -->")


def test_a_pattern_without_a_type_group_or_a_files_type_outside_the_types_is_refused() -> None:
    base = {"rule": "commit_title", "title": "x", "number": 1, "types": ["feat"]}
    with pytest.raises(ValidationError, match="no group `type`"):
        CommitTitleRule.model_validate({**base, "proposed": "(?P<kind>[a-z]+)"})
    with pytest.raises(ValidationError, match="not among the types"):
        CommitTitleRule.model_validate({**base, "by_files": [{"pattern": "^d", "type": "docs"}]})
