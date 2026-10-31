"""The catalogue: an index over signed images and bundles, and what an instance installed from
it (ADR-0175, UC-14.6).

The shapes are those of `contracts/catalogue/v1/Catalogue.json`. An entry states the tier of its
publisher, `reference` or `community`; *verified* is never stated, the instance derives it from
its own maturity records. An installation is the instance's record of one entry it verified and
installed: from which index, signed by which author, bound to which adapter identifier or made
into which proposal, by whom and when. It is written once by `CatalogueInstalls`, in the
transaction of the ledger entry `catalogue.installed`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

NAME = r"^[a-z0-9][a-z0-9-]*$"
DIGEST = r"^sha256:[0-9a-f]{64}$"
KEY = r"^[A-Za-z0-9_-]{43}$"

COMMUNITY_HIGHEST_LEVEL = 2
"""The highest autonomy level a community entry is installed at, and runs at until verified."""


class Tier(StrEnum):
    """The tier a publisher states. *verified* is no member: it is derived, never stated."""

    REFERENCE = "reference"
    COMMUNITY = "community"


type Standing = Literal["reference", "verified", "community"]
"""The tier an entry has in this instance: as stated, or *verified* where the instance's own
records earned it."""


class EntrySignature(Value):
    scheme: Literal["ed25519"]
    key: str = Field(pattern=KEY)
    value: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")


class IndexEntry(Value):
    """One artifact of an index: an adapter's image or a process bundle, by digest."""

    id: str = Field(pattern=NAME)
    kind: Literal["image", "bundle"]
    tier: Tier
    version: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    digest: str = Field(pattern=DIGEST)
    family: Literal["worker", "connector", "model"] | None = None
    contract: str | None = Field(default=None, pattern=r"^[a-z]+/v[0-9]+$")
    capabilities: tuple[str, ...] | None = None
    image: str | None = Field(default=None, min_length=1)
    process: str | None = Field(default=None, min_length=1)
    bundle: str | None = Field(default=None, min_length=1)
    signature: EntrySignature | None = None
    """Required by the contract. Read as optional here, so that an unsigned entry is listed
    with why it is refused instead of failing its whole index."""

    @model_validator(mode="after")
    def _shape(self) -> IndexEntry:
        image = (self.family, self.contract, self.capabilities, self.image)
        bundle = (self.process, self.bundle)
        if self.kind == "image" and (None in image or any(v is not None for v in bundle)):
            raise ValueError("an image entry names family, contract, capabilities and image only")
        if self.kind == "bundle" and (None in bundle or any(v is not None for v in image)):
            raise ValueError("a bundle entry names process and bundle only")
        if self.bundle is not None and not _below(self.bundle):
            raise ValueError("a bundle's file is a YAML file below the index's directory")
        return self

    @property
    def reference(self) -> str | None:
        """The image as a deployment pulls it, by digest; None for a bundle."""
        return None if self.image is None else f"{self.image}@{self.digest}"


def _below(path: str) -> bool:
    parts = path.split("/")
    return (
        not path.startswith("/")
        and ".." not in parts
        and "" not in parts
        and path.endswith((".yaml", ".yml"))
    )


class CatalogueIndex(Value):
    catalogue: str = Field(pattern=NAME)
    entries: tuple[IndexEntry, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> CatalogueIndex:
        ids = [e.id for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("an entry's id is unique within its index")
        return self


class TrustedKey(Value):
    key: str = Field(pattern=KEY)
    tier: Tier
    author: str = Field(min_length=1)


class Trust(Value):
    keys: tuple[TrustedKey, ...] = ()


class Admission(Value):
    """What the verification of one entry came to: admitted, with its author; or refused, with
    every reason."""

    admitted: bool
    findings: tuple[str, ...] = ()
    author: str | None = None


class CatalogueInstallation(Value):
    """One entry the instance verified and installed. The repository key is the adapter
    identifier for an image (`connector.mail`) and `process.<id>` for a bundle."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    catalogue: str = Field(pattern=NAME)
    entry: IndexEntry
    author: str = Field(min_length=1)
    installed_at: datetime
    actor: str = Field(min_length=1)
    evidence: str = Field(pattern=DIGEST)
    """The digest of the stored evidence: the index's name, the entry as verified, its author
    and what it was installed as."""
    adapter: str | None = Field(default=None, min_length=1)
    """For an image: the adapter identifier it was bound to."""
    proposal: str | None = Field(default=None, min_length=1)
    """For a bundle: the proposal it became."""
    process_version: str | None = Field(default=None, min_length=1)
    """For a bundle: the version the proposal would register, as `process@version`."""

    @property
    def tier(self) -> Tier:
        return self.entry.tier


def installation_id(entry: IndexEntry, adapter: str | None) -> str:
    """The key an installation is kept under."""
    if entry.kind == "bundle":
        return f"process.{entry.process}"
    if adapter is None:
        raise ValueError("an image is installed as an adapter identifier")
    return adapter
