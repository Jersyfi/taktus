"""The processes Taktus proposes, listed for a person and accepted or declined one by one
(UC-4.4, ADR-0270).

`ProcessProposals.listed` reads the tenant's ledger — `run.created` and `run.triggered`, the
heals and their recurrences, and the decisions taken already — and the runs' consumption, and
has the process component's rule (`domain/service/proposing.py`) find and order the proposals.
Nothing is stored to make the list. A person is shown the proposals that concern no person, and
the ones drawn from runs that person started; nobody else's.

`accept` hands the proposal's words to the request path of ADR-0251 §1 (`ProposalActs.ask`),
acting for the person, and records `proposal.accepted`; `decline` records `proposal.declined`.
Either is the act of the one person the proposal is shown to, once.

This is wiring, because the entries are the run component's and the ledger's, the versions the
process component's, and the request path crosses the command and run components.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from taktus.components.process.domain.model import ProcessVersion
from taktus.components.process.domain.service import proposing
from taktus.components.process.domain.service.proposing import (
    ProcessProposal,
    Recurrence,
    Start,
)
from taktus.components.run.domain.model import Run
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import ConsumptionQuantities, LedgerEntry, LedgerRefs

CREATED = "run.created"
TRIGGERED = "run.triggered"
HEALED = "step.healed"
RECURRED = "heal.recurred"
ACCEPTED = "proposal.accepted"
DECLINED = "proposal.declined"


class Asking(Protocol):
    """The request path of ADR-0251 §1: words for a process, a run that builds a proposal."""

    async def ask(self, tenant: Tenant, process_id: str, request: str, by: str) -> Run: ...


class ProposalRefused(Exception):
    """A proposal that is not the person's to decide, or is decided already."""


@dataclass(frozen=True)
class Accepted:
    proposal: ProcessProposal
    run: Run
    """The run that builds the proposal of a version (UC-4.1, UC-4.15)."""


def decided_digest(proposal_id: str) -> str:
    """How a decision names the proposal in the ledger: the digest of its identifier."""
    return "sha256:" + hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()


def used_of(quantities: ConsumptionQuantities | None) -> dict[str, float]:
    """What a run consumed as named numbers: each quantity, money by its currency code."""
    if quantities is None:
        return {}
    found: dict[str, float] = {}
    for name, value in quantities.quantities().items():
        if name == "currency":
            found.update({f"currency.{code}": float(v) for code, v in value.items()})
        elif isinstance(value, int | float) and not isinstance(value, bool):
            found[name] = float(value)
    return found


