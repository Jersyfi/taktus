"""A tenant's export, and its import into another instance, proven by its chains (ADR-0221).

An export is one JSON document: the tenant's registry entry, every row of every store the
archive holds — processes and their versions, runs and their steps, the ledger, the provenance
records, the decisions, the identities, the traces, everything with the tenant's name on it —
and the bytes of every object those rows name by digest, the artifacts and stored results among
them. It also carries what the chains looked like when it was taken: how many entries the
ledger held, the hash of the newest entry of the tenant's chain and of every run's chain, and
whether the ledger verified. Its own digest, over everything else it holds, is its last field.

An import refuses a document whose digest does not match, an object whose bytes do not hash to
its name, and a tenant the instance already holds anything of. It then writes the objects and
the rows, and checks the result where it now lives: the ledger verified from its first entry,
the same number of entries, the same newest hash on every chain, and every run's provenance
chain verified against its ledger entries. The import is recorded on the tenant's ledger after
the check, as `tenant.imported` with the export's digest; the export is recorded as
`tenant.exported` the same way, after it was read.

Neither is a backup. A backup restores a whole instance to a moment (ADR-0174); an export
moves one tenant between instances, or hands its data to its owner.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from taktus.components.run.domain.model import Run
from taktus.components.run.domain.service.provenance import verify as verify_provenance
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import (
    ArchivedRows,
    ProvenanceStore,
    Repository,
    Tenant,
    TenantArchive,
    TenantEntry,
    TenantImported,
    TenantNotEmpty,
    TenantStore,
    UnitOfWork,
)
from taktus.shared.v1 import LedgerEntry, LedgerRefs

FORMAT = "taktus.tenant-export/1"
EXPORTED = "tenant.exported"
IMPORTED = "tenant.imported"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ExportRefused(ValueError):
    """An export that cannot be taken, or a document that cannot be imported; nothing
    changed."""


def canonical(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def digest_of(document: dict[str, Any]) -> str:
    body = {k: v for k, v in document.items() if k != "digest"}
    return "sha256:" + hashlib.sha256(canonical(body)).hexdigest()


def heads(entries: Sequence[LedgerEntry]) -> dict[str, str]:
    """The hash of the newest entry of every chain, by chain: "" for the tenant's."""
    found: dict[str, str] = {}
    for entry in entries:
        found[entry.chain_name()] = entry.hash
    return found


