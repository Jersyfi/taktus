"""The rule `match` (ADR-0199): two lists matched entry by entry by a key, every entry that is
not a clean match named — the same lists, the same result."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from taktus.components.run.domain.model import MatchRule, RuleFailed
from taktus.components.run.domain.service import rules

PAID: list[dict[str, Any]] = [
    {"id": "sub_1", "customer": "cus_1", "items": [{"product": "prod_pro", "quantity": 5}]},
    {
        "id": "sub_2",
        "customer": "cus_2",
        "items": [{"product": "prod_pro", "quantity": 1}, {"product": "prod_extra", "quantity": 1}],
    },
    {"id": "sub_3", "customer": "cus_3", "items": [{"product": "prod_pro", "quantity": 2}]},
]
GRANTED: list[dict[str, Any]] = [
    {"customer": "cus_1", "product": "prod_pro", "quantity": "5"},
    {"customer": "cus_2", "product": "prod_pro", "quantity": 1},
    {"customer": "cus_2", "product": "prod_extra", "quantity": 1},
    {"customer": "cus_4", "product": "prod_pro", "quantity": 1},
]


def rule(**given: Any) -> MatchRule:
    document = {
        "rule": "match",
        "left": {"items": None, "key": ["customer", "items.product"], "each": "items"},
        "right": {"items": None, "key": ["customer", "product"]},
        **given,
    }
    return TypeAdapter(MatchRule).validate_python(document)


def test_every_item_of_a_payment_is_matched_and_each_side_s_strays_are_named() -> None:
    matched = rules.match(rule(), PAID, GRANTED)
    assert matched["matched"] == 3, "both items of the second subscription found their grant"
    assert [e["customer"] for e in matched["left_only"]] == ["cus_3"], "paid, not granted"
    assert matched["right_only"] == [GRANTED[3]], "granted, not paid"
    assert matched["mismatches"] == 2
    assert matched["first"]["kind"] == "left_only"


def test_a_compared_field_that_differs_is_a_mismatch_and_numbers_compare_as_numbers() -> None:
    compared = rule(compare=[{"left": "items.quantity", "right": "quantity"}])
    granted = [{**GRANTED[0], "quantity": "4"}, *GRANTED[1:3]]
    matched = rules.match(compared, PAID[:2], granted)
    [differing] = matched["differing"]
    assert differing["key"] == ["cus_1", "prod_pro"]
    assert differing["fields"] == [
        {"left": "items.quantity", "right": "quantity", "left_value": 5, "right_value": "4"}
    ]
    assert matched["matched"] == 2 and matched["mismatches"] == 1
    assert rules.match(compared, PAID[:2], GRANTED[:3])["mismatches"] == 0, '"5" equals 5'


def test_an_entry_without_its_key_and_a_key_seen_twice_are_mismatches_never_matches() -> None:
    granted = [GRANTED[0], GRANTED[0], {"product": "prod_pro"}]
    matched = rules.match(rule(), PAID[:1], granted)
    assert matched["matched"] == 0
    assert matched["duplicates"] == [{"side": "right", "key": ["cus_1", "prod_pro"], "count": 2}]
    assert matched["unkeyed"] == [{"side": "right", "entry": {"product": "prod_pro"}}]
    assert matched["left_only"] == [] and matched["mismatches"] == 2


def test_two_empty_lists_match_with_nothing_to_name() -> None:
    assert rules.match(rule(), [], []) == {
        "matched": 0,
        "left_only": [],
        "right_only": [],
        "differing": [],
        "unkeyed": [],
        "duplicates": [],
        "mismatches": 0,
    }


def test_the_same_lists_give_the_same_result() -> None:
    assert rules.match(rule(), PAID, GRANTED) == rules.match(rule(), PAID, GRANTED)


def test_what_is_not_a_list_of_objects_fails_the_step() -> None:
    with pytest.raises(RuleFailed, match="left is not a list"):
        rules.match(rule(), {"customer": "cus_1"}, [])
    with pytest.raises(RuleFailed, match="an item of right is not an object"):
        rules.match(rule(), [], ["cus_1"])
    with pytest.raises(RuleFailed, match="is not a list"):
        rules.match(rule(), [{"customer": "cus_1", "items": "prod_pro"}], [])


def test_keys_of_different_lengths_are_refused_when_the_process_is_read() -> None:
    with pytest.raises(ValidationError, match="field by field"):
        rule(right={"items": None, "key": ["customer"]})


# Further readings of a side (ADR-0329): the subscriptions of several payment providers.

WALLET = {
    "output": {
        "subscriptions": [{"id": "I-1", "customer": "PAYER1", "items": [{"product": "prod_pro"}]}]
    }
}
SKIPPED = {"skipped": True, "because": "the run names no third provider"}


def several() -> MatchRule:
    more = [{"reading": None, "select": "output.subscriptions"}] * 2
    return rule(
        left={"items": None, "key": ["customer", "items.product"], "each": "items", "more": more}
    )


def test_every_provider_s_payments_are_matched_and_a_skipped_reading_adds_nothing() -> None:
    granted = [*GRANTED[:3], {"customer": "PAYER1", "product": "prod_pro", "quantity": 1}]
    one_provider = rules.match(rule(), PAID[:2], granted)
    assert one_provider["right_only"] == [granted[3]], "read alone, the wallet's grant is unpaid"

    matched = rules.match(several(), PAID[:2], granted, [WALLET, SKIPPED])
    assert matched["matched"] == 4
    assert matched["mismatches"] == 0, "the second provider's payment pays the grant"


def test_a_further_reading_without_its_list_fails_the_rule_and_is_never_read_as_empty() -> None:
    with pytest.raises(RuleFailed, match=r"has no 'output\.subscriptions'"):
        rules.match(several(), PAID, GRANTED, [WALLET, {"output": {}}])
    with pytest.raises(RuleFailed, match="is not a list"):
        rules.match(several(), PAID, GRANTED, [WALLET, {"output": {"subscriptions": "none"}}])
