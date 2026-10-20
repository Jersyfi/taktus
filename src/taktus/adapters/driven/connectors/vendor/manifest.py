"""The manifest: what an operator declares about a vendor's MCP server (ADR-0117).

`Connector.json#/$defs/Manifest` is the shape. This module binds it, with the rules the schema
cannot say: an operation is named by its capability, every capability it names is declared,
no operation and no tool is listed twice. `tests/adapters/connectors/test_vendor_connector.py`
holds the binding to the contract's examples, valid and invalid.

A manifest is read once, when the connector starts. Its digest is the digest of its bytes as
read, so that the declaration names exactly the file the operator wrote.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from taktus.ports.connector import (
    CREDENTIAL_NAME_PATTERN,
    OPERATION_PATTERN,
    Demand,
    Effect,
    Idempotency,
)
from taktus.shared.v1 import Capability, Value

POINTER_PATTERN = r"^(/([^/~]|~[01])*)+$"
RECORD_KIND_PATTERN = r"^[a-z][a-z0-9_.-]*$"


class ManifestError(ValueError):
    """The manifest cannot be read, or does not hold."""


class ManifestRecord(Value):
    kind: str = Field(pattern=RECORD_KIND_PATTERN)
    id: str = Field(pattern=POINTER_PATTERN)
    url: str | None = Field(default=None, pattern=POINTER_PATTERN)


class ManifestOperation(Value):
    tool: str = Field(min_length=1, max_length=128)
    name: str = Field(pattern=OPERATION_PATTERN)
    capability: Capability
    effect: Effect
    idempotency: Literal[Idempotency.NATIVE, Idempotency.NONE] | None = None
    key_argument: str | None = Field(default=None, min_length=1)
    replayed: str | None = Field(default=None, pattern=POINTER_PATTERN)
    record: ManifestRecord | None = None
    demand: Demand | None = None
    summary: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _effect_decides_the_rest(self) -> ManifestOperation:
        if not self.name.startswith(self.capability + "."):
            raise ValueError(f"operation {self.name!r} is not named by its capability")
        if self.effect is Effect.READ:
            extra = [
                field
                for field in ("idempotency", "key_argument", "replayed", "record")
                if getattr(self, field) is not None
            ]
            if extra:
                raise ValueError(f"a read declares no {', '.join(extra)}")
            return self
        if self.idempotency is None or self.record is None:
            raise ValueError(
                f"{self.name}: an effect that leaves the system declares its idempotency and "
                "where the answer names its record"
            )
        native = self.idempotency is Idempotency.NATIVE
        if native and (self.key_argument is None or self.replayed is None):
            raise ValueError(
                f"{self.name}: native names the argument that takes the key and the answer's "
                "replayed flag"
            )
        if not native and (self.key_argument is not None or self.replayed is not None):
            raise ValueError(f"{self.name}: only native names a key argument and a replayed flag")
        return self


class Manifest(Value):
    contract: Literal["connector/v1"]
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    credential: str = Field(pattern=CREDENTIAL_NAME_PATTERN)
    operations: tuple[ManifestOperation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_each(self) -> Manifest:
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("a capability is declared twice")
        names = [op.name for op in self.operations]
        tools = [op.tool for op in self.operations]
        if len(set(names)) != len(names):
            raise ValueError("an operation is declared twice")
        if len(set(tools)) != len(tools):
            raise ValueError("a tool is declared twice")
        for op in self.operations:
            if op.capability not in self.capabilities:
                raise ValueError(f"operation {op.name!r} belongs to an undeclared capability")
        return self


def load(path: Path) -> tuple[Manifest, str]:
    """The manifest at `path` and the digest of its bytes. Raises `ManifestError`."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestError(f"{path}: cannot be read: {error.strerror}") from None
    try:
        manifest = Manifest.model_validate_json(raw)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "the manifest"
        raise ManifestError(f"{path}: {where}: {first['msg']}") from None
    return manifest, "sha256:" + hashlib.sha256(raw).hexdigest()