class TenantExports:
    def __init__(
        self,
        *,
        archive: TenantArchive,
        tenants: TenantStore,
        objects: ObjectStore,
        ledger: Ledger,
        provenance: ProvenanceStore,
        runs: Repository[Run],
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._archive = archive
        self._tenants = tenants
        self._objects = objects
        self._ledger = ledger
        self._provenance = provenance
        self._runs = runs
        self._work = work
        self._clock = clock

    async def export(self, tenant: Tenant, *, by: str) -> bytes:
        """The tenant's export, as the bytes of its document. Recorded on its ledger after it
        was read; the record is not in it."""
        async with self._work.transaction(tenant):
            entry = await self._tenants.get(tenant)
            entries = await self._ledger.entries(tenant)
            verification = await self._ledger.verify(tenant, full=True)
        if entry is None:
            raise ExportRefused(f"this instance serves no tenant {tenant!r}")
        stores = await self._archive.export(tenant)
        # Every object a row names by digest: results, artifacts, messages, ledger content.
        text = canonical({"s": [s.document() for s in stores]}).decode("utf-8")
        named = sorted(set(DIGEST.findall(text)))
        objects: dict[str, str] = {}
        absent: list[str] = []
        for digest in named:
            content = await self._objects.get(digest)
            if content is None:
                absent.append(digest)  # erased on a request, or never stored: named, not held
            else:
                objects[digest] = base64.b64encode(content).decode("ascii")
        document: dict[str, Any] = {
            "format": FORMAT,
            "exported_at": self._clock.now().isoformat(),
            "tenant": {
                "id": entry.id,
                "name": entry.name,
                "created_at": entry.created_at.isoformat(),
            },
            "ledger": {
                "entries": len(entries),
                "heads": heads(entries),
                "verified": verification.intact,
                "findings": list(verification.findings),
            },
            "stores": [s.document() for s in stores],
            "objects": objects,
            "objects_absent": absent,
        }
        document["digest"] = digest_of(document)
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=EXPORTED,
                    refs=LedgerRefs(tenant=tenant, actor=by),
                    outcome="exported",
                    content_digest=document["digest"],
                ),
            )
        return canonical(document)

    async def import_(self, content: bytes, *, by: str) -> TenantImported:
        """Write an export into this instance and check its chains here."""
        try:
            document = json.loads(content)
        except (UnicodeDecodeError, ValueError) as error:
            raise ExportRefused(f"not an export: {error}") from error
        if not isinstance(document, dict) or document.get("format") != FORMAT:
            raise ExportRefused(f"not an export of the format {FORMAT}")
        if document.get("digest") != digest_of(document):
            raise ExportRefused("the export's digest does not match what it holds: it changed")
        entry = TenantEntry(
            id=document["tenant"]["id"],
            name=document["tenant"]["name"],
            created_at=datetime.fromisoformat(document["tenant"]["created_at"]),
        )
        blobs: dict[str, bytes] = {}
        for digest, encoded in document["objects"].items():
            blob = base64.b64decode(encoded)
            if "sha256:" + hashlib.sha256(blob).hexdigest() != digest:
                raise ExportRefused(f"object {digest} does not hold what its name says")
            blobs[digest] = blob
        stores = [ArchivedRows.model_validate(s) for s in document["stores"]]
        held = await self._archive.held(entry.id)
        if held:
            raise TenantNotEmpty(entry.id, held)
        for digest, blob in blobs.items():
            stored = await self._objects.put(blob)
            if stored != digest:
                raise ExportRefused(f"the object store names {digest} {stored}")
        rows = await self._archive.restore(entry, stores)
        imported = await self._checked(entry.id, document, rows=rows, objects=len(blobs))
        async with self._work.transaction(entry.id):
            await self._ledger.record(
                entry.id,
                Fact(
                    kind=IMPORTED,
                    refs=LedgerRefs(tenant=entry.id, actor=by),
                    outcome="verified" if imported.verified else "unverified",
                    content_digest=document["digest"],
                ),
            )
        return imported

    async def _checked(
        self, tenant: Tenant, document: dict[str, Any], *, rows: int, objects: int
    ) -> TenantImported:
        findings: list[str] = []
        provenance_intact = True
        async with self._work.transaction(tenant):
            entries = await self._ledger.entries(tenant)
            verification = await self._ledger.verify(tenant, full=True)
            for run in await self._runs.list(tenant):
                checked = verify_provenance(
                    run,
                    await self._provenance.of_run(tenant, run.id),
                    await self._ledger.entries(tenant, run.id),
                )
                provenance_intact &= checked.intact
                findings.extend(f"{run.id}: {f}" for f in checked.findings)
        findings.extend(verification.findings)
        expected = document["ledger"]
        if len(entries) != expected["entries"]:
            findings.append(
                f"the ledger holds {len(entries)} entries, the export {expected['entries']}"
            )
        now = heads(entries)
        moved = sorted(
            c or "tenant"
            for c in set(now) | set(expected["heads"])
            if now.get(c) != expected["heads"].get(c)
        )
        if moved:
            findings.append("the newest entry differs on the chains " + ", ".join(moved))
        return TenantImported(
            tenant=tenant,
            rows=rows,
            objects=objects,
            entries=len(entries),
            ledger_intact=verification.intact,
            heads_match=not moved and len(entries) == expected["entries"],
            provenance_intact=provenance_intact,
            findings=tuple(findings),
        )
