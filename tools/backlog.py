# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Print the backlog in the order a session takes it (DEC-0051, docs/process/README.md).

Runs as `make backlog`. Standard library only; it reads the repository's issues through the `gh`
command line, which must be installed and signed in.

The backlog is the repository's open issues, without pull requests, without the issues of a
decision request or a needs request, which are the owner's and not work, and without an issue
labelled `report`, which carries a process's reports. For each issue:

- **claimed** when it carries the label `in-progress`: a session works on it; another skips it;
- **ready** when it carries the label `ready` and the ready standard holds: the three sections of
  a use case — what must be achieved, how it is verified, where the boundary lies — filled, a
  component, a milestone, one priority label, and nothing it names under "Blocked by" still open.
  A `NEED-NNNN` or `DEC-NNNN` is open while its file is under `docs/decisions/open/`; an issue
  `#N` while it is open;
- **not ready** otherwise, with every reason. An issue labelled `ready` that fails the standard is
  listed with the reasons too: the label is a claim, the standard is the check.

The standard is not written here: it is `src/taktus/components/run/domain/service/ready.py`,
which P-03 Implementation's admission evaluates too, loaded by its path (issue #70).

Order: earliest milestone, then priority (`priority:high`, `priority:normal`, `priority:low`), then
issue number. The grouping and the order are the same module's, `backlog()`, which P-01 Roadmap
control runs as its rule `backlog`, so that the process and this script print the same order for
the same issues (issue #71). `--next` prints only the issue a session takes next — the top
ready, unclaimed one — or, when none is ready, the top issue that is not, which the session makes
ready first, as P-02 would. `--answers` prints the owner's comments on the issues of open
requests, so that a session records every answer first (CLAUDE.md §9).

The last line is the duration.
"""

from __future__ import annotations

import argparse
import importlib.util
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

# The standard and the order are one module, shared with the rules that P-03's admission and
# P-01's ordering evaluate (issues #70, #71). It is loaded by its path, so that this script
# needs neither the project's environment nor a copy of either.
STANDARD = ROOT / "src" / "taktus" / "components" / "run" / "domain" / "service" / "ready.py"
_spec = importlib.util.spec_from_file_location("taktus_ready_standard", STANDARD)
if _spec is None or _spec.loader is None:
    raise SystemExit(f"backlog: the ready standard is not at {STANDARD}")
standard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(standard)

SECTIONS = standard.SECTIONS
CLAIMED = standard.CLAIMED
PRIORITIES = standard.PRIORITIES
NOT_WORK = standard.NOT_WORK
"""Labels of issues that are not work: the owner's to answer or provide, or a process's reports."""
sections = standard.sections
blockers = standard.blockers
milestone_key = standard.milestone_key
priority = standard.priority


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


def order(issue: Issue) -> tuple[Any, ...]:
    """The backlog's order, the standard's: earliest milestone, then priority, then number."""
    found: tuple[Any, ...] = standard.order(issue.number, issue.labels, issue.milestone)
    return found


def assess(issue: Issue, open_records: set[str], open_issues: set[int]) -> list[str]:
    """Every reason the issue is not ready; empty when the ready standard holds."""
    found: list[str] = standard.reasons(
        number=issue.number,
        body=issue.body,
        labels=issue.labels,
        milestone=issue.milestone,
        open_record_ids=open_records,
        open_issues=open_issues,
    )
    return found


def open_record_ids() -> set[str]:
    found: set[str] = standard.open_records(p.name for p in OPEN.glob("*.md"))
    return found


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


def readings(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The issues `gh` printed, in the shape the repository connector reads them: labels by
    name, the milestone by its title — the shape the standard's `backlog()` takes."""
    found = []
    for item in raw:
        milestone = item.get("milestone") or {}
        found.append(
            {
                "number": int(item["number"]),
                "title": str(item["title"]),
                "body": str(item.get("body") or ""),
                "labels": sorted(label["name"] for label in item.get("labels") or []),
                "milestone": milestone.get("title") if isinstance(milestone, dict) else None,
            }
        )
    return found


def groups(raw: list[dict[str, Any]], records: set[str]) -> dict[str, list[dict[str, Any]]]:
    """The backlog in its three groups and its order — ready, claimed, not ready — computed by
    the standard's `backlog()`, the function P-01 Roadmap control's rule `backlog` runs."""
    every = {int(item["number"]) for item in raw}
    found: dict[str, list[dict[str, Any]]] = standard.backlog(readings(raw), records, every)
    return found


def load(raw: list[dict[str, Any]]) -> tuple[list[Issue], set[int]]:
    """The backlog's issues, and the numbers of every open issue (a blocker may be any)."""
    every = {int(item["number"]) for item in raw}
    issues = []
    for item in readings(raw):
        if set(item["labels"]) & NOT_WORK:
            continue
        issues.append(
            Issue(
                number=item["number"],
                title=item["title"],
                body=item["body"],
                labels=set(item["labels"]),
                milestone=item["milestone"],
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
    raw = fetch()
    records = open_record_ids()
    if args.next:
        issues, every = load(raw)
        for issue in issues:
            issue.reasons = assess(issue, records, every)
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
    found = groups(raw, records)
    for heading, group in (
        ("ready, in the order a session takes them", "ready"),
        ("claimed", "claimed"),
        ("not ready", "not_ready"),
    ):
        print(heading)
        for entry in found[group]:
            milestone, level = entry["milestone"] or "-", entry["priority"] or "-"
            print(f"  #{entry['number']:<4} {milestone:<7} {level:<7} {entry['title']}")
            for reason in entry["reasons"] if group == "not_ready" else []:
                print(f"         - {reason}")
    print(f"{time.monotonic() - started:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
