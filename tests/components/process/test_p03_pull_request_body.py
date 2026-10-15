"""The description of a pull request P-03 opens carries each section CI checks once (issue #282).

Pull request #274 carried `## Decisions required` twice: the body's template brought it, and so
did the worker's summary, which is written in the shape the repository asks of a description.
Here the bundle's own template composes a body from such a summary and the section the
repository generates, and the repository's description checks read it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from taktus.components.run.domain.model import TemplateRule
from taktus.components.run.domain.service import rules

ROOT = Path(__file__).resolve().parents[3]
P03 = ROOT / "blueprints/dev-orchestration/processes/P-03-implementation.yaml"
PR_TEMPLATE = ROOT / ".github/pull_request_template.md"
sys.path.insert(0, str(ROOT / "tools"))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above
import check_status  # noqa: E402

GENERATED = "Needed from the owner"
"""The section the repository generates and puts last; the run appends it, not the worker."""


def headings() -> list[str]:
    """Every `## ` heading of the repository's pull request template, in order."""
    text = check_decisions.strip_comments(PR_TEMPLATE.read_text(encoding="utf-8"))
    return re.findall(r"^## (.+?)\s*$", text, re.MULTILINE)


def summary() -> str:
    """A worker's summary in the repository's shape: every section but the generated one."""
    parts = []
    for heading in headings():
        if heading == GENERATED:
            continue
        text = "None" if heading in ("Decisions required", "Behaviour changes") else "Said."
        parts.append(f"## {heading}\n\n{text}")
    return "\n\n".join(parts)


def composed(closing: str) -> str:
    """The body as the bundle's step `pull-request-body` composes it."""
    bundle = yaml.safe_load(P03.read_text(encoding="utf-8"))
    (step,) = [s for s in bundle["steps"] if s["id"] == "pull-request-body"]
    rule = TemplateRule.model_validate(step["work"])
    return rules.template(rule, {"issue": 282, "summary": summary(), "closing": closing})


def test_each_section_ci_checks_appears_once_and_the_generated_one_last() -> None:
    printed = check_status.generated(check_status.open_records())
    body = composed(f"## {GENERATED}\n\n{printed}")
    found = [name for name, _ in check_decisions.description_sections(body)]
    checked = [*check_decisions.DESCRIPTION, "Decisions required", "Behaviour changes", GENERATED]
    assert set(checked) <= set(headings()), "every section CI checks is in the template"
    for name in checked:
        assert found.count(name) == 1, (name, found)
    assert found == headings(), "the template's sections, in its order, each once"
    assert body.startswith("Closes #282.")

    report = check_decisions.Report()
    check_decisions.check_description(body, report)
    check_decisions.check_behaviour_changes(body, report)
    check_decisions.check_pull_request(body, None, [], report)
    check_status.check_pull_request(body, printed, report)
    assert report.failures == []
