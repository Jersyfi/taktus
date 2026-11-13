"""Method scaffolds in the catalogue: the shipped ones, the format of `scaffold.yaml`, and the rule
that names each artifact of a project (ADR-0307, UC-13.2; NTC-0279)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from taktus.adapters.driving.cli.bundle_command import scaffold_of, skill_on_disk, skills_below
from taktus.components.catalog.domain.model import InvalidSkill
from taktus.components.catalog.domain.model.scaffold import (
    ArtifactState,
    InvalidScaffold,
    Observed,
    ProjectCheck,
    Scaffold,
)
from taktus.components.catalog.domain.service.scaffolds import (
    examine,
    newest_change,
    parse_scaffold,
    to_create,
)

ROOT = Path(__file__).resolve().parents[3]
SHIPPED = ROOT / "scaffolds"
AT = datetime(2026, 6, 1, tzinfo=UTC)


def shipped(name: str) -> Scaffold:
    scaffold = scaffold_of(skill_on_disk(SHIPPED / "skills" / name))
    assert scaffold is not None
    return scaffold


def test_the_catalogue_holds_scaffolds_for_development_process_automation_and_analysis() -> None:
    found = {d.name: parsed for d, parsed in skills_below(SHIPPED)}
    assert set(found) == {
        "development-scaffold",
        "process-automation-scaffold",
        "analysis-scaffold",
    }
    works = {}
    for name, parsed in found.items():
        assert not isinstance(parsed, InvalidSkill), parsed
        scaffold = scaffold_of(parsed)
        assert scaffold is not None
        works[name] = scaffold.work
        # A scaffold is a skill in the open format, unchanged: Taktus added no field.
        assert set(parsed.fields) == set(), parsed.fields
    assert works == {
        "development-scaffold": "development",
        "process-automation-scaffold": "process-automation",
        "analysis-scaffold": "analysis",
    }
    development = {a.id for a in shipped("development-scaffold").artifacts}
    assert {"use-cases", "architecture-decisions", "test-strategy", "definition-of-done"} <= (
        development
    )


def test_a_scaffold_yaml_is_held_to_its_format_with_every_finding() -> None:
    with pytest.raises(InvalidScaffold) as wrong:
        parse_scaffold(
            "s",
            {
                "scaffold": 2,
                "artifacts": [
                    {"id": "a", "title": "A", "why": "w", "system": "repository", "template": "t"},
                    {
                        "id": "b",
                        "title": "B",
                        "why": "w",
                        "system": "knowledge",
                        "page": "B",
                        "template": "missing.md",
                    },
                ],
                "extra": 1,
            },
            {"t": "x"},
        )
    findings = " | ".join(wrong.value.findings)
    assert "knows no field extra" in findings
    assert "`scaffold` is the format's version" in findings
    assert "`work` names the kind of work" in findings
    assert "artifact a" in findings and "path and a shape" in findings
    assert "missing.md" in findings
    with pytest.raises(InvalidScaffold):
        parse_scaffold(
            "s",
            {
                "scaffold": 1,
                "work": "w",
                "artifacts": [
                    {
                        "id": "a",
                        "title": "A",
                        "why": "w",
                        "system": "repository",
                        "path": "../out",
                        "shape": "file",
                        "template": "t",
                    }
                ],
            },
            {"t": "x"},
        )


def test_a_skill_whose_scaffold_yaml_is_wrong_is_refused_as_the_skill(tmp_path: Path) -> None:
    directory = tmp_path / "skills" / "broken-scaffold"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: broken-scaffold\ndescription: A scaffold that is wrong.\n---\nBody\n",
        encoding="utf-8",
    )
    (directory / "scaffold.yaml").write_text("scaffold: 1\nwork: x\n", encoding="utf-8")
    ((found_dir, parsed),) = skills_below(tmp_path)
    assert found_dir == directory
    assert isinstance(parsed, InvalidSkill)
    assert any("`artifacts`" in f for f in parsed.findings)


def test_each_artifact_is_present_missing_unmaintained_or_unread_against_the_project() -> None:
    scaffold = shipped("development-scaffold")
    old = AT - timedelta(days=400)
    observed = {
        "use-cases": Observed(present=True, changed_at=AT - timedelta(days=3)),
        "architecture-decisions": Observed(present=False),
        "test-strategy": Observed(present=True, changed_at=AT - timedelta(days=180)),
        "definition-of-done": Observed(present=True, changed_at=old),
        "glossary": Observed(read=False, reason="no knowledge system is configured"),
    }
    findings = {f.artifact: f for f in examine(scaffold, observed, AT)}
    assert findings["use-cases"].state is ArtifactState.PRESENT
    assert findings["architecture-decisions"].state is ArtifactState.MISSING
    assert findings["test-strategy"].state is ArtifactState.PRESENT, "180 days is the window"
    assert findings["definition-of-done"].state is ArtifactState.UNMAINTAINED
    assert findings["definition-of-done"].stale_days == 400
    assert findings["glossary"].state is ArtifactState.UNREAD
    assert findings["glossary"].reason == "no knowledge system is configured"
    assert [f.artifact for f in examine(scaffold, observed, AT)] == [
        a.id for a in scaffold.artifacts
    ], "every artifact, in the scaffold's order"


def test_a_project_at_rest_does_not_turn_its_artifacts_stale() -> None:
    """Measured against the project's newest change, never the calendar (NTC-0279)."""
    scaffold = shipped("development-scaffold")
    long_ago = AT - timedelta(days=1000)
    observed = {a.id: Observed(present=True, changed_at=long_ago) for a in scaffold.artifacts}
    newest = newest_change(long_ago + timedelta(days=10), None)
    assert {f.state for f in examine(scaffold, observed, newest)} == {ArtifactState.PRESENT}
    assert examine(scaffold, {}, AT)[0].state is ArtifactState.UNREAD, "nothing read, not present"


def test_furnishing_creates_only_what_is_missing() -> None:
    scaffold = shipped("analysis-scaffold")
    observed = {a.id: Observed(present=True, changed_at=AT) for a in scaffold.artifacts}
    observed["method"] = Observed(present=False)
    observed["findings"] = Observed(present=True, changed_at=AT - timedelta(days=200))
    check = ProjectCheck(
        scaffold="analysis-scaffold@1",
        stage="production",
        newest=AT,
        findings=examine(scaffold, observed, AT),
    )
    assert [a.id for a in to_create(scaffold, check)] == ["method"]
    findings = next(a for a in scaffold.artifacts if a.id == "findings")
    assert findings.created_at == "analysis/findings/finding.md"
