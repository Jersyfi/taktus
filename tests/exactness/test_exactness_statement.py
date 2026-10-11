"""UC-4.13 and UC-6.9, first part (#91, ADR-0082): an exact step declares how it becomes exact,
and every process version carries its exactness statement.

The catalogue is the shared kernel's `Check`; its rows in the reader's words are the process
component's `CATALOGUE`. A bundle with an exact step and no check does not register, and the
finding names the catalogue. The statement is generated from the version, in four parts, never
says "guaranteed", and every sentence about a check is its row's, filled in with the check's
parameters and nothing else.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from taktus.adapters.driving.cli.main import app
from taktus.components.process.application.service.register_version import (
    parse_bundle,
    statement_of,
)
from taktus.components.process.domain.model import InvalidProcess
from taktus.components.process.domain.model.exactness import (
    CATALOGUE,
    NOT_YET_MEASURED,
    PARTS,
    ExactnessStatement,
    InvalidStatement,
)
from taktus.components.process.domain.service import exactness
from taktus.shared.v1 import Check, CheckKind, ExactnessClass, Step

ROOT = Path(__file__).resolve().parents[2]
BUNDLES = sorted((ROOT / "examples" / "processes").glob("*.yaml")) + sorted(
    (ROOT / "blueprints").glob("*/processes/*.yaml")
)
CHECK_EXAMPLES = ROOT / "contracts" / "shared" / "v1" / "examples" / "check" / "valid"
EXAMPLE = ROOT / "examples" / "processes" / "six-times-seven.yaml"


def bundle(*steps: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "p",
        "version": "1",
        "name": "P",
        "autonomy": {"level": 2, "reason": "r", "toward_next": "t"},
        "steps": list(steps),
    }


def rule_step(step_id: str = "s", exactness: str = "exact", **more: Any) -> dict[str, Any]:
    return {
        "id": step_id,
        "method": "rule",
        "reason": "r",
        "rejected": [],
        "exactness": exactness,
        **more,
    }


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def example_checks() -> list[Check]:
    return [
        Check.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(CHECK_EXAMPLES.glob("*.json"))
    ]


# --- the catalogue ---------------------------------------------------------------------------


def test_every_row_of_the_shared_kernel_has_its_words() -> None:
    assert set(CATALOGUE) == set(CheckKind)
    assert {check.kind for check in example_checks()} == set(CheckKind), (
        "every row has a valid example in the contract"
    )


def test_a_check_takes_exactly_the_parameters_of_its_row() -> None:
    with pytest.raises(ValidationError, match="needs source"):
        Check.model_validate({"kind": "reconciliation", "total": "the invoice total"})
    with pytest.raises(ValidationError, match="takes no share"):
        Check.model_validate({"kind": "approval", "threshold": 1, "role": "r", "share": 0.5})
    with pytest.raises(ValidationError, match="minimum, a maximum or a pattern"):
        Check.model_validate({"kind": "bounds"})
    with pytest.raises(ValidationError, match="lies above its maximum"):
        Check.model_validate({"kind": "bounds", "minimum": 2, "maximum": 1})
    with pytest.raises(ValidationError, match="no regular expression"):
        Check.model_validate({"kind": "bounds", "pattern": "("})
    with pytest.raises(ValidationError):
        Check.model_validate({"kind": "approval", "threshold": 1, "role": "A Named Person"})


@pytest.mark.parametrize("method", ["wait", "human"])
def test_a_step_that_produces_no_result_declares_no_check(method: str) -> None:
    with pytest.raises(ValidationError, match="declares no check"):
        Step.model_validate(
            {
                "id": "s",
                "method": method,
                "reason": "r",
                "rejected": [],
                "checks": [{"kind": "recomputation"}],
            }
        )


# --- the refusal -----------------------------------------------------------------------------


def test_an_exact_step_without_a_check_does_not_register_and_the_finding_names_the_catalogue() -> (
    None
):
    with pytest.raises(InvalidProcess) as refused:
        parse_bundle(bundle(rule_step()))
    (finding,) = refused.value.findings
    assert "step 's' is classed exact and declares no check" in finding
    for kind, row in CATALOGUE.items():
        assert f"{kind.value} ({row.name})" in finding
        assert row.covers in finding
        assert row.does_not_cover in finding
        assert row.needs in finding
    assert "goes to a person" in finding and "`sourced`" in finding


@pytest.mark.parametrize("cls", ["sourced", "tolerant", "free"])
def test_only_exact_must_declare_a_check(cls: str) -> None:
    version = parse_bundle(bundle(rule_step(exactness=cls)))
    assert version.steps[0].checks is None


def test_an_exact_step_with_a_check_registers() -> None:
    version = parse_bundle(bundle(rule_step(checks=[{"kind": "bounds", "minimum": 0}])))
    assert version.steps[0].exactness is ExactnessClass.EXACT


def test_a_recomputation_on_a_method_that_varies_is_refused() -> None:
    step = {
        "id": "s",
        "method": "llm",
        "reason": "r",
        "rejected": [],
        "exactness": "tolerant",
        "fallback": {"when": "always", "to": "human"},
        "checks": [{"kind": "recomputation"}],
    }
    with pytest.raises(InvalidProcess, match="does not give the same result again"):
        parse_bundle(bundle(step))


def test_every_exact_step_of_every_bundle_declares_a_check() -> None:
    for path in BUNDLES:
        version = parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8")))
        for step in version.steps:
            if step.exactness is ExactnessClass.EXACT:
                assert step.checks, f"{path.name}: {step.id}"


# --- the statement ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
def test_the_statement_of_every_bundle_renders_with_all_four_parts(path: Path) -> None:
    statement = statement_of(yaml.safe_load(path.read_text(encoding="utf-8")))
    parts = statement.parts()
    assert tuple(parts) == PARTS
    assert all(parts.values()), "no part is empty"
    text = statement.render()
    for title in PARTS:
        assert f"## {title}" in text
    assert "guarant" not in text.lower()
    assert parts["The residual risk"][-1] == NOT_YET_MEASURED


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
def test_every_result_producing_step_is_in_the_statement(path: Path) -> None:
    version = parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8")))
    statement = exactness.statement(version.ref, version.name, version.steps)
    for step in version.steps:
        named = f"`{step.id}` ({step.exactness.value})" if step.exactness else f"`{step.id}`"
        lines = [line for part in statement.parts().values() for line in part]
        if step.exactness is None:
            assert not any(line.startswith(f"`{step.id}`") for line in lines)
            continue
        for title in ("Which checks apply", "What they do not cover", "The residual risk"):
            assert any(line.startswith(named) for line in statement.parts()[title]), (
                f"{step.id} in {title!r}"
            )
        if step.checks:
            assert sum(
                line.startswith(named) for line in statement.parts()["What they cover"]
            ) == len(step.checks)


def test_a_changed_check_changes_the_statement() -> None:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    before = statement_of(document)
    changed = copy.deepcopy(document)
    for step in changed["steps"]:
        if step["id"] == "verify-answer":
            step["checks"] = [{"kind": "bounds", "subject": "the answer", "pattern": "^4[0-9]$"}]
    after = statement_of(changed)
    assert after != before
    assert "`^4[0-9]$`" in after.render() and "`^4[0-9]$`" not in before.render()


def test_a_statement_without_what_it_does_not_cover_does_not_render() -> None:
    with pytest.raises(InvalidStatement, match="'What they do not cover'"):
        ExactnessStatement(
            process_version="p@1",
            name="P",
            applies=("a",),
            covers=("b",),
            does_not_cover=(),
            residual=("d",),
        )


def test_a_bundle_whose_statement_would_say_guaranteed_is_refused() -> None:
    step = rule_step(checks=[{"kind": "recomputation", "subject": "the guaranteed total"}])
    with pytest.raises(InvalidProcess, match="never says guaranteed"):
        parse_bundle(bundle(step))


def test_a_step_without_a_check_is_named_unchecked_in_every_part() -> None:
    version = parse_bundle(bundle(rule_step(exactness="tolerant")))
    statement = exactness.statement(version.ref, version.name, version.steps)
    assert statement.parts()["Which checks apply"] == ("`s` (tolerant): no check declared.",)
    assert statement.parts()["What they cover"] == (
        "Nothing: no step of this process declares a check.",
    )
    assert "no wrong result of it is found" in statement.parts()["What they do not cover"][0]
    assert "every wrong result slips through" in statement.parts()["The residual risk"][0]


def test_a_process_without_a_result_still_says_what_is_not_covered() -> None:
    human = {"id": "h", "method": "human", "reason": "r", "rejected": []}
    version = parse_bundle(bundle(human))
    statement = exactness.statement(version.ref, version.name, version.steps)
    assert all(statement.parts().values())


@pytest.mark.parametrize("check", example_checks(), ids=lambda c: f"{c.kind}-{c.subject}")
def test_every_sentence_about_a_check_is_its_rows_filled_in_with_its_parameters(
    check: Check,
) -> None:
    """Change any one parameter of a check: every sentence about it changes in exactly that
    parameter's place, and nowhere else. So nothing but the row's fixed text and the check's own
    parameters is said about a check."""

    def sentences(c: Check) -> list[str]:
        step = Step.model_validate(rule_step(checks=[c.document()]))
        statement = exactness.statement("p@1", "P", [step])
        return [
            statement.parts()[title][0]
            for title in ("Which checks apply", "What they cover", "What they do not cover")
        ] + [statement.parts()["The residual risk"][0]]

    replacements = {
        "subject": "the zzz-subject",
        "total": "the zzz-total",
        "source": "zzz.source",
        "role": "zzz-role",
        "pattern": "^zzz$",
    }
    original = sentences(check)
    for name, value in replacements.items():
        current = getattr(check, name)
        if current is None:
            continue
        varied = check.model_copy(update={name: value})
        expected = [
            s.replace(current, value).replace(_capital(current), _capital(value)) for s in original
        ]
        assert expected == sentences(varied), name
    row = CATALOGUE[check.kind]
    assert original[0].startswith(f"`s` (exact): {row.name} — ")


def test_no_model_writes_the_statement() -> None:
    """The statement's modules reach no port, no adapter and no model: a rule writes it."""
    for module in (
        ROOT / "src" / "taktus" / "components" / "process" / "domain" / "service" / "exactness.py",
        ROOT / "src" / "taktus" / "components" / "process" / "domain" / "model" / "exactness.py",
    ):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        imported = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ] + [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        assert not [m for m in imported if m.startswith(("taktus.ports", "taktus.adapters"))]


# --- the command line ------------------------------------------------------------------------


def test_taktusctl_prints_the_statement_of_a_bundle() -> None:
    result = CliRunner().invoke(app, ["exactness", "--process", str(EXAMPLE)], obj=None)
    assert result.exit_code == 0, result.output
    for title in PARTS:
        assert f"## {title}" in result.output
    data = CliRunner().invoke(app, ["exactness", "--process", str(EXAMPLE), "--json"], obj=None)
    assert [p["title"] for p in json.loads(data.output)["parts"]] == list(PARTS)


def test_taktusctl_names_the_findings_of_a_bundle_it_would_refuse(tmp_path: Path) -> None:
    path = tmp_path / "bundle.yaml"
    path.write_text(yaml.safe_dump(bundle(rule_step())), encoding="utf-8")
    result = CliRunner().invoke(app, ["exactness", "--process", str(path)], obj=None)
    assert result.exit_code == 2
    assert "declares no check" in result.output
