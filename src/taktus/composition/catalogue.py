"""The catalogue as an instance reads it: index files in a directory, verified against the keys
its operator trusts, and installed (ADR-0175, UC-14.6).

- **Read on each request.** Each `*.json` in the directory `TAKTUS_CATALOGUE_DIRECTORY` names is
  one index. Nothing of it is kept; an index removed is gone at the next reading. An index that
  is not one by contract — one that states *verified*, say — is listed as refused, with why.
- **Verified before anything.** An entry is admitted only by the catalog component's rule
  (`CatalogueInstalls.admit`): signed, by a key `TAKTUS_CATALOGUE_KEYS` trusts for its tier,
  over the bytes of its bundle where it has one.
- **Installed as the instance itself would.** An image is bound to the adapter identifier the
  operator names, and its reference by digest is returned for the deployment to pull. A bundle
  is parsed as registration parses it, refused above level 2 when it is a community entry, and
  becomes a proposal through `Proposals.propose`; a person decides on it. The record and the
  ledger entry are the catalog component's (`CatalogueInstalls.install`).
- **Listed with its tier here.** An installed adapter is *verified* when the run's maturity port
  says so, which counts only what was taken after the installation (`composition/maturity.py`).

This is wiring: it reads files and joins the catalog and the process component, which only the
composition root may do (`composition/README.md`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from taktus.components.catalog.application.service import (
    CatalogueInstalls,
    InstallEntry,
    NotAdmitted,
)
from taktus.components.catalog.domain.model import (
    COMMUNITY_HIGHEST_LEVEL,
    CatalogueIndex,
    CatalogueInstallation,
    IndexEntry,
    Tier,
    Trust,
    TrustedKey,
)
from taktus.components.catalog.domain.service.catalogue import digest_of, payload
from taktus.components.process.application.service.proposals import Proposals, Propose
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.process.domain.service.bundle import next_version
from taktus.composition.maturity import CatalogMaturities
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry

SUFFIX = ".json"


@dataclass(frozen=True)
class Read:
    """One index file as read: the index, or why it is not one."""

    path: Path
    index: CatalogueIndex | None
    refused: str | None = None


@dataclass(frozen=True)
class Listed:
    """One entry as `taktusctl catalogue list` prints it."""

    catalogue: str
    entry: IndexEntry
    admitted: bool
    findings: tuple[str, ...]
    installed_as: str | None = None
    standing: str | None = None
    """The tier the entry has here: `reference`, `verified` or `community`."""
    missing: tuple[str, ...] = ()
    """For an installed adapter: what keeps it from *verified*."""


@dataclass(frozen=True)
class Installed:
    installation: CatalogueInstallation
    entry: LedgerEntry
    pull: str | None = None
    """For an image: the reference by digest the deployment pulls."""


def read_indexes(directory: Path | None) -> list[Read]:
    """Every index file in the directory, by name."""
    if directory is None or not directory.is_dir():
        return []
    found: list[Read] = []
    for path in sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == SUFFIX):
        try:
            index = CatalogueIndex.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as error:
            found.append(Read(path, None, refused=_reason(error)))
            continue
        found.append(Read(path, index))
    return found


def read_trust(path: Path | None) -> tuple[TrustedKey, ...]:
    """The keys the operator trusts; none where no file is named. A file that is named and
    cannot be read is an error: trusting nothing silently would hide a misconfiguration."""
    if path is None:
        return ()
    return Trust.model_validate_json(path.read_text(encoding="utf-8")).keys


def bundle_bytes(index_path: Path, entry: IndexEntry) -> bytes | None:
    """The bytes of a bundle entry's file, below the index's directory; None where there are
    none or the path leaves the directory."""
    if entry.bundle is None:
        return None
    root = index_path.parent.resolve()
    path = (root / entry.bundle).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path.read_bytes()


def _reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        return f"not an index by contract catalogue/v1: {where}: {first['msg']}"
    return f"unreadable: {error}"


class InstanceCatalogueIndex:
    def __init__(
        self,
        *,
        directory: Path | None,
        keys: Path | None,
        installs: CatalogueInstalls,
        maturities: CatalogMaturities,
        proposals: Proposals | None,
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
    ) -> None:
        self._directory = directory
        self._keys = keys
        self._installs = installs
        self._maturities = maturities
        self._proposals = proposals
        self._versions = versions
        self._work = work

    def indexes(self) -> list[Read]:
        return read_indexes(self._directory)

    async def listed(self, tenant: Tenant) -> tuple[list[Listed], list[Read]]:
        """Every entry of every index, with whether it is admitted and its tier here; and every
        index file that was refused."""
        trusted = read_trust(self._keys)
        installed = {i.id: i for i in await self._installs.installed(tenant)}
        by_entry = {(i.catalogue, i.entry.id, i.entry.digest): i for i in installed.values()}
        rows: list[Listed] = []
        refused: list[Read] = []
        for read in self.indexes():
            if read.index is None:
                refused.append(read)
                continue
            for entry in read.index.entries:
                admission = self._installs.admit(entry, trusted, bundle_bytes(read.path, entry))
                installation = by_entry.get((read.index.catalogue, entry.id, entry.digest))
                standing, missing = await self._standing(tenant, installation)
                rows.append(
                    Listed(
                        catalogue=read.index.catalogue,
                        entry=entry,
                        admitted=admission.admitted,
                        findings=admission.findings,
                        installed_as=None if installation is None else installation.id,
                        standing=standing,
                        missing=missing,
                    )
                )
        return rows, refused

    async def _standing(
        self, tenant: Tenant, installation: CatalogueInstallation | None
    ) -> tuple[str | None, tuple[str, ...]]:
        if installation is None:
            return None, ()
        if installation.adapter is None:
            return str(installation.tier), ()
        standing = await self._maturities.standing(tenant, installation.adapter)
        if standing.maturity == "verified":
            return "verified", ()
        return str(installation.tier), standing.missing

    def _find(self, catalogue: str, entry_id: str) -> tuple[Read, IndexEntry]:
        for read in self.indexes():
            if read.index is None or read.index.catalogue != catalogue:
                continue
            for entry in read.index.entries:
                if entry.id == entry_id:
                    return read, entry
        raise NotAdmitted(entry_id, [f"the catalogue {catalogue!r} holds no entry {entry_id!r}"])

    async def install(
        self,
        tenant: Tenant,
        catalogue: str,
        entry_id: str,
        *,
        actor: str,
        adapter: str | None = None,
    ) -> Installed:
        """Install one entry. NotAdmitted with every reason for one the instance refuses;
        InvalidProcess with every finding for a bundle registration or a proposal refuses."""
        read, entry = self._find(catalogue, entry_id)
        trusted = read_trust(self._keys)
        content = bundle_bytes(read.path, entry)
        admission = self._installs.admit(entry, trusted, content)
        if not admission.admitted:
            raise NotAdmitted(entry.id, admission.findings)
        if entry.kind == "image":
            installation, recorded = await self._installs.install(
                InstallEntry(
                    tenant=tenant,
                    catalogue=catalogue,
                    entry=entry,
                    trusted=trusted,
                    actor=actor,
                    adapter=adapter,
                )
            )
            return Installed(installation, recorded, pull=entry.reference)
        if adapter is not None:
            raise NotAdmitted(entry.id, ["a bundle is installed as a proposal, not as an adapter"])
        if self._proposals is None:
            raise NotAdmitted(entry.id, ["this instance makes no proposals"])
        document = _bundle_document(content or b"")
        version = parse_bundle(document)
        if version.process_id != entry.process:
            raise InvalidProcess(
                (f"the bundle is for the process {version.process_id!r}, not {entry.process!r}",)
            )
        if entry.tier is Tier.COMMUNITY and version.autonomy_level > COMMUNITY_HIGHEST_LEVEL:
            raise NotAdmitted(
                entry.id,
                [
                    f"it starts at autonomy level {version.autonomy_level}; a community bundle "
                    f"is installed at level {COMMUNITY_HIGHEST_LEVEL} or below"
                ],
            )
        async with self._work.transaction(tenant):
            registered = [
                v.version
                for v in await self._versions.list(tenant)
                if v.process_id == entry.process
            ]
        if registered:
            document["version"] = next_version(registered)
        proposal = await self._proposals.propose(
            Propose(
                tenant=tenant,
                process_id=version.process_id,
                bundle=document,
                by=actor,
                request=f"from the catalogue {catalogue}: {entry.id} {entry.version}",
            )
        )
        installation, recorded = await self._installs.install(
            InstallEntry(
                tenant=tenant,
                catalogue=catalogue,
                entry=entry,
                trusted=trusted,
                actor=actor,
                bundle=content,
                proposal=proposal.id,
                process_version=f"{proposal.process_id}@{proposal.version}",
            )
        )
        return Installed(installation, recorded)


def _bundle_document(content: bytes) -> dict[str, Any]:
    try:
        document = yaml.safe_load(content.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise InvalidProcess((f"the bundle cannot be read: {error}",)) from error
    if not isinstance(document, dict):
        raise InvalidProcess(("the bundle is not a mapping",))
    return document


def sign_index(path: Path, seed: bytes, signer: Any) -> list[str]:
    """Sign every entry of the index at `path` with the seed, after filling each bundle's digest
    from its file; write the index back. Returns the ids signed. `signer` is the signing
    adapter: `public(seed)` and `sign(seed, payload)`. The seed is never written or returned."""
    document = json.loads(path.read_text(encoding="utf-8"))
    entries = document.get("entries") or []
    key = signer.public(seed)
    signed: list[str] = []
    for raw in entries:
        raw.pop("signature", None)
        if raw.get("kind") == "bundle" and isinstance(raw.get("bundle"), str):
            bundle = (path.parent / raw["bundle"]).resolve()
            if not bundle.is_relative_to(path.parent.resolve()) or not bundle.is_file():
                raise ValueError(
                    f"{raw.get('id')}: its bundle {raw['bundle']} is not beside the index"
                )
            raw["digest"] = digest_of(bundle.read_bytes())
        entry = IndexEntry.model_validate(raw)
        raw["signature"] = {
            "scheme": "ed25519",
            "key": key,
            "value": signer.sign(seed, payload(entry)),
        }
        signed.append(entry.id)
    CatalogueIndex.model_validate(document)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return signed


class CatalogueAuthor:
    """`taktusctl catalogue key` and `sign`, over the instance's Ed25519 adapter."""

    def __init__(self, signer: Any) -> None:
        self._signer = signer

    def key(self, seed: bytes) -> str:
        return str(self._signer.public(seed))

    def sign(self, index: Path, seed: bytes) -> list[str]:
        return sign_index(index, seed, self._signer)
