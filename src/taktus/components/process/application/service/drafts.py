"""Use case: a BPMN model becomes a plan draft, and a filled draft a bundle (UC-4.23, ADR-0168).

`read_drafts` reads a model into drafts: never a version, nothing stored. `complete` turns a
draft the person filled in into a bundle document, and holds it to the checks registration
holds a bundle to on its own (`parse_bundle`). Every open question of the draft, and every
finding of registration, is a finding of `InvalidProcess`. The bundle is then proposed,
rehearsed and commissioned as any bundle is (ADR-0091); nothing here registers anything.

`export` writes a version as BPMN, a projection of it (ADR-0168 §5).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.process.domain.model.draft import Draft
from taktus.components.process.domain.service import interchange
from taktus.wire.bpmn import Unreadable

__all__ = ["Unreadable", "complete", "export", "read_drafts"]


def read_drafts(data: bytes) -> tuple[Draft, ...]:
    """One draft per process of the model that holds a task. Raises `Unreadable`."""
    return interchange.drafts_of(data)


def complete(document: Mapping[str, Any], version: str = "1") -> dict[str, Any]:
    """The filled draft as a bundle that would register; `InvalidProcess` with every finding."""
    try:
        draft = Draft.model_validate(document)
    except ValidationError as error:
        raise InvalidProcess(
            tuple(
                f"{'.'.join(str(p) for p in e['loc']) or 'draft'}: {e['msg']}"
                for e in error.errors()
            )
        ) from None
    try:
        bundle = interchange.bundle_of(draft, version)
    except ValueError as error:
        raise InvalidProcess(tuple(error.args[0])) from None
    parse_bundle(bundle)
    return bundle


def export(version: ProcessVersion) -> bytes:
    """The version as a BPMN document."""
    return interchange.export(version)
