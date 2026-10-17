"""`tools/describe.py`, P-03's command after the work: it prints the section the repository
generates only for a summary that, with that section, passes the description check, and names
the check's findings otherwise (#471, ADR-0101). Run on this repository's tree, as the worker
runs it on the branch's."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above
import describe  # noqa: E402

SUMMARY = """## What this is about

A greeting.

## Decisions required

None

## What was done

Wrote hello.txt.

## Why this way

The issue asks for it.

## What to check

hello.txt says hello.
"""


def described(summary: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — the repository's own tool, fixed arguments
        [sys.executable, str(TOOLS / "describe.py")],
        input=summary,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def generated() -> str:
    return subprocess.run(  # noqa: S603 — the repository's own tool, fixed arguments
        [sys.executable, str(TOOLS / "check_status.py"), "--print"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_a_summary_that_passes_gets_the_generated_section_byte_for_byte() -> None:
    done = described(SUMMARY)
    assert done.returncode == 0, done.stderr
    assert done.stdout == generated()


def test_a_summary_with_a_placeholder_prints_nothing_and_names_the_check() -> None:
    """What #470 carried: a reference quoted with an ellipsis, read as a placeholder."""
    done = described(SUMMARY.replace("hello.txt says hello.", "hello.txt (ADR 0034, …"))
    assert done.returncode == 1
    assert done.stdout == ""
    last = done.stderr.strip().splitlines()[-1]
    assert last == (
        "description: `## What to check` keeps a placeholder: '…' — "
        "`tools/check_decisions.py --pr-body` fails the description"
    )


def test_a_summary_without_a_section_of_the_description_fails() -> None:
    done = described(SUMMARY.replace("## Why this way", "## Why"))
    assert done.returncode == 1
    assert "no `## Why this way`" in done.stderr.strip().splitlines()[-1]


def test_the_description_checked_is_the_summary_and_the_section_under_its_heading() -> None:
    body = describe.compose(SUMMARY, "Nothing is open.\n")
    assert body == SUMMARY.strip() + "\n\n## Needed from the owner\n\nNothing is open.\n"
    report = check_decisions.Report()
    check_decisions.check_description(body, report)
    assert report.failures == []


def test_description_only_runs_the_checks_that_read_the_description(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text(describe.compose(SUMMARY, generated()), encoding="utf-8")
    checked = subprocess.run(  # noqa: S603 — the repository's own tool, fixed arguments
        [sys.executable, str(TOOLS / "check_decisions.py"), "--pr-body", str(body),
         "--description-only"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert checked.returncode == 0, checked.stdout
    groups = [line for line in checked.stdout.splitlines() if line and not line.startswith(" ")]
    assert groups[:3] == ["description", "pull request", "behaviour changes"], groups
