"""Two things a step's work is read for before it runs (ADR-0193): a workspace's ref given as a
reference is kept for the moment the step runs, and a pattern that is no regular expression is
refused when the version is read, never when the step runs."""

from __future__ import annotations

import pytest

from components.run.test_engine import rule, worker
from taktus.components.run.domain.model import UnsupportedWork, WorkerWork, parse_work
from taktus.components.run.domain.model.work import referenced_values


def test_a_workspace_ref_given_as_a_reference_is_resolved_when_the_step_runs() -> None:
    step, work = worker("repair", {"pull": 7}, after=("red",))
    given = {
        **work,
        "workspace": {
            "kind": "git",
            "location": "https://git.example/a.git",
            "ref": {"$from": "red", "$select": "first.head"},
        },
    }
    read = parse_work(step, given)
    assert isinstance(read, WorkerWork)
    assert read.workspace.ref is None and read.workspace.location == "https://git.example/a.git"
    assert read.workspace_ref == {"$from": "red", "$select": "first.head"}
    assert read.workspace_ref in referenced_values(read), "a dependency the version must name"

    plain = parse_work(step, {**work, "workspace": {"kind": "git", "ref": "main"}})
    assert isinstance(plain, WorkerWork)
    assert plain.workspace.ref == "main" and plain.workspace_ref is None


@pytest.mark.parametrize(
    "work",
    [
        {"rule": "filter", "items": [], "all": [{"field": "path", "matches": "a(?i)b"}]},
        {"rule": "check", "conditions": [{"value": "x", "not_matches": "("}]},
    ],
    ids=["filter", "check"],
)
def test_a_pattern_that_is_no_regular_expression_is_refused_when_the_work_is_read(
    work: dict[str, object],
) -> None:
    step, _ = rule("select", work)
    with pytest.raises(UnsupportedWork, match="not a regular expression"):
        parse_work(step, work)
