"""Artifact.json: a result that is data, referenced by digest."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from taktus.shared.v1.value import Value

DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"

type Digest = Annotated[str, StringConstraints(pattern=DIGEST_PATTERN)]
"""A content hash with its algorithm as prefix; only sha256 in v1."""


class Artifact(Value):
    id: str = Field(min_length=1)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    digest: Digest
    media_type: str | None = Field(
        default=None, pattern=r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+(;.*)?$"
    )
    size_bytes: int | None = Field(default=None, ge=0)
    uri: str | None = Field(default=None, min_length=1)
    title: str | None = None
    created_at: datetime | None = None
