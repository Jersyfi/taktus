"""Capability.json: what an adapter can do, named by function and never by product."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

CAPABILITY_PATTERN = r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*)+$"
CAPABILITY_PATTERN_PATTERN = r"^[a-z][a-z0-9]*(\.([a-z][a-z0-9_-]*|\*))+(:([a-z0-9_-]+|\*))?$"

type Capability = Annotated[str, StringConstraints(pattern=CAPABILITY_PATTERN)]
"""Lowercase dotted segments, at least two, so that a bare product name never validates."""

type CapabilityPattern = Annotated[str, StringConstraints(pattern=CAPABILITY_PATTERN_PATTERN)]
"""A capability narrowed by a qualifier or widened by `*`, where a set is denied or anchored."""
