"""Use case: the instance installs an entry of a catalogue it verified, and records its origin
(ADR-0175 §4, UC-14.6).

This is the one writer of `CatalogueInstallation`. Its command names the index, the entry as
read, the keys the operator trusts, and what the entry is installed as: an adapter identifier
for an image, the proposal it became for a bundle. It verifies the entry again, whatever the
caller checked before, and refuses one that does not pass with every reason (`NotAdmitted`):
nothing unverified is ever recorded.

The evidence — the index's name, the entry as verified, its author and what it was installed
as — is stored as one document in the object store. One transaction then writes the record and
the ledger entry `catalogue.installed`: `outcome` is the tier the entry states, `adapter` the
identifier of an image, `refs.process_version` the version a bundle's proposal would register,
`refs.actor` the person, and `content_digest` the evidence's digest.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from taktus.components.catalog.domain.model.catalogue import (
    Admission,
    CatalogueInstallation,
    IndexEntry,
    TrustedKey,
    installation_id,
)
from taktus.components.catalog.domain.service import catalogue as rules
from taktus.components.catalog.ports.signatures import Signatures
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

CATALOGUE_INSTALLED = "catalogue.installed"


class NotAdmitted(Exception):
    """An entry the instance does not install, with every reason."""

    def __init__(self, entry: str, findings: Sequence[str]) -> None:
        self.findings = tuple(findings)
        super().__init__(f"{entry} is not installed: {'; '.join(self.findings)}")


@dataclass(frozen=True)
class InstallEntry:
    tenant: Tenant
    catalogue: str
    entry: IndexEntry
    trusted: Sequence[TrustedKey]
    actor: str
    """Who installs it, as the ledger names them."""
    bundle: bytes | None = None
    """For a bundle: the bytes of its file, read beside the index."""
    adapter: str | None = None
    """For an image: the adapter identifier it is bound to, of its family."""
    proposal: str | None = None
    """For a bundle: the proposal it became."""
    process_version: str | None = None
    """For a bundle: the version its proposal would register, as `process@version`."""


class CatalogueInstalls:
    def __init__(
        self,
        signatures: Signatures,
        installations: Repository[CatalogueInstallation],
        work: UnitOfWork,
        ledger: Ledger,
        objects: ObjectStore,
        clock: Clock,
    ) -> None:
        self._signatures = signatures
        self._installations = installations
        self._work = work
        self._ledger = ledger
        self._objects = objects
        self._clock = clock

    def admit(
        self, entry: IndexEntry, trusted: Sequence[TrustedKey], bundle: bytes | None = None
    ) -> Admission:
        """Whether the entry may be installed, with every reason it may not."""
        return rules.admit(entry, trusted, self._signatures.verify, bundle)

    async def install(self, command: InstallEntry) -> tuple[CatalogueInstallation, LedgerEntry]:
        entry = command.entry
        admission = self.admit(entry, command.trusted, command.bundle)
        findings = list(admission.findings)
        if entry.kind == "image":
            unfit = (
                "an image is installed as an adapter identifier"
                if command.adapter is None
                else rules.fits(entry, command.adapter)
            )
            if unfit is not None:
                findings.append(unfit)
        elif command.proposal is None or command.process_version is None:
            findings.append("a bundle is installed as the proposal it became")
        if findings or admission.author is None:
            raise NotAdmitted(entry.id, findings)
        adapter = command.adapter if entry.kind == "image" else None
        identifier = installation_id(entry, adapter)
        evidence = {
            "catalogue": command.catalogue,
            "entry": entry.document(),
            "author": admission.author,
            "installed_as": identifier,
            "proposal": command.proposal,
        }
        digest = await self._objects.put(
            json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        installation = CatalogueInstallation(
            id=identifier,
            tenant=command.tenant,
            catalogue=command.catalogue,
            entry=entry,
            author=admission.author,
            installed_at=self._clock.now(),
            actor=command.actor,
            evidence=digest,
            adapter=adapter,
            proposal=command.proposal if entry.kind == "bundle" else None,
            process_version=command.process_version if entry.kind == "bundle" else None,
        )
        async with self._work.transaction(command.tenant):
            await self._installations.put(command.tenant, installation)
            recorded = await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CATALOGUE_INSTALLED,
                    refs=LedgerRefs(
                        tenant=command.tenant,
                        actor=command.actor,
                        process_version=installation.process_version,
                    ),
                    adapter=adapter,
                    outcome=str(entry.tier),
                    content_digest=digest,
                ),
            )
        return installation, recorded

    async def installed(self, tenant: Tenant) -> list[CatalogueInstallation]:
        async with self._work.transaction(tenant):
            return list(await self._installations.list(tenant))

    async def installation(self, tenant: Tenant, identifier: str) -> CatalogueInstallation | None:
        async with self._work.transaction(tenant):
            return await self._installations.get(tenant, identifier)
