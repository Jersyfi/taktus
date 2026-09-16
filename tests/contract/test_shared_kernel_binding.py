"""The Python binding of the shared kernel and of the worker contract matches the schemas.

Drift between a schema and its Python type is the defect these tests prevent. Three readings of
each schema are held against the type: the shape (every property, exactly the required ones),
the enumerations and patterns, and the contract's own examples — every valid example parses and
writes back byte-for-byte, every must-fail example is refused.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

import taktus.ports.worker as worker
import taktus.shared.v1 as shared
from taktus.shared.v1 import method as method_module

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "contracts" / "shared" / "v1"
WORKER = ROOT / "contracts" / "worker" / "v1"
WORKER_SCHEMA = json.loads((WORKER / "Worker.json").read_text(encoding="utf-8"))


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schemas() -> list[Path]:
    return sorted(SHARED.glob("*.json"))


def binding_of(schema_path: Path) -> Any:
    """The Python type bound to a shared schema: the class or alias named after its title."""
    return getattr(shared, load(schema_path)["title"])


def fields_of(model: type[BaseModel]) -> dict[str, bool]:
    """Property name (alias applied) → required."""
    return {
        (field.alias or name): field.is_required() for name, field in model.model_fields.items()
    }


def properties_of(
    schema: dict[str, Any], defs: dict[str, Any], base: Path
) -> tuple[set[str], set[str]]:
    """The properties and required set, with `allOf` references to other object shapes
    merged in, as the schema's readers see them."""
    properties = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    for item in schema.get("allOf", []):
        ref = item.get("$ref")
        if ref is None:
            continue
        target, target_defs = resolve(ref, defs, base)
        more, more_required = properties_of(target, target_defs, base)
        properties |= more
        required |= more_required
    return properties, required


