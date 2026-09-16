"""Locating and loading the contract schemas the suite validates against.

The schemas live under contracts/ in the repository and are copied into the wheel, so that the
suite works from a checkout and from an installed package alike. Every schema is registered under
the `$id` its path prescribes (ADR-0019); relative `$ref`s between the worker contract and the
shared kernel resolve through that registry.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError, best_match
from referencing import Registry
from referencing.jsonschema import DRAFT202012

NAMESPACE = "https://taktus.eu/contracts/"
WORKER = NAMESPACE + "worker/v1/Worker.json"

type Json = dict[str, Any]
type SchemaRegistry = Registry[bool | Mapping[str, Any]]


def contracts_root() -> Path:
    """The contracts directory: the repository's when running from a checkout, the packaged copy
    when running from an installed wheel."""
    checkout = Path(__file__).resolve().parents[3] / "contracts"
    if (checkout / "worker" / "v1" / "Worker.json").is_file():
        return checkout
    packaged = Path(str(files("taktus") / "contracts"))
    if (packaged / "worker" / "v1" / "Worker.json").is_file():
        return packaged
    raise FileNotFoundError("contracts/ not found next to the package nor inside it")


@cache
def registry() -> SchemaRegistry:
    root = contracts_root()
    reg: SchemaRegistry = Registry()
    for path in sorted(root.glob("*/v*/*.json")):
        with path.open(encoding="utf-8") as handle:
            schema = json.load(handle)
        uri = NAMESPACE + path.relative_to(root).as_posix()
        reg = reg.with_resource(uri=uri, resource=DRAFT202012.create_resource(schema))
    return reg


@cache
def validator(definition: str) -> Draft202012Validator:
    """A validator for one definition of Worker.json, for example "Capabilities"."""
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"{WORKER}#/$defs/{definition}",
        },
        registry=registry(),
        format_checker=FormatChecker(),
    )


def first_error(definition: str, instance: Any) -> str | None:
    """The most relevant validation error as one line, or None when the instance validates."""
    error = best_match(validator(definition).iter_errors(instance))
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
