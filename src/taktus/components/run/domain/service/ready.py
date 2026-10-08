"""The ready standard of a backlog task and the backlog's order (DEC-0051,
docs/process/README.md), written once.

A task is ready when its text carries three sections — what must be achieved, how it is
verified, where the boundary lies — filled, a component, a milestone, exactly one priority
label, the label `ready`, and a section "Blocked by" that names nothing still open: no open
`NEED-NNNN` or `DEC-NNNN` record and no open issue. Sections are found by their heading, as an
issue form renders them (`### Label`) or as a person writes them (`## 1. Label`).

Two readers apply it, and both import this module, so that the standard exists once:
`tools/backlog.py`, which a session runs by hand, and the built-in rules of the run component.
The rule `ready` (`rules.ready`) is what P-03 Implementation's admission evaluates (`exact`) and
what P-02 Refinement uses to find the sections an issue lacks. It adds two conditions the
backlog reads elsewhere: the issue is open and not a pull request, and it is not claimed — a
session that reads the backlog lists a claimed issue apart instead of refusing it.

The backlog's order is here too: earliest milestone, then priority, then issue number. The rule
`backlog` (`rules.backlog`), which P-01 Roadmap control evaluates, and `make backlog` both
group and order the backlog with `backlog()` below, so that a process and a session print the
same order for the same issues (issue #71).

Standard library only, and nothing of the run component: `tools/backlog.py` loads this file by
its path, without the project's environment.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

SECTIONS = ("What must be achieved", "How it is verified", "Where the boundary lies")
COMPONENT = "Component"
BLOCKED_BY = "Blocked by"
READY = "ready"
CLAIMED = "in-progress"
PRIORITIES = {"priority:high": 0, "priority:normal": 1, "priority:low": 2}
NOT_WORK = frozenset({"decision-request", "needs-owner", "report"})
"""Labels of issues that are not work: a question or a need for the owner, or the issue that
carries a process's reports."""
EMPTY = {"", "_no response_", "none", "-", "n/a"}
NOTHING = {"nothing", "none", "-", "_no response_", ""}

HEADING = re.compile(r"^#{2,3}\s+(?:\d+\.\s+)?(.+?)\s*$", re.MULTILINE)
RECORD = re.compile(r"\b((?:NEED|DEC)-\d{4})\b")
ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")
RECORD_NAME = re.compile(r"^((?:NEED|DEC)-\d{4})-.*\.md$")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def sections(body: str) -> dict[str, str]:
    """The body's sections by heading, each with the text up to the next heading."""
    found: dict[str, str] = {}
    marks = list(HEADING.finditer(body or ""))
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        found[mark.group(1).strip()] = body[mark.end() : end].strip()
    return found


def filled(text: str | None) -> bool:
    return (text or "").strip().lower() not in EMPTY


def missing_sections(body: str) -> list[str]:
    """The three sections of a use case that the body lacks or leaves empty, in their order."""
    found = sections(body)
    return [name for name in SECTIONS if not filled(found.get(name))]


def blockers(text: str) -> tuple[set[str], set[int]]:
    """The records and issues a "Blocked by" section names."""
    return set(RECORD.findall(text)), {int(n) for n in ISSUE.findall(text)}


def open_records(names: Iterable[str]) -> set[str]:
    """The identifiers of the records whose files are named — the file names of the directory
    that holds the open records, `docs/decisions/open/` in this repository."""
    return {m[1] for name in names if (m := RECORD_NAME.match(name))}


def reasons(
    *,
    number: int,
    body: str,
    labels: Iterable[str],
    milestone: str | None,
    open_record_ids: set[str],
    open_issues: set[int],
) -> list[str]:
    """Every reason the task is not ready, in a fixed order; empty when the standard holds."""
    labels = set(labels)
    found: list[str] = []
    if READY not in labels:
        found.append("not labelled ready")
    parts = sections(body)
    for name in SECTIONS:
        if not filled(parts.get(name)):
            found.append(f"section '{name}' is missing or empty")
    if not filled(parts.get(COMPONENT)):
        found.append("no component")
    if not milestone:
        found.append("no milestone")
    if sum(1 for label in labels if label in PRIORITIES) != 1:
        found.append("not exactly one priority label")
    blocked = parts.get(BLOCKED_BY)
    if blocked is None:
        found.append("no 'Blocked by' section (write 'nothing' when nothing blocks it)")
    else:
        records, issues = blockers(blocked)
        if not records and not issues and blocked.strip().lower() not in NOTHING:
            found.append("'Blocked by' names no NEED, DEC or issue, and is not 'nothing'")
        for record in sorted(records & open_record_ids):
            found.append(f"blocked by {record}, still open")
        for other in sorted((issues & open_issues) - {number}):
            found.append(f"blocked by #{other}, still open")
    return found


