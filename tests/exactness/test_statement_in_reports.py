"""A report a process delivers carries the exactness statement of the checks behind its numbers
(UC-6.9 §1, §2; #224).

A step that composes a report names the statement by `{"$run": "exactness"}`. The run reads it
from the version it executes, rendered by the process component, and the report carries it as it
is: no step edits, shortens or rewrites it, and no model writes it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from components.run.test_engine import TENANT, Harness

from taktus.adapters.driven.memory import MemoryPersistence, MemoryRepository
from taktus.components.process.application.service.register_version import (
    parse_bundle,
    statement_of,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.levels import VersionStatements
from taktus.shared.v1 import Check, ExactnessClass, Method, Step

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = yaml.safe_load((ROOT / "examples" / "processes" / "six-times-seven.yaml").read_text())
RENDERED = statement_of(BUNDLE).render()


class Statements:
    async def rendered(self, tenant: str, process_version: str) -> str | None:
        return RENDERED if process_version == "p@1" else None


def steps() -> tuple[tuple[Step, dict[str, Any]], ...]:
    total = Step(
        id="total",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        checks=(Check.model_validate({"kind": "bounds", "minimum": 0}),),
    )
    report = Step(
        id="report",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=("total",),
    )
    return (
        (total, {"rule": "constant", "value": 42}),
        (
            report,
            {
                "rule": "template",
                "text": "The total is ${total}.\n\n${statement}",
                "values": {"total": {"$from": "total"}, "statement": {"$run": "exactness"}},
            },
        ),
    )


async def _report(harness: Harness) -> str:
    run = await harness.start()
    assert run.state is RunState.FINISHED, run
    checkpoint = run.step_run("report").checkpoint
    assert checkpoint is not None and checkpoint.result_digest is not None
    content = await harness.objects.get(checkpoint.result_digest)
    assert content is not None
    text = json.loads(content)
    assert isinstance(text, str)
    return text


async def test_a_report_carries_the_statement_of_the_process_that_produced_it_unchanged() -> None:
    harness = Harness(*steps())
    harness.engine._statements = Statements()
    report = await _report(harness)
    assert report.startswith("The total is 42.")
    assert report.endswith(RENDERED)
    for title in ("Which checks apply", "What they cover", "What they do not cover"):
        assert f"## {title}" in report
    assert "The residual risk" in report and "not yet measured" in report


async def test_a_report_without_a_statement_to_carry_fails_rather_than_go_without_it() -> None:
    harness = Harness(*steps())  # no statements wired
    run = await harness.start()
    assert run.step_run("report").state is StepState.FAILED
    assert "exactness" in (run.step_run("report").reason or "")


async def test_the_statement_a_run_reads_is_the_one_its_version_generates() -> None:
    persistence = MemoryPersistence()
    versions = MemoryRepository(persistence, ProcessVersion)
    version = parse_bundle(BUNDLE)
    async with persistence.transaction(TENANT):
        await versions.put(TENANT, version)
    statements = VersionStatements(persistence, versions)
    assert await statements.rendered(TENANT, version.ref) == RENDERED
    assert await statements.rendered(TENANT, "nothing@1") is None
