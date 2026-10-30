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
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

# What the contract says of a capability, an operation, an effect and a demand, bound here and
# not imported: a connector imports nothing from the control plane (ADR-0158). The contract's
# schema is the one source; `tests/adapters/connectors/test_vendor_connector.py` holds this
# binding to its examples, valid and invalid.
CAPABILITY_PATTERN = r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*)+$"
OPERATION_PATTERN = r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$"
CREDENTIAL_NAME_PATTERN = r"^[A-Z][A-Z0-9_]*$"
POINTER_PATTERN = r"^(/([^/~]|~[01])*)+$"
RECORD_KIND_PATTERN = r"^[a-z][a-z0-9_.-]*$"


type Capability = Annotated[str, StringConstraints(pattern=CAPABILITY_PATTERN)]
type CurrencyAmounts = Annotated[
    dict[Annotated[str, StringConstraints(pattern=r"^[a-z]{3}$")], Annotated[float, Field(ge=0)]],
    Field(min_length=1),
]


class Value(BaseModel):
    """Frozen and closed, as the contract's `additionalProperties: false` makes it."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    def document(self) -> dict[str, Any]:
        """The instance as the JSON document the schema describes, absent fields left out."""
        result: dict[str, Any] = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        return result


class Effect(StrEnum):
    READ = "read"
    WRITE = "write"
    DELIVERY = "delivery"


class Idempotency(StrEnum):
    NATIVE = "native"
    MARKED = "marked"
    NONE = "none"


class Demand(Value):
    """The most one call of an operation consumes."""

    quota_units: float | None = Field(default=None, ge=0)
    compute_seconds: float | None = Field(default=None, ge=0)
    currency: CurrencyAmounts | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Demand:
        if self.quota_units is None and self.compute_seconds is None and self.currency is None:
            raise ValueError("a demand names at least one quantity")
        return self


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
