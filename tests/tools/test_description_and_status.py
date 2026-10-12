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


DEPENDABOT_BODY = (
    "Bumps [pyjwt](https://example.org) from 2.14.0 to 2.15.0.\n\n"
    "<details><summary>Release notes</summary>…</details>\n"
)


def run_tool(module: object, *argv: str) -> int:
    return module.main(list(argv))  # type: ignore[attr-defined, no-any-return]


def test_a_dependency_bots_description_is_not_held_to_the_shape(tmp_path: Path) -> None:
    """NTC-0013: the shape is a session's and Taktus's; a dependency bot explains its own change.
    Everything else the tool checks still runs."""
    body = tmp_path / "body.md"
    body.write_text(DEPENDABOT_BODY, encoding="utf-8")
    assert run_tool(check_decisions, "--pr-body", str(body), "--author", "dependabot[bot]") == 0
    assert run_tool(check_decisions, "--pr-body", str(body), "--author", "Jersyfi") == 1, (
        "the same text from a person or from Taktus fails"
    )
    assert run_tool(check_decisions, "--pr-body", str(body)) == 1, "no author: held to the shape"


# The owner section is written from the register, not checked against a hand copy (DEC-0189
# rule 1, issue #314).

LIST = "| Record | What |\n|---|---|\n| NEED-0001 | a token |"
WITHOUT_SECTION = COMPLETE.replace("## Needed from the owner\n\nNothing.\n", "")


def test_the_list_is_appended_to_a_description_without_the_section() -> None:
    written = check_status.with_owner_section(WITHOUT_SECTION, LIST)
    assert written.endswith(f"## Needed from the owner\n\n{check_status.printable(LIST)}\n")
    assert description(written) == []
    report = check_status.Report()
    check_status.check_pull_request(written, LIST, report)
    assert report.failures == []


def test_a_stale_list_is_replaced_and_nothing_else_changes() -> None:
    stale = check_status.printable("Nothing is open.")
    body = COMPLETE.replace("Nothing.", f"{stale}\n\nGenerated with a tool.")
    written = check_status.with_owner_section(body, LIST)
    assert written == body.replace(stale, check_status.printable(LIST))


def test_a_list_of_an_earlier_marker_wording_is_replaced() -> None:
    earlier = (
        "<!-- generated by tools/check_status.py from elsewhere -->\nold\n<!-- end generated -->"
    )
    written = check_status.with_owner_section(COMPLETE.replace("Nothing.", earlier), LIST)
    assert "old" not in written
    assert check_status.printable(LIST) in written


def test_under_a_heading_without_a_list_the_persons_text_stays() -> None:
    written = check_status.with_owner_section(COMPLETE, LIST)
    assert f"## Needed from the owner\n\n{check_status.printable(LIST)}\n" in written
    assert written.rstrip().endswith("Nothing.")


def test_writing_twice_changes_nothing_the_second_time() -> None:
    once = check_status.with_owner_section(COMPLETE, LIST)
    assert check_status.with_owner_section(once, LIST) == once


def test_the_writer_leaves_a_dependency_bots_description_alone(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text(DEPENDABOT_BODY, encoding="utf-8")
    assert run_tool(check_status, "--write-pr-body", str(body), "--author", "dependabot[bot]") == 0
    assert body.read_text(encoding="utf-8") == DEPENDABOT_BODY
    assert run_tool(check_status, "--write-pr-body", str(body), "--author", "Jersyfi") == 0
    written = body.read_text(encoding="utf-8")
    assert written.startswith(DEPENDABOT_BODY.rstrip())
    assert check_status.BEGIN in written


def test_both_tools_name_the_same_dependency_bots() -> None:
    assert check_decisions.DEPENDENCY_BOTS == check_status.DEPENDENCY_BOTS
