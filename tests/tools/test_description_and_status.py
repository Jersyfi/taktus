"""A pull request description must say what, what was done, why and what to check; the status
file carries no line every pull request rewrites.

Both checks live in scripts under `tools/`; the tests call their functions directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above
import check_status  # noqa: E402

COMPLETE = """## What this is about

The problem.

## Decisions required

None

## What was done

The change.

## Why this way

The reason.

## What to check

The risk.

## Needed from the owner

Nothing.
"""


def description(body: str) -> list[str]:
    report = check_decisions.Report()
    check_decisions.check_description(body, report)
    return report.failures


def test_a_complete_description_passes() -> None:
    assert description(COMPLETE) == []


@pytest.mark.parametrize("section", check_decisions.DESCRIPTION)
def test_a_description_without_one_of_the_four_fails(section: str) -> None:
    body = COMPLETE.replace(f"## {section}\n", "## Something else\n")
    [failure] = description(body)
    assert f"no `## {section}`" in failure


def test_an_empty_section_fails_even_with_the_template_comment() -> None:
    body = COMPLETE.replace("The reason.", "<!-- The reason for this shape. -->")
    [failure] = description(body)
    assert "`## Why this way` is empty" in failure


def test_the_four_out_of_order_fail() -> None:
    body = COMPLETE.replace("## What was done\n\nThe change.\n\n", "").replace(
        "## What to check\n\nThe risk.\n",
        "## What to check\n\nThe risk.\n\n## What was done\n\nThe change.\n",
    )
    [failure] = description(body)
    assert "out of order" in failure


def test_a_code_span_is_not_a_placeholder() -> None:
    body = COMPLETE.replace("The change.", "Reads `TAKTUS_<KEY>_FILE`, as before.")
    assert description(body) == []


STATUS = "\n\n".join(f"## {name}\n\nText." for name in check_status.SECTIONS)


@pytest.mark.parametrize(
    "line", ["**As of:** 2026-09-29", "**Decided since the last version:** DEC-0001 (#1)."]
)
def test_a_status_line_every_pull_request_rewrites_fails(line: str) -> None:
    report = check_status.Report()
    check_status.check_shape(f"# Status\n\n{line}\n\n{STATUS}\n", report)
    [failure] = report.failures
    assert "DEC-0027" in failure


def test_a_status_without_such_a_line_passes() -> None:
    report = check_status.Report()
    check_status.check_shape(f"# Status\n\n{STATUS}\n", report)
    assert report.failures == []


@pytest.mark.parametrize(
    ("path", "counted"),
    [
        ("docs/roadmap.md", True),
        ("contracts/worker/v1/Worker.json", True),
        ("docs/adr/ADR-0005-step-atomicity.md", True),
        ("docs/decisions/DEC-0021-must-a-taktus-pull-request-update-the-status-report.md", True),
        ("docs/decisions/DEC-0020-a-branch-the-connector-writes-loses-the-file-mode.md", False),
        ("src/taktus/components/run/application/service/execute_run.py", False),
        ("tools/first_run.sh", False),
        ("workers/claudecode/worker.py", False),
    ],
)
def test_the_state_changes_with_a_milestone_a_need_a_decision_or_a_contract(
    path: str, counted: bool
) -> None:
    """DEC-0021, as the owner answered it: a defect's record and a change of code alone do not
    change the state of the project."""
    assert check_status.counts(path) is counted
