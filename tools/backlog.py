# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Print the backlog in the order a session takes it (DEC-0051, docs/process/README.md).

Runs as `make backlog`. Standard library only; it reads the repository's issues through the `gh`
command line, which must be installed and signed in.

The backlog is the repository's open issues, without pull requests and without the issues of a
decision request or a needs request, which are the owner's and not work. For each issue:

- **claimed** when it carries the label `in-progress`: a session works on it; another skips it;
- **ready** when it carries the label `ready` and the ready standard holds: the three sections of
  a use case — what must be achieved, how it is verified, where the boundary lies — filled, a
  component, a milestone, one priority label, and nothing it names under "Blocked by" still open.
  A `NEED-NNNN` or `DEC-NNNN` is open while its file is under `docs/decisions/open/`; an issue
  `#N` while it is open;
- **not ready** otherwise, with every reason. An issue labelled `ready` that fails the standard is
  listed with the reasons too: the label is a claim, the standard is the check.

Order: earliest milestone, then priority (`priority:high`, `priority:normal`, `priority:low`), then
issue number. `--next` prints only the issue a session takes next — the top ready, unclaimed one —
or, when none is ready, the top issue that is not, which the session makes ready first, as P-02
would. `--answers` prints the owner's comments on the issues of open requests, so that a session
records every answer first (CLAUDE.md §9).

The last line is the duration.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPEN = ROOT / "docs" / "decisions" / "open"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"

SECTIONS = ("What must be achieved", "How it is verified", "Where the boundary lies")
COMPONENT = "Component"
BLOCKED_BY = "Blocked by"
READY = "ready"
CLAIMED = "in-progress"
PRIORITIES = {"priority:high": 0, "priority:normal": 1, "priority:low": 2}
NOT_WORK = {"decision-request", "needs-owner"}
"""Labels of issues that are the owner's to answer or provide, not a session's to work."""
EMPTY = {"", "_no response_", "none", "-", "n/a"}
NOTHING = {"nothing", "none", "-", "_no response_", ""}

HEADING = re.compile(r"^#{2,3}\s+(?:\d+\.\s+)?(.+?)\s*$", re.MULTILINE)
RECORD = re.compile(r"\b((?:NEED|DEC)-\d{4})\b")
ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass
class Issue:
    number: int
    title: str
    body: str
    labels: set[str]
    milestone: str | None
    reasons: list[str] = field(default_factory=list)

    @property
    def claimed(self) -> bool:
        return CLAIMED in self.labels

    @property
    def ready(self) -> bool:
        return not self.reasons


def sections(body: str) -> dict[str, str]:
    """The body's sections by heading, as an issue form renders them (`### Label`) or as a person
    writes them (`## 1. Label`)."""
    found: dict[str, str] = {}
    marks = list(HEADING.finditer(body or ""))
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        found[mark.group(1).strip()] = body[mark.end() : end].strip()
    return found


def milestone_key(title: str | None) -> tuple[int, int, int]:
    """A milestone's place in the roadmap; an issue without one sorts last."""
    if title and (m := VERSION.search(title)):
        return (int(m[1]), int(m[2]), int(m[3]))
    return (9999, 0, 0)


def priority(labels: set[str]) -> int:
    ranks = [PRIORITIES[label] for label in labels if label in PRIORITIES]
    return min(ranks) if ranks else len(PRIORITIES)


def order(issue: Issue) -> tuple[tuple[int, int, int], int, int]:
    return (milestone_key(issue.milestone), priority(issue.labels), issue.number)


def blockers(text: str) -> tuple[set[str], set[int]]:
    """The records and issues a "Blocked by" section names."""
    return set(RECORD.findall(text)), {int(n) for n in ISSUE.findall(text)}


def assess(issue: Issue, open_records: set[str], open_issues: set[int]) -> list[str]:
    """Every reason the issue is not ready; empty when the ready standard holds."""
    reasons: list[str] = []
    if READY not in issue.labels:
        reasons.append("not labelled ready")
    found = sections(issue.body)
    for name in SECTIONS:
        if found.get(name, "").strip().lower() in EMPTY:
            reasons.append(f"section '{name}' is missing or empty")
    if found.get(COMPONENT, "").strip().lower() in EMPTY:
        reasons.append("no component")
    if not issue.milestone:
        reasons.append("no milestone")
    if sum(1 for label in issue.labels if label in PRIORITIES) != 1:
        reasons.append("not exactly one priority label")
    blocked = found.get(BLOCKED_BY)
    if blocked is None:
        reasons.append("no 'Blocked by' section (write 'nothing' when nothing blocks it)")
    else:
        records, issues = blockers(blocked)
        if not records and not issues and blocked.strip().lower() not in NOTHING:
            reasons.append("'Blocked by' names no NEED, DEC or issue, and is not 'nothing'")
        for record in sorted(records & open_records):
            reasons.append(f"blocked by {record}, still open")
        for number in sorted((issues & open_issues) - {issue.number}):
            reasons.append(f"blocked by #{number}, still open")
    return reasons


