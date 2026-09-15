# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema>=4.23,<5", "pyyaml>=6,<7", "rfc3339-validator>=0.1.4,<1"]
# ///
"""Validate the contracts under contracts/.

Runs as `make gate-contracts`. Needs no installed project: `uv run tools/validate_contracts.py`
creates the environment from the header above, so a third party can check a contract with
nothing but this file.

Checks, in order:

1. every schema (`contracts/<family>/<version>/<Concept>.json`) is a valid JSON Schema 2020-12
   document, carries the `$id` its path prescribes (ADR-0019), and every `$ref` in it resolves;
2. every `openapi.yaml` is OpenAPI 3.1 and every `$ref` in it resolves;
3. every example under `examples/<target>/valid/` validates against its target;
4. every example under `examples/<target>/invalid/` fails — by schema, or for transcripts by one of
   the stream rules below — and every conformance check W-01..W-12 has at least one such example;
5. every target has at least two valid examples.

The target of an examples directory is its name in kebab-case: for the shared kernel the schema
file (`exactness-class` -> `ExactnessClass.json`), for a contract the definition
(`assignment-state` -> `Worker.json#/$defs/AssignmentState`).

The stream rules are the executable reading of the conformance checks that cannot be expressed in
JSON Schema. The conformance suite (tests/conformance, next pull request) is the authority against a
live worker; these rules exist so that its fixtures are known good or known bad before it exists.
"""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError, best_match
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
NAMESPACE = "https://taktus.eu/contracts/"  # ADR-0019: the $id of a schema is its path under here
CHECKS = [f"W-{n:02d}" for n in range(1, 13)]
MIN_VALID_EXAMPLES = 2

type Json = dict[str, Any]
type SchemaRegistry = Registry[bool | Mapping[str, Any]]


@dataclass
class Report:
    passed: int = 0
    failures: list[str] = field(default_factory=list)

    def ok(self, what: str) -> None:
        self.passed += 1
        print(f"  ok   {what}")

    def fail(self, what: str, why: str) -> None:
        self.failures.append(f"{what}: {why}")
        print(f"  FAIL {what}\n       {why}")


# --- loading -------------------------------------------------------------------------------------


def file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def schema_files() -> list[Path]:
    return sorted(CONTRACTS.glob("*/v*/*.json"))


def expected_id(path: Path) -> str:
    return NAMESPACE + path.relative_to(CONTRACTS).as_posix()


def openapi_files() -> list[Path]:
    return sorted(CONTRACTS.glob("*/v*/openapi.yaml"))


def build_registry(schemas: dict[Path, Json]) -> SchemaRegistry:
    """Register every schema under the `$id` its path prescribes and under its file URI. Relative
    `$ref`s therefore resolve the same way from the namespace and from disk, which is the point of
    ADR-0019: the served URL of a schema is its repository path."""
    registry: SchemaRegistry = Registry()
    for path, schema in schemas.items():
        resource = DRAFT202012.create_resource(schema)
        registry = registry.with_resource(uri=expected_id(path), resource=resource)
        registry = registry.with_resource(uri=file_uri(path), resource=resource)
    return registry


def walk_refs(node: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{pointer}/{key}"
            if key == "$ref" and isinstance(value, str):
                yield here, value
            else:
                yield from walk_refs(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_refs(value, f"{pointer}/{index}")


# --- 1. schemas ----------------------------------------------------------------------------------


def check_schemas(schemas: dict[Path, Json], registry: SchemaRegistry, report: Report) -> None:
    print("schemas")
    for path, schema in schemas.items():
        rel = path.relative_to(ROOT)
        try:
            Draft202012Validator.check_schema(schema, format_checker=FormatChecker())
        except SchemaError as error:
            report.fail(str(rel), f"not a valid 2020-12 schema: {error.message}")
            continue
        if schema.get("$id") != expected_id(path):
            report.fail(str(rel), f"$id must be {expected_id(path)}, found {schema.get('$id')!r}")
            continue
        resolver = registry.resolver(base_uri=expected_id(path))
        broken = []
        for pointer, ref in walk_refs(schema):
            try:
                resolver.lookup(ref)
            except Unresolvable:
                broken.append(f"{pointer} -> {ref}")
        if broken:
            report.fail(str(rel), "unresolvable $ref: " + ", ".join(broken))
        else:
            report.ok(str(rel))


# --- 2. openapi ----------------------------------------------------------------------------------


def check_openapi(registry: SchemaRegistry, report: Report) -> None:
    print("openapi")
    for path in openapi_files():
        rel = path.relative_to(ROOT)
        document = load_yaml(path)
        version = str(document.get("openapi", ""))
        if not version.startswith("3.1"):
            report.fail(str(rel), f"expected OpenAPI 3.1, found {version!r}")
            continue
        if not document.get("paths"):
            report.fail(str(rel), "no paths")
            continue
        own = DRAFT202012.create_resource(document)
        resolver = registry.with_resource(uri=file_uri(path), resource=own).resolver(
            base_uri=file_uri(path)
        )
        broken = []
        for pointer, ref in walk_refs(document):
            try:
                resolver.lookup(ref)
            except Unresolvable:
                broken.append(f"{pointer} -> {ref}")
        if broken:
            report.fail(str(rel), "unresolvable $ref: " + ", ".join(broken))
            continue
        for route, item in document["paths"].items():
            for method, operation in item.items():
                if method in {"parameters", "summary", "description"}:
                    continue
                if not operation.get("responses"):
                    broken.append(f"{method.upper()} {route} has no responses")
        if broken:
            report.fail(str(rel), "; ".join(broken))
        else:
            report.ok(f"{rel} ({len(document['paths'])} paths)")


# --- 3./4./5. examples ---------------------------------------------------------------------------


def kebab_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))


