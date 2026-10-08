"""The roadmap held against the backlog (issue #71), as P-01 Roadmap control's rule `roadmap`
evaluates it.

A roadmap states, per milestone, what the milestone is to contain: a heading `### \\`X.Y.Z\\``
followed by its items, separated by ` · `, up to the line that begins `**Complete when**`. An
item names the issues that carry it by number, `#N` (docs/process/README.md). What follows the
completion criterion — what was done so far, what is still missing — is prose and is not read.

Two disagreements are found, and each is reported once:

- **an item without an issue**: an item of a milestone that names no issue at all;
- **an issue the roadmap does not place**: an open issue that is work, in a milestone whose
  items do not name it — named under another milestone, or nowhere. An issue without a
  milestone that the roadmap names is the same disagreement seen from the other side.

An item that names an issue that is closed, or a pull request, carries that issue: the work is
done or delivered, and the item has its issue. Which issues are work is the backlog's rule
(`ready.NOT_WORK`). The verdict comes from the text and the readings alone: admissible for
`exact`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from taktus.components.run.domain.service import ready

MILESTONE = re.compile(r"^###\s+`(\d+\.\d+\.\d+)`.*$", re.MULTILINE)
END = re.compile(r"^(\*\*Complete when\*\*|#{1,3}\s|---\s*$)", re.MULTILINE)
SEPARATOR = " · "
ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")
SHORT = 90


def milestones(text: str) -> list[dict[str, Any]]:
    """The roadmap's milestones in their order, each with its items: the item's text with its
    whitespace collapsed, and the issue numbers it names."""
    found: list[dict[str, Any]] = []
    for mark in MILESTONE.finditer(text):
        rest = text[mark.end() :]
        end = END.search(rest)
        listing = " ".join((rest[: end.start()] if end else rest).split())
        items = [
            {"text": item.strip(), "issues": sorted({int(n) for n in ISSUE.findall(item)})}
            for item in listing.split(SEPARATOR.strip())
            if item.strip()
        ]
        found.append({"milestone": mark.group(1), "items": items})
    return found


def short(item: str) -> str:
    """An item as a report names it: without emphasis, at most SHORT characters."""
    plain = item.replace("**", "").replace("`", "")
    return plain if len(plain) <= SHORT else plain[: SHORT - 1].rstrip() + "…"


def reconcile(text: str, issues: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every place where the roadmap and the open issues disagree, items first in the
    roadmap's order, then issues by number."""
    found: list[dict[str, Any]] = []
    placed: dict[int, list[str]] = {}
    for listed in milestones(text):
        version = str(listed["milestone"])
        for item in listed["items"]:
            if not item["issues"]:
                found.append(
                    {
                        "kind": "item-without-issue",
                        "milestone": version,
                        "item": short(item["text"]),
                    }
                )
            for number in item["issues"]:
                where = placed.setdefault(number, [])
                if version not in where:
                    where.append(version)
    work = []
    for issue in issues:
        labels = {str(label) for label in issue.get("labels") or []}
        if issue.get("is_pull_request") or labels & ready.NOT_WORK:
            continue
        work.append(issue)
    for issue in sorted(work, key=lambda i: int(i["number"])):
        number = int(issue["number"])
        milestone = str(issue["milestone"]) if issue.get("milestone") else None
        where = placed.get(number, [])
        if (milestone is None and not where) or milestone in where:
            continue
        found.append(
            {
                "kind": "issue-not-placed",
                "number": number,
                "title": str(issue.get("title") or ""),
                "milestone": milestone,
                "placed": where,
            }
        )
    return found


def describe(disagreement: Mapping[str, Any]) -> str:
    """One disagreement as one line a person reads."""
    if disagreement["kind"] == "item-without-issue":
        return f"{disagreement['milestone']}: the item “{disagreement['item']}” names no issue"
    where = disagreement["placed"]
    placed = "places it in " + ", ".join(where) if where else "does not name it"
    if disagreement["milestone"] is None:
        return f"#{disagreement['number']} has no milestone; the roadmap {placed}"
    return (
        f"#{disagreement['number']} is in milestone {disagreement['milestone']}; "
        f"the roadmap {placed}"
    )