def admission(
    issue: Mapping[str, Any], open_record_ids: set[str], open_issues: set[int]
) -> list[str]:
    """Every reason a process may not take the issue up: the standard's reasons, and before
    them that it is closed, a pull request, or claimed. `issue` is a repository reading:
    `number`, `state`, `is_pull_request`, `body`, `labels` (names) and `milestone` (a title, or
    nothing)."""
    labels = {str(label) for label in issue.get("labels") or []}
    found: list[str] = []
    if issue.get("state") != "open":
        found.append(f"not open: {issue.get('state')}")
    if issue.get("is_pull_request"):
        found.append("a pull request, not an issue")
    if CLAIMED in labels:
        found.append(f"claimed: labelled {CLAIMED}")
    milestone = issue.get("milestone")
    return found + reasons(
        number=int(issue["number"]),
        body=str(issue.get("body") or ""),
        labels=labels,
        milestone=str(milestone) if milestone else None,
        open_record_ids=open_record_ids,
        open_issues=open_issues,
    )


def milestone_key(title: str | None) -> tuple[int, int, int]:
    """A milestone's place in the roadmap; an issue without one sorts last."""
    if title and (m := VERSION.search(title)):
        return (int(m[1]), int(m[2]), int(m[3]))
    return (9999, 0, 0)


def priority(labels: Iterable[str]) -> int:
    """The rank of the highest priority label; an issue without one sorts after `low`."""
    ranks = [PRIORITIES[label] for label in labels if label in PRIORITIES]
    return min(ranks) if ranks else len(PRIORITIES)


def order(number: int, labels: Iterable[str], milestone: str | None) -> tuple[Any, ...]:
    """The backlog's order: earliest milestone, then priority, then issue number."""
    return (milestone_key(milestone), priority(labels), number)


def backlog(
    issues: Iterable[Mapping[str, Any]], open_record_ids: set[str], open_issues: set[int]
) -> dict[str, list[dict[str, Any]]]:
    """The backlog as a session reads it, in its order, in three groups: `ready` — the label
    and the standard hold and nobody claimed it, in the order a session takes them;
    `claimed`; and `not_ready`, each with every reason. A pull request and an issue labelled
    as not work (`NOT_WORK`) are not part of it.

    `issues` are repository readings: `number`, `title`, `body`, `labels` as names,
    `milestone` as a title or nothing, and optionally `is_pull_request`. Each entry carries
    `number`, `title`, `milestone`, `priority` (the label's level, or nothing), `labels`,
    `reasons`, and `content` — the reasons that remain when nothing is counted as open, which
    is what the label `ready` claims (points 1 to 5 of the standard): a task whose only
    reasons are open blockers keeps its label rightly."""
    entries: list[dict[str, Any]] = []
    for issue in issues:
        labels = {str(label) for label in issue.get("labels") or []}
        if issue.get("is_pull_request") or labels & NOT_WORK:
            continue
        number = int(issue["number"])
        milestone = str(issue["milestone"]) if issue.get("milestone") else None
        body = str(issue.get("body") or "")
        named = sorted(
            (label for label in labels if label in PRIORITIES), key=PRIORITIES.__getitem__
        )
        found, content = (
            reasons(
                number=number,
                body=body,
                labels=labels,
                milestone=milestone,
                open_record_ids=records,
                open_issues=numbers,
            )
            for records, numbers in ((open_record_ids, open_issues), (set(), set()))
        )
        entries.append(
            {
                "number": number,
                "title": str(issue.get("title") or ""),
                "milestone": milestone,
                "priority": named[0].split(":", 1)[1] if named else None,
                "labels": sorted(labels),
                "reasons": found,
                "content": content,
            }
        )
    entries.sort(key=lambda e: order(e["number"], e["labels"], e["milestone"]))
    claimed = [e for e in entries if CLAIMED in e["labels"]]
    free = [e for e in entries if CLAIMED not in e["labels"]]
    return {
        "ready": [e for e in free if not e["reasons"]],
        "claimed": claimed,
        "not_ready": [e for e in free if e["reasons"]],
    }
