"""The rule `ready`: the backlog's ready standard (DEC-0051) over a repository's reading of an
issue, as P-03's admission and P-02's search for missing sections evaluate it (issue #70)."""

from __future__ import annotations

from typing import Any

import pytest

from taktus.components.run.domain.model import ReadyRule, RuleFailed, UnsupportedWork, parse_work
from taktus.components.run.domain.service import ready, rules
from taktus.shared.v1 import ExactnessClass, Method, Step

FORM = """### What must be achieved

The scheduler starts a run from a bundle's trigger.

### How it is verified

{verified}

### Where the boundary lies

Event triggers are not part of it.

### Component

run

### Source

docs/roadmap.md, 0.2.0

### Blocked by

{blocked}
"""

RECORDS = [{"name": "README.md"}, {"name": "DEC-0999-a-token.md"}, {"name": "DEC-0044-x.md"}]


def reading(**changes: Any) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "number": 7,
        "state": "open",
        "is_pull_request": False,
        "body": FORM.format(verified="A test sees one run per tick.", blocked="nothing"),
        "labels": ["priority:normal", "ready", "task"],
        "milestone": "0.2.0",
    }
    return issue | changes


def admission() -> ReadyRule:
    return ReadyRule(rule="ready", expect="ready", issue={}, open_records=[], open_issues=[])


def test_a_ready_issue_is_admitted_with_nothing_missing() -> None:
    result = rules.ready(admission(), reading(), RECORDS, [{"number": 3}])
    assert result == {"number": 7, "ready": True, "reasons": [], "missing": []}


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"milestone": None}, "no milestone"),
        ({"labels": ["ready", "task"]}, "not exactly one priority label"),
        ({"labels": ["priority:normal", "task"]}, "not labelled ready"),
        ({"labels": ["in-progress", "priority:normal", "ready"]}, "claimed: labelled in-progress"),
        ({"state": "closed"}, "not open: closed"),
        ({"is_pull_request": True}, "a pull request, not an issue"),
        (
            {"body": FORM.format(verified="_No response_", blocked="nothing")},
            "section 'How it is verified' is missing or empty",
        ),
        (
            {"body": FORM.format(verified="v", blocked="DEC-0999 and #3")},
            "blocked by DEC-0999, still open; blocked by #3, still open",
        ),
    ],
)
def test_an_admission_refuses_naming_the_reason(changes: dict[str, Any], reason: str) -> None:
    with pytest.raises(RuleFailed, match="issue #7 is not ready: ") as refused:
        rules.ready(admission(), reading(**changes), RECORDS, [3, 9])
    assert reason in str(refused.value)


def test_a_closed_record_or_issue_does_not_block() -> None:
    body = FORM.format(verified="v", blocked="NEED-0012, DEC-0043 and #4")
    assert rules.ready(admission(), reading(body=body), RECORDS, [3])["ready"] is True


def test_sections_missing_names_them_and_refuses_an_issue_that_has_them_all() -> None:
    rule = ReadyRule(rule="ready", expect="sections_missing", issue={})
    body = FORM.format(verified="", blocked="nothing").replace("Event triggers", "")
    lacking = reading(body=body.replace("are not part of it.", ""), labels=[], milestone=None)
    result = rules.ready(rule, lacking, None, None)
    assert result["missing"] == ["How it is verified", "Where the boundary lies"]
    with pytest.raises(RuleFailed, match="carries every section already"):
        rules.ready(rule, reading(), None, None)
    with pytest.raises(RuleFailed, match="not open"):
        rules.ready(rule, reading(state="closed", body=body), None, None)


def test_an_admission_must_read_what_is_open() -> None:
    step = Step(
        id="admit", method=Method.RULE, reason="r", rejected=[], exactness=ExactnessClass.EXACT
    )
    work = {"rule": "ready", "expect": "ready", "issue": {"$from": "read"}}
    with pytest.raises(UnsupportedWork, match="open_records and open_issues"):
        parse_work(step, work)
    given = {**work, "open_records": {"$from": "a"}, "open_issues": {"$from": "b"}}
    assert isinstance(parse_work(step, given), ReadyRule)


def test_a_footer_after_a_rule_is_no_blocker_and_hides_none() -> None:
    """The form ends at a horizontal rule: a footer naming records is not read as a blocker,
    and prose under "Blocked by" is still caught when a footer names records after it."""
    form = (
        "### What must be achieved\n\nA.\n\n### How it is verified\n\nB.\n\n"
        "### Where the boundary lies\n\nC.\n\n### Component\n\nrun\n\n### Blocked by\n\n{blocked}\n"
        "\n---\n\nWritten under DEC-0051 and #59.\n"
    )
    labels = {"ready", "task", "priority:normal"}

    def reasons_for(blocked: str) -> list[str]:
        return ready.reasons(
            number=7,
            body=form.format(blocked=blocked),
            labels=labels,
            milestone="0.2.0",
            open_record_ids={"DEC-0051"},
            open_issues={59},
        )

    assert ready.sections(form.format(blocked="nothing"))["Blocked by"] == "nothing"
    assert reasons_for("nothing") == []
    assert reasons_for("needs a decision request on the fallback") == [
        "'Blocked by' names no NEED, DEC or issue, and is not 'nothing'"
    ]