class ProcessProposals:
    def __init__(
        self,
        *,
        ledger: Ledger,
        runs: Repository[Run],
        versions: Repository[ProcessVersion],
        objects: ObjectStore,
        work: UnitOfWork,
        clock: Clock,
        asking: Asking | None = None,
    ) -> None:
        self._ledger = ledger
        self._runs = runs
        self._versions = versions
        self._objects = objects
        self._work = work
        self._clock = clock
        self._asking = asking

    async def listed(self, tenant: Tenant, viewer: str) -> list[ProcessProposal]:
        """The proposals `viewer` is shown, most often recurring first, none decided already."""
        return proposing.visible(await self._open(tenant), viewer)

    async def accept(self, tenant: Tenant, proposal_id: str, by: str) -> Accepted:
        proposal = await self._decidable(tenant, proposal_id, by)
        if self._asking is None:
            raise ProposalRefused(
                "no request path builds a process on this instance (ADR-0251): nothing accepted"
            )
        run = await self._asking.ask(tenant, proposal.process_id, proposal.words, by)
        await self._record(tenant, ACCEPTED, proposal, by, run.id)
        return Accepted(proposal=proposal, run=run)

    async def decline(self, tenant: Tenant, proposal_id: str, by: str) -> ProcessProposal:
        proposal = await self._decidable(tenant, proposal_id, by)
        await self._record(tenant, DECLINED, proposal, by, None)
        return proposal

    async def _decidable(self, tenant: Tenant, proposal_id: str, by: str) -> ProcessProposal:
        for proposal in proposing.visible(await self._open(tenant), by):
            if proposal.id == proposal_id:
                return proposal
        raise ProposalRefused(
            f"no open proposal {proposal_id!r} is shown to {by!r}: it is decided already, or "
            "it is not theirs"
        )

    async def _record(
        self, tenant: Tenant, kind: str, proposal: ProcessProposal, by: str, run_id: str | None
    ) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=tenant, actor=by, run_id=run_id),
                    outcome=kind.removeprefix("proposal."),
                    content_digest=decided_digest(proposal.id),
                ),
            )

    async def _open(self, tenant: Tenant) -> list[ProcessProposal]:
        async with self._work.transaction(tenant):
            entries = list(
                await self._ledger.of_kinds(
                    tenant, (CREATED, TRIGGERED, HEALED, RECURRED, ACCEPTED, DECLINED)
                )
            )
        decided = {e.content_digest for e in entries if e.kind in (ACCEPTED, DECLINED)}
        found = proposing.proposals(
            self._starts(entries),
            await self._recurrences(tenant, entries),
            self._clock.now(),
            await self._costs(tenant, entries),
        )
        return [p for p in found if decided_digest(p.id) not in decided]

    @staticmethod
    def _starts(entries: Sequence[LedgerEntry]) -> list[Start]:
        triggered = {e.refs.run_id for e in entries if e.kind == TRIGGERED}
        return [
            Start(
                process_id=(e.refs.process_version or "").split("@", 1)[0],
                process_name=(e.refs.process_version or "").split("@", 1)[0],
                identity=e.refs.actor or "",
                at=e.ts,
            )
            for e in entries
            if e.kind == CREATED
            and not e.rehearsal
            and e.refs.run_id not in triggered
            and e.refs.actor is not None
            and e.refs.process_version is not None
        ]

    async def _costs(
        self, tenant: Tenant, entries: Sequence[LedgerEntry]
    ) -> dict[str, dict[str, float]]:
        """What a run of each process consumed on average, over all its runs, whoever started
        them: the process's cost (ADR-0270 §2)."""
        runs: dict[str, list[str]] = {}
        for e in entries:
            if e.kind == CREATED and not e.rehearsal and e.refs.process_version and e.refs.run_id:
                runs.setdefault(e.refs.process_version.split("@", 1)[0], []).append(e.refs.run_id)
        costs: dict[str, dict[str, float]] = {}
        async with self._work.transaction(tenant):
            for process_id, ids in runs.items():
                found = [await self._runs.get(tenant, run_id) for run_id in ids]
                costs[process_id] = _mean([used_of(r.consumed()) for r in found if r is not None])
        return costs

    async def _recurrences(
        self, tenant: Tenant, entries: Sequence[LedgerEntry]
    ) -> list[Recurrence]:
        now = self._clock.now()
        heals: list[tuple[LedgerEntry, str]] = []
        for entry in entries:
            if entry.kind == HEALED and not entry.rehearsal and entry.content_digest is not None:
                stored = await self._objects.get(entry.content_digest)
                reason = "" if stored is None else str(json.loads(stored).get("failure") or "")
                heals.append((entry, reason))
        found: list[Recurrence] = []
        for entry in entries:
            if entry.kind != RECURRED or entry.refs.process_version is None:
                continue
            ref = entry.refs.process_version
            process_id = ref.split("@", 1)[0]
            same = [
                (heal, reason)
                for heal, reason in heals
                if (heal.refs.process_version or "").split("@", 1)[0] == process_id
                and heal.refs.step_id == entry.refs.step_id
                and "sha256:" + hashlib.sha256(reason.encode("utf-8")).hexdigest()
                == entry.content_digest
            ]
            async with self._work.transaction(tenant):
                version = await self._versions.get(tenant, ref)
                runs = [await self._runs.get(tenant, heal.refs.run_id or "") for heal, _ in same]
            used = [used_of(run.consumed()) for run in runs if run is not None]
            found.append(
                Recurrence(
                    process_id=process_id,
                    process_name=process_id if version is None else version.name,
                    step=entry.refs.step_id or "",
                    failure=same[0][1] if same else "a failure healed again and again",
                    healed=len(same),
                    recent=sum(1 for heal, _ in same if now - heal.ts <= proposing.MONTH),
                    at=entry.ts,
                    used=_mean(used),
                )
            )
        return found


def _mean(used: Sequence[dict[str, float]]) -> dict[str, float]:
    names = {name for each in used for name in each}
    if not used:
        return {}
    return {name: sum(each.get(name, 0.0) for each in used) / len(used) for name in names}
