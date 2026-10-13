"""The rule `extract` (ADR-0095): what a pattern names in a list of texts, less what it names
in another. P-03 derives with it the references that reserve the numbers of the records its
change adds; the rule itself knows no register."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from taktus.components.run.domain.model import ExtractRule, RuleFailed
from taktus.components.run.domain.service import rules

PATTERN = r"^records/(?:open/)?(?P<id>(?:A|B)-[0-9]{4})-[a-z-]+\.md$"


def extract(values: Any, excluding: Any = None, text: str = "refs/held/${id}") -> list[str]:
    rule = ExtractRule(rule="extract", values=None, pattern=PATTERN, text=text)
    result: list[str] = rules.extract(rule, values, excluding)["extracted"]
    return result


def test_what_the_values_name_less_what_the_exclusions_name_sorted_and_distinct() -> None:
    changeset = [
        {"path": "records/B-0007-a-new-one.md", "content": "x"},
        {"path": "records/A-0003-an-answered-one.md", "content": "x"},
        {"path": "records/open/A-0009-a-new-request.md", "content": "x"},
        {"path": "records/open/A-0009-a-new-request.md", "content": "x"},
        {"path": "src/B-0001-not-a-record.md", "content": "x"},
        "records/B-0008-given-as-text.md",
    ]
    listing = [
        [{"name": "A-0003-an-answered-one.md", "path": "records/A-0003-an-answered-one.md"}],
        [{"name": "README.md", "path": "records/open/README.md"}],
    ]
    assert extract(changeset, listing) == [
        "refs/held/A-0009",
        "refs/held/B-0007",
        "refs/held/B-0008",
    ]


def test_a_record_moved_or_renamed_keeps_its_identifier_and_is_left_out() -> None:
    """Exclusion is by the composed text, not by the path: a record the base holds under
    another path or another title is still the base's."""
    moved = [{"path": "records/A-0003-renamed.md"}]
    held = [{"path": "records/open/A-0003-as-it-was.md"}]
    assert extract(moved, held) == []


def test_nothing_named_is_an_empty_result_never_a_failure() -> None:
    assert extract([]) == []
    assert extract(None) == []
    assert extract([{"path": "hello.txt"}], None) == []


@pytest.mark.parametrize("values", ["records/A-0001-x.md", [{"content": "no path"}], [3]])
def test_what_is_neither_a_list_nor_texts_nor_entries_fails_the_step(values: Any) -> None:
    with pytest.raises(RuleFailed):
        extract(values)


def test_a_group_the_text_names_must_be_in_the_pattern() -> None:
    with pytest.raises(ValidationError, match="does not group"):
        ExtractRule(rule="extract", values=[], pattern=r"(?P<id>x)", text="${other}")
    with pytest.raises(ValidationError, match="does not compile"):
        ExtractRule(rule="extract", values=[], pattern="(", text="x")
