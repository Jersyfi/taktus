"""Data-protection requests: prepared by Taktus, carried out by a person (ADR-0176, UC-11.2).

`prepare` finds what the tenant holds of a subject and stores the request; it changes nothing
else. `confirm` carries a prepared request out, for a person who checked the requester's
identity, on exactly the holdings that person was shown: an erasure erases them, an access or
portability export is generated and handed back, and a rectification is recorded as done by
the person at the source. `withdraw` ends a prepared request. Every one of them is a ledger
entry naming the request and who acted, never the subject (ADR-0006).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from taktus.components.governance.domain.model.subjects import (
    Exported,
    Outcome,
    RequestKind,
    RequestRefused,
    SubjectRequest,
    carried_out,
    confirmable,
    signature,
    withdrawn,
)
from taktus.components.governance.ports.subjects import SubjectHoldings
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

PREPARED = "subject.request_prepared"
ERASED = "subject.erased"
EXPORTED = "subject.exported"
RECTIFIED = "subject.rectified"
WITHDRAWN = "subject.request_withdrawn"
KINDS = frozenset({PREPARED, ERASED, EXPORTED, RECTIFIED, WITHDRAWN})
"""The tenant-chain entries of a request; `run.content_erased` is on each erased run's chain."""


@dataclass(frozen=True)
class PrepareRequest:
    tenant: Tenant
    kind: RequestKind
    subject: str


@dataclass(frozen=True)
class Confirmed:
    """A request carried out; `export` is the document of an access or portability request,
    handed to the caller and stored nowhere."""

    request: SubjectRequest
    export: bytes | None = None


def canonical(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")


class SubjectRequests:
    def __init__(
        self,
        requests: Repository[SubjectRequest],
        holdings: SubjectHoldings,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._requests = requests
        self._holdings = holdings
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids

    async def prepare(self, command: PrepareRequest, *, by: str) -> SubjectRequest:
        subject = command.subject.strip()
        if not subject:
            raise RequestRefused("a request names its subject")
        found = await self._holdings.holdings(command.tenant, subject)
        request = SubjectRequest(
            id=self._ids.new("dsr"),
            tenant=command.tenant,
            kind=command.kind,
            subject=subject,
            holdings=tuple(found),
            created_at=self._clock.now(),
            prepared_by=by,
        )
        async with self._work.transaction(command.tenant):
            await self._requests.put(command.tenant, request)
            await self._record(command.tenant, PREPARED, request, by, outcome=request.kind.value)
        return request

    async def get(self, tenant: Tenant, request_id: str) -> SubjectRequest | None:
        async with self._work.transaction(tenant):
            return await self._requests.get(tenant, request_id)

    async def list(self, tenant: Tenant) -> Sequence[SubjectRequest]:
        async with self._work.transaction(tenant):
            return await self._requests.list(tenant)

    async def confirm(
        self, tenant: Tenant, request_id: str, *, by: str, identity_checked: bool
    ) -> Confirmed:
        """Carry the request out. Refused, changing nothing, where it is not prepared, where
        the person did not state the identity check, or where the holdings changed since it
        was prepared."""
        request = await self._known(tenant, request_id)
        confirmable(request, identity_checked=identity_checked)
        now = await self._holdings.holdings(tenant, request.subject)
        if signature(tuple(now)) != signature(request.holdings):
            raise RequestRefused(
                f"what Taktus holds of the subject changed since request {request.id} was "
                "prepared; withdraw it and prepare a new one, so that the confirmation covers "
                "what it acts on"
            )
        export: bytes | None = None
        if request.kind is RequestKind.ERASURE:
            erased = await self._holdings.erase(tenant, request.id, request.holdings)
            outcome = Outcome(erased=erased)
            kind = ERASED
            said = "verified" if erased.ledger_intact and erased.provenance_intact else "unverified"
            digest = None
        elif request.kind in (RequestKind.ACCESS, RequestKind.PORTABILITY):
            document = await self._holdings.export(
                tenant, request.holdings, processing=request.kind is RequestKind.ACCESS
            )
            export = canonical(
                {
                    "request": request.id,
                    "kind": request.kind.value,
                    "subject": request.subject,
                    "generated_at": self._clock.now().isoformat(),
                    **document,
                }
            )
            digest = "sha256:" + hashlib.sha256(export).hexdigest()
            outcome = Outcome(exported=Exported(digest=digest, size_bytes=len(export)))
            kind, said = EXPORTED, request.kind.value
        else:
            outcome, kind, said, digest = Outcome(), RECTIFIED, "confirmed", None
        done = carried_out(request, by=by, at=self._clock.now(), outcome=outcome)
        async with self._work.transaction(tenant):
            await self._requests.put(tenant, done)
            await self._record(tenant, kind, done, by, outcome=said, digest=digest)
        return Confirmed(request=done, export=export)

    async def withdraw(self, tenant: Tenant, request_id: str, *, by: str) -> SubjectRequest:
        request = withdrawn(await self._known(tenant, request_id), by=by, at=self._clock.now())
        async with self._work.transaction(tenant):
            await self._requests.put(tenant, request)
            await self._record(tenant, WITHDRAWN, request, by, outcome="withdrawn")
        return request

    async def _known(self, tenant: Tenant, request_id: str) -> SubjectRequest:
        found = await self.get(tenant, request_id)
        if found is None:
            raise RequestRefused(f"no request {request_id!r}")
        return found

    async def _record(
        self,
        tenant: Tenant,
        kind: str,
        request: SubjectRequest,
        by: str,
        *,
        outcome: str,
        digest: str | None = None,
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(tenant=tenant, subject_request_id=request.id, actor=by),
                outcome=outcome,
                content_digest=digest,
            ),
        )
