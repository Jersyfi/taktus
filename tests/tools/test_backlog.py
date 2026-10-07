"""The backlog's ready standard and its order (DEC-0051), on issues given as data — no `gh`.

An issue is ready when it carries the three sections of a use case, a component, a milestone,
one priority label and nothing open under "Blocked by"; a session takes the earliest milestone,
then the highest priority, then the lowest number, and skips a claimed issue.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import backlog  # noqa: E402 — a script under tools/, found through the line above
from backlog import Issue  # noqa: E402

FORM = """### What must be achieved

The scheduler starts a run from a bundle's trigger.

### How it is verified

A test with a fake clock sees one run started per tick that is due.

### Where the boundary lies

Event triggers are not part of it.

### Component

run

### Source

docs/roadmap.md, 0.2.0

### Blocked by

{blocked}
"""


def issue(
    number: int = 7,
    *,
    blocked: str = "nothing",
    labels: tuple[str, ...] = ("ready", "priority:normal"),
    milestone: str | None = "0.2.0",
    body: str | None = None,
) -> Issue:
    return Issue(
        number=number,
        title=f"task {number}",
        body=FORM.format(blocked=blocked) if body is None else body,
        labels=set(labels),
        milestone=milestone,
    )


def test_an_issue_in_the_shape_of_the_form_is_ready() -> None:
    task = issue()
    task.reasons = backlog.assess(task, set(), set())
    assert task.reasons == [] and task.ready


def test_the_sections_are_read_as_a_person_writes_them_too() -> None:
    body = FORM.format(blocked="nothing").replace(
        "### What must be achieved", "## 1. What must be achieved"
    )
    assert backlog.assess(issue(body=body), set(), set()) == []


def test_a_missing_or_empty_section_is_named() -> None:
    body = FORM.format(blocked="nothing").replace(
        "Event triggers are not part of it.", "_No response_"
    )
    assert backlog.assess(issue(body=body), set(), set()) == [
        "section 'Where the boundary lies' is missing or empty"
    ]


def test_no_milestone_no_priority_no_component_are_each_a_reason() -> None:
    body = FORM.format(blocked="nothing").replace("\nrun\n", "\n\n")
    reasons = backlog.assess(issue(body=body, labels=(), milestone=None), set(), set())
    assert reasons == [
        "not labelled ready",
        "no component",
        "no milestone",
        "not exactly one priority label",
    ]


def test_an_open_need_decision_or_issue_blocks_and_a_closed_one_does_not() -> None:
    task = issue(blocked="NEED-0011, DEC-0044 and #41")
    assert backlog.assess(task, {"NEED-0011"}, {41, 7}) == [
        "blocked by NEED-0011, still open",
        "blocked by #41, still open",
    ]
    assert backlog.assess(task, set(), set()) == []


def test_blocked_by_must_name_something_or_say_nothing() -> None:
    reasons = backlog.assess(issue(blocked="the deployment"), set(), set())
    assert reasons == ["'Blocked by' names no NEED, DEC or issue, and is not 'nothing'"]
    body = FORM.format(blocked="nothing").split("### Blocked by")[0]
    assert backlog.assess(issue(body=body), set(), set()) == [
        "no 'Blocked by' section (write 'nothing' when nothing blocks it)"
    ]


def test_the_order_is_milestone_then_priority_then_number() -> None:
    tasks = [
        issue(9, milestone="0.2.0", labels=("ready", "priority:high")),
        issue(3, milestone="0.2.0", labels=("ready", "priority:low")),
        issue(5, milestone="0.10.0", labels=("ready", "priority:high")),
        issue(8, milestone="0.1.0", labels=("ready", "priority:low")),
        issue(4, milestone="0.2.0", labels=("ready", "priority:high")),
        issue(1, milestone=None, labels=("ready", "priority:high")),
    ]
    assert [t.number for t in sorted(tasks, key=backlog.order)] == [8, 4, 9, 3, 5, 1]


def test_the_next_issue_skips_a_claimed_one_and_falls_back_to_the_top_unready() -> None:
    claimed = issue(1, milestone="0.1.0", labels=("ready", "priority:high", "in-progress"))
    ready = issue(4)
    unready = issue(2, labels=("priority:normal",))
    for task in (claimed, ready, unready):
        task.reasons = backlog.assess(task, set(), set())
    assert backlog.next_issue([claimed, ready, unready]) == (ready, True)
    assert backlog.next_issue([claimed, unready]) == (unready, False)
    assert backlog.next_issue([claimed]) == (None, False)


def test_a_label_without_the_standard_is_not_ready() -> None:
    task = issue(labels=("ready", "priority:normal"), milestone=None)
    task.reasons = backlog.assess(task, set(), set())
    assert not task.ready


def test_the_owners_requests_are_not_work() -> None:
    raw = [
        {"number": 1, "title": "DEC-0044", "body": "", "labels": [{"name": "decision-request"}]},
        {"number": 2, "title": "NEED-0011", "body": "", "labels": [{"name": "needs-owner"}]},
        {"number": 3, "title": "task", "body": "", "labels": [], "milestone": {"title": "0.2.0"}},
    ]
    issues, every = backlog.load(raw)
    assert [i.number for i in issues] == [3] and every == {1, 2, 3}
    assert issues[0].milestone == "0.2.0"


def test_the_open_records_are_the_files_under_open() -> None:
    found = backlog.open_record_ids()
    names = [p.name for p in (ROOT / "docs" / "decisions" / "open").glob("*-*.md")]
    assert found == {name.rsplit("-", name.count("-") - 1)[0] for name in names}