def open_record_ids() -> set[str]:
    return {m[1] for p in OPEN.glob("*.md") if (m := re.match(r"((?:NEED|DEC)-\d{4})-", p.name))}


def gh(*args: str) -> str:
    # The arguments are this script's own; `gh` is found on the path, as `make` finds it.
    command = ["gh", *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout  # noqa: S603


def fetch() -> list[dict[str, Any]]:
    fields = "number,title,body,labels,milestone"
    raw: list[dict[str, Any]] = json.loads(
        gh("issue", "list", "--state", "open", "--limit", "1000", "--json", fields)
    )
    return raw


def load(raw: list[dict[str, Any]]) -> tuple[list[Issue], set[int]]:
    """The backlog's issues, and the numbers of every open issue (a blocker may be any)."""
    every = {int(item["number"]) for item in raw}
    issues = []
    for item in raw:
        labels = {label["name"] for label in item.get("labels") or []}
        if labels & NOT_WORK:
            continue
        milestone = item.get("milestone") or {}
        issues.append(
            Issue(
                number=int(item["number"]),
                title=str(item["title"]),
                body=str(item.get("body") or ""),
                labels=labels,
                milestone=milestone.get("title") if isinstance(milestone, dict) else None,
            )
        )
    return issues, every


def next_issue(issues: list[Issue]) -> tuple[Issue | None, bool]:
    """The issue a session takes next, and whether it is ready."""
    free = sorted((i for i in issues if not i.claimed), key=order)
    ready = [i for i in free if i.ready]
    if ready:
        return ready[0], True
    return (free[0], False) if free else (None, False)


def owner() -> str:
    for line in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        if line.startswith("*") and (m := re.search(r"@([\w-]+)", line)):
            return m[1]
    raise SystemExit("no owner in .github/CODEOWNERS")


def answers() -> int:
    """The owner's comments on the issues of open requests: each is an answer to record first."""
    who = owner()
    issue_line = re.compile(r"^\*\*Issue:\*\*.*?#(\d+)", re.MULTILINE)
    count = 0
    for path in sorted(OPEN.glob("*.md")):
        if not (m := issue_line.search(path.read_text(encoding="utf-8"))):
            continue
        comments = json.loads(gh("issue", "view", m[1], "--json", "comments"))["comments"]
        for comment in comments:
            if (comment.get("author") or {}).get("login") == who:
                count += 1
                print(f"{path.stem[:9]}  #{m[1]}  {comment['createdAt']}")
                print("  " + comment["body"].strip().replace("\n", "\n  "))
    if not count:
        print("no answer from the owner waits in an issue of an open request")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--next", action="store_true", help="print only the issue to take next")
    parser.add_argument("--answers", action="store_true", help="print the answers to record")
    args = parser.parse_args()
    if shutil.which("gh") is None:
        print("backlog: the `gh` command line is needed: https://cli.github.com", file=sys.stderr)
        return 2
    started = time.monotonic()
    if args.answers:
        answers()
        print(f"{time.monotonic() - started:.2f}s")
        return 0
    issues, every = load(fetch())
    records = open_record_ids()
    for issue in issues:
        issue.reasons = assess(issue, records, every)
    if args.next:
        chosen, ready = next_issue(issues)
        if chosen is None:
            print("the backlog is empty")
        elif ready:
            print(f"#{chosen.number}  {chosen.title}")
        else:
            print(f"none is ready; make #{chosen.number} ready first: {chosen.title}")
            for reason in chosen.reasons:
                print(f"  - {reason}")
        return 0
    ordered = sorted(issues, key=order)
    print("ready, in the order a session takes them")
    for issue in (i for i in ordered if i.ready and not i.claimed):
        print(f"  #{issue.number:<4} {issue.milestone or '-':<7} {_prio(issue):<7} {issue.title}")
    print("claimed")
    for issue in (i for i in ordered if i.claimed):
        print(f"  #{issue.number:<4} {issue.milestone or '-':<7} {_prio(issue):<7} {issue.title}")
    print("not ready")
    for issue in (i for i in ordered if not i.ready and not i.claimed):
        print(f"  #{issue.number:<4} {issue.milestone or '-':<7} {_prio(issue):<7} {issue.title}")
        for reason in issue.reasons:
            print(f"         - {reason}")
    print(f"{time.monotonic() - started:.2f}s")
    return 0


def _prio(issue: Issue) -> str:
    named = [label.split(":", 1)[1] for label in issue.labels if label in PRIORITIES]
    return named[0] if named else "-"


if __name__ == "__main__":
    sys.exit(main())
