"""The index of what Taktus read from knowledge sources (UC-5.5, ADR-0265 §4).

One entry per document of a source in a tenant: where the document is, which version of it was
last observed with which digest, when, and whether the source held it then. The source stays the
record. An entry never holds a document's text; it holds what is needed to find the document
again and to say whether a citation of it still holds.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import Field

from taktus.shared.v1 import Digest, Value


class Observed(Value):
    """An earlier version of a document, as an observation found it."""

    version: str
    digest: Digest
    at: datetime


class KnowledgeEntry(Value):
    """What the index knows of one document of one source."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    created_at: datetime
    """When a reading first found the document."""
    capability: str = Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*)+$")
    """The capability the document was read through: which source, never which product."""
    identifier: str = Field(min_length=1)
    """The document's identifier in its source."""
    title: str
    url: str = Field(min_length=1)
    """The link that opens the document in its source."""
    version: str
    """The version the source held at `observed_at`, or held last where it held none then."""
    digest: Digest
    observed_at: datetime
    held: bool = True
    """Whether the source showed the document at `observed_at`. False: it was removed, or
    hidden from the identity that read it — the source does not say which."""
    earlier: tuple[Observed, ...] = ()
    """The versions observed before `version`, oldest first."""


def entry_id(capability: str, document: str) -> str:
    """The entry of one document of one source: the same for every reading of it."""
    seed = f"{capability}\n{document}".encode()
    return "kne_" + hashlib.sha256(seed).hexdigest()[:24]
