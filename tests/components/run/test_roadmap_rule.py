"""The rules `backlog` and `roadmap`: the backlog in its order and the roadmap held against the
open issues, as P-01 Roadmap control evaluates them (issue #71)."""

from __future__ import annotations

from typing import Any

import pytest

from taktus.components.run.domain.model import (
    BacklogRule,
    RoadmapRule,
    RuleFailed,
    parse_work,
)
from taktus.components.run.domain.service import roadmap as plan
from taktus.components.run.domain.service import rules
from taktus.shared.v1 import ExactnessClass, Method, Step

FORM = """### What must be achieved

Something.

### How it is verified

{verified}

### Where the boundary lies

Nothing else.

### Component

run

### Blocked by

{blocked}
"""

ROADMAP = """# Roadmap

Intro that names #99, which is not an item.

### `0.1.0` — first
The first item (#2) · the second **item**
(#3, #9)

**Complete when** it is done.

**Done so far:** everything (#42) · and more.

### `0.2.0` — second
An item without an issue · a greeting (#4)

**Complete when** it is done.

---

## After

Nothing (#77).
"""


def issue(number: int, milestone: str | None, *labels: str, **changes: Any) -> dict[str, Any]:
    reading: dict[str, Any] = {
        "number": number,
        "title": f"task {number}",
        "state": "open",
        "is_pull_request": False,
        "body": FORM.format(verified="A test.", blocked="nothing"),
        "labels": sorted(labels),
        "milestone": milestone,
    }
    return reading | changes


def backlog_rule() -> BacklogRule:
    return BacklogRule(rule="backlog", issues=[], open_records=[])


def roadmap_rule() -> RoadmapRule:
    return RoadmapRule(rule="roadmap", roadmap="", issues=[])


def test_the_items_are_read_up_to_the_completion_criterion() -> None:
    found = plan.milestones(ROADMAP)
    assert [m["milestone"] for m in found] == ["0.1.0", "0.2.0"]
    assert found[0]["items"] == [
        {"text": "The first item (#2)", "issues": [2]},
        {"text": "the second **item** (#3, #9)", "issues": [3, 9]},
    ]
    assert [i["issues"] for i in found[1]["items"]] == [[], [4]]


def test_a_consistent_roadmap_and_backlog_disagree_nowhere() -> None:
    issues = [
        issue(2, "0.1.0", "ready", "priority:high"),
        issue(3, "0.1.0", "priority:low"),
        issue(4, "0.2.0", "ready", "priority:normal"),
        issue(5, None),  # no milestone and not named: not a roadmap item, no disagreement
        issue(6, None, "report"),
        issue(7, "0.2.0", "decision-request"),
    ]
    roadmap = ROADMAP.replace("An item without an issue · ", "")
    result = rules.roadmap(roadmap_rule(), roadmap, issues)
    assert result["disagreements"] == [] and result["disagreements_text"] == "none"
    assert result["milestones"] == ["0.1.0", "0.2.0"]


def test_each_disagreement_is_found_once() -> None:
    issues = [
        issue(2, "0.1.0"),
        issue(3, "0.2.0"),  # named under 0.1.0, in 0.2.0
        issue(4, None),  # named under 0.2.0, without a milestone
        issue(8, "0.2.0"),  # named nowhere
        issue(10, "0.2.0", is_pull_request=True),  # a pull request is not work
    ]
    result = rules.roadmap(roadmap_rule(), ROADMAP, issues)
    assert result["disagreements_text"].splitlines() == [
        "- 0.2.0: the item “An item without an issue” names no issue",
        "- #3 is in milestone 0.2.0; the roadmap places it in 0.1.0",
        "- #4 has no milestone; the roadmap places it in 0.2.0",
        "- #8 is in milestone 0.2.0; the roadmap does not name it",
    ]


def test_a_text_without_a_milestone_is_not_a_roadmap() -> None:
    with pytest.raises(RuleFailed, match="not a roadmap"):
        rules.roadmap(roadmap_rule(), "# Something else\n", [])
    with pytest.raises(RuleFailed, match="not a reading with a number"):
        rules.roadmap(roadmap_rule(), ROADMAP, [{"title": "no number"}])


def test_the_backlog_is_grouped_and_ordered_as_a_session_reads_it() -> None:
    issues = [
        issue(9, "0.2.0", "ready", "priority:high"),
        issue(3, "0.2.0", "ready", "priority:low"),
        issue(8, "0.1.0", "ready", "priority:low"),
        issue(4, "0.2.0", "ready", "priority:high", "in-progress"),
        issue(5, "0.1.0", "priority:normal"),
        issue(6, None, "report"),
    ]
    result = rules.backlog(backlog_rule(), issues, [])
    assert [e["number"] for e in result["ready"]] == [8, 9, 3]
    assert [e["number"] for e in result["claimed"]] == [4]
    assert [e["number"] for e in result["not_ready"]] == [5]
    assert result["text"].splitlines()[:5] == [
        "**Ready, in the order a session takes them**",
        "- #8 · 0.1.0 · low · task 8",
        "- #9 · 0.2.0 · high · task 9",
        "- #3 · 0.2.0 · low · task 3",
        "",
    ]
    assert result["disagreements"] == [] and result["disagreements_text"] == "none"


def test_a_ready_label_on_content_that_fails_is_a_disagreement_and_a_blocker_is_not() -> None:
    lacking = FORM.format(verified="_No response_", blocked="nothing")
    blocked = FORM.format(verified="A test.", blocked="DEC-0999 and #2")
    issues = [
        issue(2, "0.1.0", "priority:low"),
        issue(7, "0.2.0", "ready", "priority:normal", body=lacking),
        issue(11, "0.2.0", "ready", "priority:normal", body=blocked),
        issue(12, None, "ready", "priority:normal", "in-progress"),
    ]
    records = [{"name": "DEC-0999-open.md"}, {"name": "README.md"}]
    result = rules.backlog(backlog_rule(), issues, records)
    assert result["disagreements_text"].splitlines() == [
        "- #7 is labelled `ready` and fails the standard: "
        "section 'How it is verified' is missing or empty",
        "- #12 is labelled `ready` and fails the standard: no milestone",
    ]
    not_ready = {e["number"]: e["reasons"] for e in result["not_ready"]}
    assert not_ready[11] == ["blocked by DEC-0999, still open", "blocked by #2, still open"]


@pytest.mark.parametrize(
    ("work", "kind"),
    [
        (
            {"rule": "backlog", "issues": {"$from": "a"}, "open_records": {"$from": "b"}},
            BacklogRule,
        ),
        ({"rule": "roadmap", "roadmap": {"$from": "a"}, "issues": {"$from": "b"}}, RoadmapRule),
    ],
)
def test_both_parse_as_rules_admissible_for_exact(work: dict[str, Any], kind: type) -> None:
    step = Step(id="s", method=Method.RULE, reason="r", rejected=[], exactness=ExactnessClass.EXACT)
    assert isinstance(parse_work(step, work), kind)