def resolve(ref: str, defs: dict[str, Any], base: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """A `$ref` inside the same document or a relative path from `base`: the target and the
    `$defs` its own references resolve against."""
    if ref.startswith("#/$defs/"):
        return dict(defs[ref.removeprefix("#/$defs/")]), defs
    path, _, fragment = ref.partition("#")
    document = load((base / path).resolve())
    target_defs = dict(document.get("$defs", {}))
    if fragment.startswith("/$defs/"):
        return dict(document["$defs"][fragment.removeprefix("/$defs/")]), target_defs
    return dict(document), target_defs


def nested_models(model: type[BaseModel]) -> dict[str, type[BaseModel]]:
    """Property → nested Value class, for properties whose type is one."""
    nested: dict[str, type[BaseModel]] = {}
    for name, field in model.model_fields.items():
        for candidate in _leaf_types(field.annotation):
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                nested[field.alias or name] = candidate
    return nested


def _leaf_types(annotation: Any) -> list[Any]:
    origin = get_origin(annotation)
    if origin is None:
        return [annotation]
    return [leaf for arg in get_args(annotation) for leaf in _leaf_types(arg)]


# --- shape -----------------------------------------------------------------------------------


@pytest.mark.parametrize("schema_path", schemas(), ids=lambda p: p.stem)
def test_every_shared_schema_has_a_binding_with_the_same_shape(schema_path: Path) -> None:
    schema = load(schema_path)
    binding = binding_of(schema_path)
    if schema["type"] == "object":
        assert isinstance(binding, type) and issubclass(binding, BaseModel)
        assert_same_shape(schema, binding, schema.get("$defs", {}), SHARED, where=schema["title"])
    elif schema["type"] == "string" and "enum" in schema:
        assert issubclass(binding, StrEnum)
        assert [m.value for m in binding] == schema["enum"]
    elif schema["type"] == "string":
        assert pattern_of(binding) == schema["pattern"]
    elif schema["type"] == "integer":
        assert list(get_args(binding.__value__)) == schema["enum"]
    else:
        pytest.fail(f"{schema_path.name}: unhandled schema type {schema['type']}")


def assert_same_shape(
    schema: dict[str, Any],
    model: type[BaseModel],
    defs: dict[str, Any],
    base: Path,
    *,
    where: str,
) -> None:
    properties, required = properties_of(schema, defs, base)
    fields = fields_of(model)
    assert set(fields) == properties, f"{where}: properties differ"
    assert {name for name, needed in fields.items() if needed} == required, f"{where}: required"
    for name, nested in nested_models(model).items():
        sub = schema["properties"][name]
        sub_defs = defs
        if "$ref" in sub:
            sub, sub_defs = resolve(sub["$ref"], defs, base)
        if sub.get("type") == "object":
            assert_same_shape(sub, nested, sub_defs, base, where=f"{where}.{name}")
    for name, sub in schema.get("properties", {}).items():
        if "enum" in sub and name in fields:
            assert enum_of(model, name) == sub["enum"], f"{where}.{name}: enum"


def pattern_of(binding: Any) -> str | None:
    """The pattern of a string alias, read from the TypeAdapter's JSON schema."""
    adapter: TypeAdapter[Any] = TypeAdapter(binding)
    return str(adapter.json_schema().get("pattern"))


def enum_of(model: type[BaseModel], name: str) -> list[Any]:
    field = next(f for n, f in model.model_fields.items() if (f.alias or n) == name)
    for leaf in _leaf_types(field.annotation):
        if isinstance(leaf, type) and issubclass(leaf, StrEnum):
            return [m.value for m in leaf]
    literal = TypeAdapter(field.annotation).json_schema()
    for branch in literal.get("anyOf", [literal]):
        if "enum" in branch:
            return list(branch["enum"])
    return []


def test_method_subsets_match_their_definitions() -> None:
    schema = load(SHARED / "Method.json")
    for name, definition in schema["$defs"].items():
        constant = snake(name).upper()
        assert getattr(method_module, constant) == frozenset(definition["enum"]), name


# --- examples ----------------------------------------------------------------------------------


def example_cases(root: Path) -> list[tuple[Path, bool]]:
    return [
        (path, kind == "valid")
        for concept in sorted(root.glob("*"))
        if concept.is_dir()
        for kind in ("valid", "invalid")
        for path in sorted((concept / kind).glob("*.json"))
    ]


def shared_binding_for(concept: str) -> Any:
    title = "".join(part.capitalize() for part in concept.split("-"))
    return getattr(shared, title)


@pytest.mark.parametrize(
    ("path", "valid"),
    example_cases(SHARED / "examples"),
    ids=lambda p: p.relative_to(SHARED / "examples").as_posix() if isinstance(p, Path) else "",
)
def test_shared_examples_through_the_binding(path: Path, valid: bool) -> None:
    binding = shared_binding_for(path.parent.parent.name)
    adapter: TypeAdapter[Any] = TypeAdapter(binding)
    data = load(path)
    if valid:
        instance = adapter.validate_python(data)
        written = instance.document() if isinstance(instance, BaseModel) else instance
        assert written == data, "a valid example writes back exactly as it reads"
    else:
        with pytest.raises(ValidationError):
            adapter.validate_python(data)


WORKER_DEFINITIONS = {
    "artifact-list": worker.ArtifactList,
    "assignment": worker.Assignment,
    "assignment-state": worker.AssignmentState,
    "capabilities": worker.Capabilities,
    "estimate": worker.Estimate,
    "estimate-request": worker.EstimateRequest,
    "health": worker.Health,
    "stop-request": worker.StopRequest,
}


@pytest.mark.parametrize(
    ("path", "valid"),
    [c for c in example_cases(WORKER / "examples") if c[0].parent.parent.name != "transcript"],
    ids=lambda p: p.relative_to(WORKER / "examples").as_posix() if isinstance(p, Path) else "",
)
def test_worker_examples_through_the_port_types(path: Path, valid: bool) -> None:
    concept = path.parent.parent.name
    adapter: TypeAdapter[Any] = (
        worker.EVENT if concept == "event" else TypeAdapter(WORKER_DEFINITIONS[concept])
    )
    data = load(path)
    if valid:
        instance = adapter.validate_python(data)
        assert instance.document() == data
    else:
        with pytest.raises(ValidationError):
            adapter.validate_python(data)


@pytest.mark.parametrize(
    "definition",
    sorted(
        name
        for name, body in WORKER_SCHEMA["$defs"].items()
        if body.get("type") == "object" and "oneOf" not in body and hasattr(worker, name)
    ),
)
def test_worker_definitions_have_the_same_shape(definition: str) -> None:
    body = WORKER_SCHEMA["$defs"][definition]
    assert_same_shape(
        body, getattr(worker, definition), WORKER_SCHEMA["$defs"], WORKER, where=definition
    )


def test_every_worker_object_definition_is_bound() -> None:
    unbound = [
        name
        for name, body in WORKER_SCHEMA["$defs"].items()
        if body.get("type") == "object" and "oneOf" not in body and not hasattr(worker, name)
    ]
    assert unbound == ["Transcript"], "Transcript is a fixture shape, not a wire object"
