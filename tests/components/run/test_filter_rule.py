"""The rule `filter` (ADR-0192 §1): the items of a reading its conditions keep, less those an
earlier run already marked, ordered and limited — the same lists, the same result."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from taktus.components.run.domain.model import FilterRule, RuleFailed
from taktus.components.run.domain.service import rules

ERRORS: list[dict[str, Any]] = [
    {"id": "11", "title": "TypeError", "culprit": "app/feed.ts", "users": 3},
    {"id": "12", "title": "Charge failed", "culprit": "api/payments/charge", "users": 1},
    {"id": "13", "title": "Timeout", "culprit": "app/list.ts", "users": 140},
    {"id": "14", "title": "Null", "culprit": "app/settings.ts"},
]


def rule(**given: Any) -> FilterRule:
    return TypeAdapter(FilterRule).validate_python({"rule": "filter", "items": None, **given})


def test_any_of_its_conditions_keeps_an_item_and_a_missing_field_fails_only_its_condition() -> None:
    kept = rules.filter_items(
        rule(
            any=[{"field": "users", "at_least": 50}, {"field": "culprit", "matches": "payment"}],
            order="users",
            descending=True,
        ),
        ERRORS,
        None,
    )
    assert [i["id"] for i in kept["items"]] == ["13", "12"]
    assert kept["count"] == 2 and kept["first"]["id"] == "13"


def test_an_item_an_earlier_run_marked_is_left_out_and_nothing_kept_has_no_first() -> None:
    filed = [{"number": 7, "body": "Taktus filed this.\n\nerrors-issue:13"}, {"number": 8}]
    kept = rules.filter_items(
        rule(all=[{"field": "users", "at_least": 50}], marker="errors-issue:${id}", within="body"),
        ERRORS,
        filed,
    )
    assert kept == {"items": [], "count": 0}


def test_all_its_conditions_must_hold_and_numbers_compare_as_numbers() -> None:
    kept = rules.filter_items(
        rule(all=[{"field": "users", "at_least": "2"}, {"field": "users", "at_most": 100}]),
        ERRORS,
        None,
    )
    assert [i["id"] for i in kept["items"]] == ["11"]
    limited = rules.filter_items(rule(order="users", limit=1), ERRORS, None)
    assert limited["first"]["id"] == "14", "an item without the field sorts first"


def test_what_is_not_a_list_of_objects_fails_the_step() -> None:
    with pytest.raises(RuleFailed, match="items is not a list"):
        rules.filter_items(rule(), {"id": 1}, None)
    with pytest.raises(RuleFailed, match="not an object"):
        rules.filter_items(rule(), ["text"], None)


def test_a_condition_that_tests_nothing_and_excluding_without_a_marker_are_refused() -> None:
    with pytest.raises(ValidationError, match="tests nothing"):
        rule(all=[{"field": "users"}])
    with pytest.raises(ValidationError, match="needs a `marker`"):
        rule(excluding=[])
