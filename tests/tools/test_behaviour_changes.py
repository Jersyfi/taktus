"""A behaviour change inside an agreed scope (M2.4) is a line of the pull request description,
not a notice file (DEC-0189 rule 2, issue #315): the description check holds the line to its
three parts, a notice of that kind a branch adds fails, and `make status` counts the lines of
merged pull requests with the decisions that overrode one, so that the override rate stays
measurable (DEC-0042)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above
import check_status  # noqa: E402

BASE = """## What this is about

The problem.

## Decisions required

None

## Behaviour changes

{changes}

## What was done

The change.

## Why this way

The reason.

## What to check

The risk.

## Needed from the owner

Nothing.
"""
LINE = (
    "- **Old:** a failed step was retried at once **New:** it waits for the host's Retry-After "
    "**Reason:** the scope of #312 is to stop provoking the limit"
)


def checked(changes: str) -> list[str]:
    report = check_decisions.Report()
    check_decisions.check_behaviour_changes(BASE.format(changes=changes), report)
    return report.failures


def test_a_line_with_old_new_and_reason_passes() -> None:
    assert checked(LINE) == []
    assert checked(f"{LINE}\n{LINE.replace('at once', 'twice')}") == []
    parsed = check_decisions.behaviour_changes(BASE.format(changes=LINE))
    assert parsed is not None
    [change] = parsed[0]
    assert change.old == "a failed step was retried at once"
    assert change.reason.startswith("the scope of #312")


def test_none_and_an_absent_section_pass() -> None:
    assert checked("None") == []
    without = BASE.replace("## Behaviour changes\n\n{changes}\n\n", "")
    assert check_decisions.behaviour_changes(without) is None
    report = check_decisions.Report()
    check_decisions.check_behaviour_changes(without, report)
    assert report.failures == []


def test_the_template_comment_is_not_a_line() -> None:
    assert checked("None\n\n<!--\n- **Old:** <what it did> **New:** <x> **Reason:** <y>\n-->") == []


@pytest.mark.parametrize(
    ("line", "says"),
    [
        ("- the retry waits now", "not a behaviour change"),
        ("- **Old:** a **New:** b", "not a behaviour change"),
        ("- **Old:** **New:** b **Reason:** c", "says nothing after **Old:**"),
        ("- **Old:** a **New:** b **Reason:**", "says nothing after **Reason:**"),
        ("- **Old:** a **New:** a **Reason:** c", "the same"),
        ("- **Old:** a **New:** b **Reason:** TODO", "placeholder"),
    ],
)
def test_a_line_without_its_three_parts_fails(line: str, says: str) -> None:
    [failure] = checked(line)
    assert says in failure


def test_the_description_check_runs_it(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text(BASE.format(changes="- the retry waits now"), encoding="utf-8")
    assert check_decisions.main(["--pr-body", str(body), "--author", "Jersyfi"]) == 1
    body.write_text(BASE.format(changes=LINE), encoding="utf-8")
    assert check_decisions.main(["--pr-body", str(body), "--author", "Jersyfi"]) == 0


def test_the_pull_request_template_carries_the_section() -> None:
    template = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert check_decisions.behaviour_changes(template) == ([], [])


# --- a notice of the kind is no longer added ---------------------------------------------------


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)  # noqa: S603, S607


def test_a_behaviour_change_notice_a_branch_adds_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register = tmp_path / "docs" / "decisions"
    register.mkdir(parents=True)
    old = register / "NTC-0001-old.md"
    old.write_text("# NTC-0001 — old\n", encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
    monkeypatch.setattr(check_decisions, "ROOT", tmp_path)

    def notice(path: Path, kind: str) -> check_decisions.Document:
        number = path.name.split("-")[1]
        return check_decisions.Document(path, number, "x", {"Kind": kind}, {})

    added = register / "NTC-0002-new.md"
    other = register / "NTC-0003-other.md"
    report = check_decisions.Report()
    check_decisions.check_no_behaviour_notice(
        report,
        [
            notice(old, "behaviour-change"),
            notice(added, "behaviour-change"),
            notice(other, "unlisted"),
        ],
        "main",
    )
    [failure] = report.failures
    assert failure.startswith("docs/decisions/NTC-0002-new.md")
    assert "## Behaviour changes" in failure


# --- the override of a behaviour change --------------------------------------------------------


def record(**header: str) -> list[str]:
    fields = {"Category": "NON-BLOCKING", "Raised in": "#1", **header}
    doc = check_decisions.Document(
        ROOT / "docs" / "decisions" / "DEC-0999-x.md", "0999", "x", fields, {}
    )
    problems: list[str] = []
    check_decisions.check_record(doc, problems)
    return [p for p in problems if "Overrides" in p]


def test_an_override_names_the_pull_request() -> None:
    assert record(Overrides="#401, its second line") == []
    [problem] = record(Overrides="the retry change")
    assert "#NNN" in problem


# --- make status counts them ---------------------------------------------------------------------


def test_make_status_counts_the_lines_and_the_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "DEC-0001-x.md").write_text(
        "# DEC-0001 — x\n\n**Category:** NON-BLOCKING\n**Overrides:** #401\n", encoding="utf-8"
    )
    monkeypatch.setattr(check_status, "REGISTER", tmp_path)
    merged = [
        BASE.format(changes=f"{LINE}\n{LINE}"),
        BASE.format(changes="None"),
        BASE.format(changes="- not a line"),
        "a description from before the section existed",
    ]
    line = check_status.acceptance(merged)
    assert "of 2 behaviour change(s) in merged pull requests, 1 overridden by a decision" in line
    offline = check_status.acceptance(None)
    assert "behaviour changes in merged pull requests not counted" in offline
    assert "(1 overridden by a decision)" in offline


def test_the_descriptions_are_read_from_the_file_a_workflow_fetched(tmp_path: Path) -> None:
    fetched = tmp_path / "merged.json"
    fetched.write_text(json.dumps([{"number": 7, "body": "text"}]), encoding="utf-8")
    assert check_status.merged_descriptions(fetched) == ["text"]
    assert check_status.merged_descriptions(tmp_path / "absent.json") is None
    fetched.write_text("not json", encoding="utf-8")
    assert check_status.merged_descriptions(fetched) is None


def test_the_host_unreachable_is_not_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(*_: object, **__: object) -> None:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(check_status.subprocess, "run", unreachable)
    assert check_status.merged_descriptions(None) is None


@pytest.mark.parametrize(
    "changes",
    [
        LINE,
        f"{LINE}\n{LINE}",
        "None",
        "- the retry waits now",
        "- **Old:** a **New:** a **Reason:** c",
        "- **Old:** a **New:** b **Reason:** TODO",
        "- **Old:** **New:** b **Reason:** c",
        f"<!--\n{LINE}\n-->",
        f"{LINE}\n- not a line",
    ],
)
def test_status_counts_what_the_description_check_accepts(changes: str) -> None:
    """`check_status.py` runs alone in P-03's workspace and so repeats the line's shape; the
    two tools agree on every line."""
    body = BASE.format(changes=changes)
    parsed = check_decisions.behaviour_changes(body)
    accepted = len(parsed[0]) if parsed is not None else 0
    assert check_status.behaviour_lines(body) == accepted


def test_status_runs_alone_and_prints_offline(tmp_path: Path) -> None:
    """P-03's worker runs `python3 tools/check_status.py --print` in a tree that holds this file
    alone; it imports nothing of the repository's and asks no host."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "check_status.py").write_bytes(
        (ROOT / "tools" / "check_status.py").read_bytes()
    )
    printed = subprocess.run(
        [sys.executable, "tools/check_status.py", "--print"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "/nonexistent"},
    ).stdout
    assert "behaviour changes in merged pull requests not counted" in printed