def target_ref(examples_dir: Path, target: str, schemas: dict[Path, Json]) -> str | None:
    """Map an examples directory name to the URI of the schema it exercises."""
    version_dir = examples_dir.parent
    definition = kebab_to_pascal(target)
    single = version_dir / f"{definition}.json"
    if single in schemas:
        return expected_id(single)
    for path, schema in schemas.items():
        if path.parent != version_dir:
            continue
        if definition in schema.get("$defs", {}):
            return f"{expected_id(path)}#/$defs/{definition}"
    return None


def validator_for(ref: str, registry: SchemaRegistry) -> Draft202012Validator:
    return Draft202012Validator(
        {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": ref},
        registry=registry,
        format_checker=FormatChecker(),
    )


def first_error(validator: Draft202012Validator, instance: Any) -> str | None:
    error = best_match(validator.iter_errors(instance))
    if error is None:
        return None
    if error.validator == "oneOf" and error.context:
        # Events are discriminated by `type`; report the branch whose `type` matched, not the union.
        branches: dict[int, list[ValidationError]] = {}
        for sub in error.context:
            branches.setdefault(int(sub.relative_schema_path[0]), []).append(sub)
        matching = [
            errors
            for errors in branches.values()
            if not any(e.validator == "const" and list(e.relative_path) == ["type"] for e in errors)
        ]
        if len(matching) == 1:
            error = best_match(matching[0]) or error
    where = "/".join(str(p) for p in error.absolute_path) or "<root>"
    return f"{where}: {error.message}"


def check_examples(schemas: dict[Path, Json], registry: SchemaRegistry, report: Report) -> None:
    print("examples")
    covered: set[str] = set()
    for examples_dir in sorted(CONTRACTS.glob("*/v*/examples")):
        for target_dir in sorted(p for p in examples_dir.iterdir() if p.is_dir()):
            target = target_dir.name
            ref = target_ref(examples_dir, target, schemas)
            rel = target_dir.relative_to(ROOT)
            if ref is None:
                report.fail(str(rel), "no schema or definition matches this directory name")
                continue
            validator = validator_for(ref, registry)
            valid = sorted((target_dir / "valid").glob("*.json"))
            invalid = sorted((target_dir / "invalid").glob("*.json"))
            if len(valid) < MIN_VALID_EXAMPLES:
                report.fail(str(rel), f"{len(valid)} valid example(s), need {MIN_VALID_EXAMPLES}")
            for path in valid:
                instance = load_json(path)
                why = first_error(validator, instance)
                if why is None and target == "transcript":
                    why = first_stream_violation(instance)
                if why is None:
                    report.ok(str(path.relative_to(ROOT)))
                else:
                    report.fail(str(path.relative_to(ROOT)), why)
            for path in invalid:
                instance = load_json(path)
                why = first_error(validator, instance)
                if why is None and target == "transcript":
                    why = first_stream_violation(instance)
                name = path.relative_to(ROOT)
                if why is None:
                    report.fail(str(name), "must fail but validates")
                else:
                    report.ok(f"{name} fails as it must ({why})")
                    match = re.match(r"(W-\d{2})-", path.name)
                    if match:
                        covered.add(match.group(1))
    missing = [check for check in CHECKS if check not in covered]
    if missing:
        report.fail("conformance coverage", "no must-fail example for " + ", ".join(missing))
    else:
        report.ok(f"every check {CHECKS[0]}..{CHECKS[-1]} has a must-fail example")


# --- stream rules --------------------------------------------------------------------------------


def matches_pattern(tool: str, pattern: str) -> bool:
    """`*` stands for a whole segment or qualifier; a pattern without qualifier matches any."""
    if ":" in pattern:
        return fnmatch.fnmatchcase(tool, pattern)
    base = tool.split(":", 1)[0]
    return fnmatch.fnmatchcase(base, pattern)


def exceeds_limits(estimate: Json, limits: Json) -> str | None:
    for code, amount in estimate.get("currency", {}).items():
        ceiling = limits.get("currency", {}).get(code)
        if ceiling is not None and amount > ceiling:
            return f"currency {code} {amount} > {ceiling}"
    if "quota" in limits and estimate.get("quota_units", 0) > limits["quota"]["units"]:
        return f"quota {estimate['quota_units']} > {limits['quota']['units']}"
    compute = limits.get("compute")
    if compute and estimate.get("resource_class") == compute["resource_class"]:
        if estimate.get("compute_seconds", 0) > compute["seconds"]:
            return f"compute {estimate['compute_seconds']} > {compute['seconds']}"
    return None


def first_stream_violation(transcript: Json) -> str | None:
    """The executable reading of W-03..W-07, W-10 and W-11 for a fixture. Returns the first
    violated rule, or None."""
    assignment = transcript["assignment"]
    events = transcript["events"]
    frame = assignment["frame"]

    foreign = [e["seq"] for e in events if e["assignment_id"] != assignment["assignment_id"]]
    if foreign:
        return f"events {foreign} carry a foreign assignment_id"

    seqs = [e["seq"] for e in events]
    if seqs != list(range(1, len(events) + 1)):  # W-03
        return f"W-03 seq is not gapless from 1: {seqs}"

    last = events[-1]
    if last["type"] != "assignment.finished":
        return "the last event is not assignment.finished"
    if any(e["type"] == "assignment.finished" for e in events[:-1]):
        return "assignment.finished is not the last event"

    outcome = last["outcome"]
    excess = exceeds_limits(transcript["estimate"], assignment["limits"])
    if excess and (outcome != "rejected" or len(events) != 1):  # W-10
        return f"W-10 estimate exceeds limits ({excess}) but the stream did not reject first"
    if outcome == "rejected":
        return None if len(events) == 1 else "a rejected assignment emits exactly one event"

    started = [e["step_id"] for e in events if e["type"] == "step.started"]
    if len(started) > frame["max_steps"]:
        return f"{len(started)} steps started, frame allows {frame['max_steps']}"

    reported = {e["step_id"] for e in events if e["type"] == "consumption.reported"}
    unreported = [s for s in started if s not in reported]
    if unreported:  # W-04
        return f"W-04 no consumption.reported for step(s) {unreported}"

    boundaries = [e for e in events if e["type"] == "step.boundary"]
    if not boundaries:  # W-05
        return "W-05 no step.boundary in the stream"

    if outcome == "stopped":  # W-06
        before = events[-2] if len(events) > 1 else None
        if before is None or before["type"] != "step.boundary":
            return "W-06 stopped without a step.boundary directly before assignment.finished"
        if before["checkpoint_ref"] != last.get("checkpoint_ref"):
            return "W-06 checkpoint_ref of assignment.finished differs from the boundary's"

    allowed = set(frame["allowed_tools"])
    forbidden = frame.get("forbidden", [])
    for event in (e for e in events if e["type"] == "tool.called"):  # W-07
        tool = event["tool"]
        outside = tool not in allowed or any(matches_pattern(tool, p) for p in forbidden)
        if outside and not event.get("refused", False):
            return f"W-07 tool {tool} is outside the frame and was not refused (seq {event['seq']})"

    digests: dict[str, int] = {}
    for event in (e for e in events if e["type"] == "artifact.produced"):  # W-11
        if event["digest"] in digests:
            return (
                f"W-11 artifact digest {event['digest'][:19]}… emitted twice "
                f"(seq {digests[event['digest']]} and {event['seq']})"
            )
        digests[event["digest"]] = event["seq"]
    return None


# --- main ----------------------------------------------------------------------------------------


def main() -> int:
    schemas = {path: load_json(path) for path in schema_files()}
    if not schemas:
        print("no schemas found under contracts/")
        return 1
    registry = build_registry(schemas)
    report = Report()
    check_schemas(schemas, registry, report)
    check_openapi(registry, report)
    check_examples(schemas, registry, report)
    print()
    if report.failures:
        print(f"{report.passed} passed, {len(report.failures)} failed")
        return 1
    print(f"{report.passed} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
