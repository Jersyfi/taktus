"""The blueprints' own reports that carry a number carry the exactness statement of the checks
behind it (UC-6.9 §1, ADR-0226, #224).

Each of these reports is a template step whose numbers come from the steps before it. It names
the statement by `{"$run": "exactness"}`, and its text places it, so the run hands it over as
the process component renders it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

REPORTS = {
    "blueprints/self-operation/processes/S-01-removal-test.yaml": "report",
    "blueprints/self-operation/processes/S-05-guides.yaml": "report",
    "blueprints/self-operation/processes/S-06-maturation.yaml": "report",
    "blueprints/software-operations/processes/B-7.05-review.yaml": "compose",
}


def _step(bundle: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(s for s in bundle["steps"] if s["id"] == step_id)


@pytest.mark.parametrize("path", sorted(REPORTS))
def test_a_blueprint_report_with_numbers_carries_the_statement(path: str) -> None:
    bundle = yaml.safe_load((ROOT / path).read_text())
    work = _step(bundle, REPORTS[path])["work"]
    assert work["rule"] == "template"
    names = [k for k, v in work["values"].items() if v == {"$run": "exactness"}]
    assert names, f"{path}: its report names no statement"
    assert all(f"${{{n}}}" in work["text"] for n in names), "the text places it"
