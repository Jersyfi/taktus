"""The contract-compatibility lane (#396, ADR-0171): a breaking change of a published contract
fails unless its major version rises; a compatible one passes; a frozen one does not move."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import contract_compat  # noqa: E402 — a script under tools/, found through the line above
import validate_contracts  # noqa: E402

STEP = "contracts/shared/v1/Step.json"
STEP_V2 = "contracts/shared/v2/Step.json"

BASE: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://taktus.eu/contracts/shared/v1/Step.json",
    "title": "Step",
    "type": "object",
    "required": ["id", "kind"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "kind": {"enum": ["rule", "llm"]},
        "note": {"type": "string", "maxLength": 200},
        "weight": {"type": "integer", "minimum": 0},
        "event": {"oneOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]},
    },
    "$defs": {"A": {"const": "a"}, "B": {"const": "b"}},
}


def _bytes(schema: dict[str, Any]) -> bytes:
    return json.dumps(schema, indent=2).encode()


def _changed(**edit: Any) -> dict[str, Any]:
    schema = json.loads(json.dumps(BASE))
    for pointer, value in edit.items():
        *path, last = pointer.split("__")
        node = schema
        for part in path:
            node = node[part]
        if value is None:
            del node[last]
        else:
            node[last] = value
    return schema


def _kinds(new: dict[str, Any]) -> set[str]:
    changes = contract_compat.classify({STEP: _bytes(BASE)}, {STEP: _bytes(new)})
    assert changes, "the change was not seen"
    return {change.kind for change in changes}


@pytest.mark.parametrize(
    "edit",
    [
        {"properties__note": None},  # a removed property
        {"required": ["id", "kind", "note"]},  # a new required property
        {"required": ["id"]},  # a property a reader relied on, no longer required
        {"properties__kind__enum": ["rule"]},  # a narrowed enum
        {"properties__id__type": "integer"},  # a changed type
        {"properties__weight__type": ["integer"], "properties__weight__minimum": 1},
        {"properties__note__maxLength": 100},  # a tightened upper bound
        {"properties__id__pattern": "^s_"},  # a new pattern
        {"$id": "https://taktus.eu/contracts/shared/v2/Step.json"},  # a changed $id
        {"$defs__B": None},  # a removed definition
        {"properties__event__oneOf": [{"$ref": "#/$defs/A"}]},  # a lost alternative
        {"properties__note__x-taktus": True},  # a keyword nobody classified
        {"properties__id__if": {"type": "string"}},  # a new condition
    ],
)
def test_a_breaking_change_is_classified_breaking(edit: dict[str, Any]) -> None:
    assert contract_compat.BREAKING in _kinds(_changed(**edit))


@pytest.mark.parametrize(
    "edit",
    [
        {"properties__extra": {"type": "string"}},  # an added optional property
        {"properties__kind__enum": ["rule", "llm", "ml"]},  # a widened enum
        {"properties__note__maxLength": 400},  # a loosened bound
        {"properties__weight__minimum": None},  # a removed bound
        {"properties__id__type": ["string", "null"]},  # a widened type
        {"description": "What a step is."},  # an annotation
        {"$defs__C": {"const": "c"}},  # an added definition
        {  # an alternative added, wherever it stands
            "properties__event__oneOf": [
                {"$ref": "#/$defs/A"},
                {"$ref": "#/$defs/C"},
                {"$ref": "#/$defs/B"},
            ]
        },
        {"additionalProperties": None},  # any further property admitted
    ],
)
def test_a_compatible_change_is_classified_compatible(edit: dict[str, Any]) -> None:
    assert _kinds(_changed(**edit)) == {contract_compat.COMPATIBLE}


def test_a_new_schema_is_compatible_and_a_removed_one_breaks_unless_its_successor_exists() -> None:
    added = contract_compat.classify({}, {STEP: _bytes(BASE)})
    assert [change.kind for change in added] == [contract_compat.COMPATIBLE]
    gone = contract_compat.classify({STEP: _bytes(BASE)}, {})
    assert [change.kind for change in gone] == [contract_compat.BREAKING]
    retired = contract_compat.classify({STEP: _bytes(BASE)}, {STEP_V2: _bytes(BASE)})
    assert {change.kind for change in retired} == {contract_compat.COMPATIBLE}


def test_a_file_that_is_not_a_schema_is_not_compared() -> None:
    readme = "contracts/shared/v1/README.md"
    example = "contracts/shared/v1/examples/step/valid/one.json"
    changes = contract_compat.classify({readme: b"a", example: b"{}"}, {readme: b"b"})
    assert changes == []


def test_an_openapi_document_gains_paths_compatibly_and_loses_them_breaking() -> None:
    path = "contracts/worker/v1/openapi.yaml"
    old = b"openapi: 3.1.0\npaths:\n  /v1/a:\n    get:\n      operationId: a\n"
    grown = old + b"  /v1/b:\n    get:\n      operationId: b\n"
    renamed = old.replace(b"operationId: a", b"operationId: z")
    assert {c.kind for c in contract_compat.classify({path: old}, {path: grown})} == {
        contract_compat.COMPATIBLE
    }
    assert {c.kind for c in contract_compat.classify({path: grown}, {path: old})} == {
        contract_compat.BREAKING
    }
    assert {c.kind for c in contract_compat.classify({path: old}, {path: renamed})} == {
        contract_compat.BREAKING
    }


def test_the_last_release_is_the_highest_release_tag_a_pre_release_is_none() -> None:
    tags = ["v0.2.0-rc.34", "v0.2.0", "v0.10.0", "v1.0.0-beta", "v0.9.1", "x1.0.0"]
    assert contract_compat.last_release(tags, lambda _tag: True) == "v0.10.0"
    assert contract_compat.last_release(tags, lambda tag: tag != "v0.10.0") == "v0.9.1"
    assert contract_compat.last_release(["v0.2.0-rc.34", "v1.0.0-beta"], lambda _t: True) is None


# --- the lane against a repository: both outcomes ------------------------------------------


def _git(root: Path, *args: str) -> None:
    command = ["git", *args]
    subprocess.run(command, cwd=root, check=True, capture_output=True)  # noqa: S603


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository whose release `v1.0.0` publishes `shared/v1/Step.json`."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / STEP).parent.mkdir(parents=True)
    (tmp_path / STEP).write_bytes(_bytes(BASE))
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "release")
    _git(tmp_path, "tag", "v1.0.0")
    _git(tmp_path, "tag", "v1.1.0-rc.1")
    monkeypatch.setattr(contract_compat, "ROOT", tmp_path)
    return tmp_path


def test_a_compatible_change_of_a_published_contract_passes(repository: Path) -> None:
    (repository / STEP).write_bytes(_bytes(_changed(properties__extra={"type": "string"})))
    assert contract_compat.main([]) == 0


def test_a_breaking_change_of_a_published_contract_fails(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / STEP).write_bytes(_bytes(_changed(properties__note=None)))
    assert contract_compat.main([]) == 1
    assert "property `note` removed" in capsys.readouterr().out


def test_the_same_break_passes_when_the_major_version_rises(repository: Path) -> None:
    successor = _changed(properties__note=None)
    successor["$id"] = "https://taktus.eu/contracts/shared/v2/Step.json"
    (repository / STEP_V2).parent.mkdir(parents=True)
    (repository / STEP_V2).write_bytes(_bytes(successor))
    assert contract_compat.main([]) == 0
    (repository / STEP).unlink()  # and v1 retired beside it
    assert contract_compat.main([]) == 0


def test_with_no_release_nothing_is_enforced_but_the_change_is_reported(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repository, "tag", "-d", "v1.0.0")
    (repository / STEP).write_bytes(_bytes(_changed(properties__note=None)))
    assert contract_compat.main(["--base", "main"]) == 0
    out = capsys.readouterr().out
    assert "no release yet" in out
    assert "property `note` removed" in out


def test_a_shallow_clone_is_refused_rather_than_read_as_unreleased(
    repository: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = tmp_path_factory.mktemp("shallow") / "clone"
    _git(clone.parent, "clone", "-q", "--depth", "1", repository.as_uri(), str(clone))
    monkeypatch.setattr(contract_compat, "ROOT", clone)
    assert contract_compat.main([]) == 2


# --- the freeze record, held by `make gate-contracts` --------------------------------------


def _freeze(contracts: Path, files: dict[str, str]) -> None:
    record = {"frozen": "2027-01-15", "decision": "DEC-9999", "files": files}
    (contracts / "FREEZE.json").write_text(json.dumps(record))


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def contracts(tmp_path: Path) -> Path:
    root = tmp_path / "contracts"
    (root / "shared/v1").mkdir(parents=True)
    (root / "shared/v1/Step.json").write_bytes(_bytes(BASE))
    return root


def test_without_a_freeze_record_nothing_is_frozen(contracts: Path) -> None:
    report = validate_contracts.Report()
    validate_contracts.check_freeze(report, contracts)
    assert report.failures == []
    assert report.passed == 0


def test_a_frozen_schema_unchanged_passes(contracts: Path) -> None:
    _freeze(contracts, {"shared/v1/Step.json": _digest(contracts / "shared/v1/Step.json")})
    report = validate_contracts.Report()
    validate_contracts.check_freeze(report, contracts)
    assert report.failures == []


def test_a_frozen_schema_changed_even_compatibly_fails(contracts: Path) -> None:
    step = contracts / "shared/v1/Step.json"
    _freeze(contracts, {"shared/v1/Step.json": _digest(step)})
    step.write_bytes(_bytes(_changed(description="only an annotation")))
    report = validate_contracts.Report()
    validate_contracts.check_freeze(report, contracts)
    assert any("changed since the freeze" in failure for failure in report.failures)


def test_a_schema_added_to_a_frozen_version_fails(contracts: Path) -> None:
    _freeze(contracts, {"shared/v1/Step.json": _digest(contracts / "shared/v1/Step.json")})
    (contracts / "shared/v1/Plan.json").write_text("{}")
    (contracts / "shared/v2").mkdir()
    (contracts / "shared/v2/Step.json").write_text("{}")  # a new major is not frozen
    report = validate_contracts.Report()
    validate_contracts.check_freeze(report, contracts)
    assert [failure.split(":")[0] for failure in report.failures] == ["frozen shared/v1/Plan.json"]


def test_a_freeze_record_without_its_decision_fails(contracts: Path) -> None:
    (contracts / "FREEZE.json").write_text(json.dumps({"files": {"shared/v1/Step.json": "x"}}))
    report = validate_contracts.Report()
    validate_contracts.check_freeze(report, contracts)
    assert report.failures
