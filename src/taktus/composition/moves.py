"""A proposal to move a step to a trained model, accepted, applied; and the move rolled back
(ADR-0114, issue #218, DEC-0164 provisionally Option A).

- **Apply.** A proposal is a decision request (ADR-0084 §6). Once a person's answer took
  effect with the option that moves the step, and without modifications, the step's process
  gains a new version: the active version written back as a bundle, the step in it moved by
  `run.domain.service.maturation.moved_step`, registered through the one registration every
  version takes. Registration refuses a step on a trained model without its evaluation on the
  held-out cases (UC-8.4 §2). The replaced version stays registered and unchanged. The ledger
  records `method.moved`, with the person whose answer took effect as its actor and the move by
  digest. Applied twice, the same proposal gives the same version.
- **Roll back.** One act: the version the move replaced is registered again as a new version,
  and becomes current. The ledger records `process.rolled_back`, as every rollback does
  (ADR-0091 §5), and `method.rolled_back` with the move. A person may roll back at any time; a
  proposal to roll back that a person accepted does the same (`ReviewMovesHandler`).
- **Decided.** Every decision that took effect is handed here. One that answers a proposal to
  move, or to roll back, is applied; any other changes nothing.

This is wiring, because each act crosses components — run, decision and process — and only the
composition root may hold them all (`composition/README.md`).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.components.process.domain.service.bundle import bundle_of, next_version
from taktus.components.run.application.service.maturation import PROPOSED
from taktus.components.run.application.service.moves import MoveError
from taktus.components.run.domain.service import maturation
from taktus.components.run.domain.service.maturation import Move, MoveReview, Proposal
from taktus.components.run.ports import Decisions
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs, Method

ROLLED_BACK = "process.rolled_back"
"""The ledger kind of every rollback (ADR-0091 §5)."""


class MethodMoves:
    def __init__(
        self,
        *,
        versions: Repository[ProcessVersion],
        processes: Repository[Process],
        register: RegisterProcessVersionHandler,
        decisions: Decisions,
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
    ) -> None:
        self._versions = versions
        self._processes = processes
        self._register = register
        self._decisions = decisions
        self._ledger = ledger
        self._objects = objects
        self._work = work

    async def decided(self, tenant: Tenant, request_id: str) -> ProcessVersion | None:
        """A decision took effect. A proposal to move that was accepted is applied; a proposal
        to roll back that was accepted rolls back; any other decision changes nothing, and
        neither does a proposal declined. None when nothing was registered."""
        entries = await self._entries(tenant)
        if any(_proposed(e, request_id) for e in entries):
            verdict = await self._decisions.verdict(tenant, request_id)
            if verdict is None or verdict.option != maturation.ACCEPT:
                return None
            return await self.apply(tenant, request_id)
        for entry in entries:
            if entry.kind == maturation.MEASURED and entry.refs.decision_request_id == request_id:
                verdict = await self._decisions.verdict(tenant, request_id)
                if verdict is None or not verdict.applied or verdict.option != maturation.ACCEPT:
                    return None
                if verdict.modified:
                    raise MoveError(
                        "modified",
                        f"the answer to {request_id} modified the proposal to roll back; a "
                        "rollback is made as proposed only",
                    )
                review = MoveReview.model_validate(await self._document(entry))
                return await self.rollback(
                    tenant, review.move.process_id, by=verdict.decided_by or "unknown"
                )
        return None

    async def apply(self, tenant: Tenant, request_id: str) -> ProcessVersion:
        """The new version in which the proposed step runs on the trained model, registered;
        or MoveError naming why not."""
        entries = await self._entries(tenant)
        proposed = next((e for e in entries if _proposed(e, request_id)), None)
        if proposed is None:
            raise MoveError("unknown", f"{request_id} is no proposal to move a step")
        verdict = await self._decisions.verdict(tenant, request_id)
        if verdict is None or not verdict.applied:
            raise MoveError(
                "undecided", f"no answer to {request_id} took effect: a person decides the move"
            )
        if verdict.option != maturation.ACCEPT:
            raise MoveError(
                "declined", f"{request_id} was answered with option {verdict.option}: not moved"
            )
        if verdict.modified:
            raise MoveError(
                "modified",
                f"the answer to {request_id} modified the proposal; a move is applied as "
                "proposed only, and a changed one is a change of the process (ADR-0091)",
            )
        for move in await self._moves(entries):
            if move.request_id == request_id:
                async with self._work.transaction(tenant):
                    stored = await self._versions.get(tenant, move.process_version)
                if stored is not None:
                    return stored
        proposal = Proposal.model_validate(await self._document(proposed))
        model = await self._objects.get(proposal.evidence.digest)
        if model is None:
            raise MoveError(
                "unknown",
                f"the model {proposal.evidence.digest} is no longer in the object store: "
                "propose again",
            )
        process_id = proposal.process_version.split("@", 1)[0]
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            base = await self._versions.get(tenant, proposal.process_version)
            registered = [
                v.version for v in await self._versions.list(tenant) if v.process_id == process_id
            ]
        if base is None or process is None:
            raise MoveError("unknown", f"no registered version {proposal.process_version}")
        if f"{process_id}@{process.active_version}" != proposal.process_version:
            raise MoveError(
                "stale",
                f"the proposal was made on {proposal.process_version}, and {process_id} is at "
                f"version {process.active_version}: the step is proposed again on its cases there",
            )
        by = verdict.decided_by or "unknown"
        bundle = bundle_of(
            base,
            as_version=next_version(registered),
            author=by,
            reason=(
                f"step {proposal.step_id} moved to the trained model {proposal.model} on the "
                f"proposal {request_id}"
            ),
        )
        try:
            bundle["steps"] = _replaced(bundle["steps"], proposal, model, request_id)
        except ValueError as error:
            raise MoveError("refused", str(error)) from error
        version = await self._registered(tenant, bundle, by)
        move = Move(
            process_version=version.ref,
            replaced=base.ref,
            step_id=proposal.step_id,
            request_id=request_id,
            model=proposal.model,
            model_digest=proposal.evidence.digest,
            threshold=proposal.threshold,
        )
        await self._record(tenant, maturation.MOVED, move, version, "moved", by)
        return version

    async def rollback(self, tenant: Tenant, process_id: str, *, by: str) -> ProcessVersion:
        """The version the newest move of the process replaced, current again as a new
        version. Only a move whose version is current can be rolled back: a later change is a
        version of its own, rolled back as any other (ADR-0091 §5)."""
        entries = await self._entries(tenant)
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            registered = [
                v.version for v in await self._versions.list(tenant) if v.process_id == process_id
            ]
        if process is None or process.active_version is None:
            raise MoveError("unknown", f"no process {process_id!r}")
        active = f"{process_id}@{process.active_version}"
        move = next(
            (m for m in reversed(await self._moves(entries)) if m.process_version == active), None
        )
        if move is None:
            raise MoveError(
                "unknown", f"{active} is not a version a step was moved to a trained model in"
            )
        async with self._work.transaction(tenant):
            earlier = await self._versions.get(tenant, move.replaced)
        if earlier is None:
            raise MoveError("unknown", f"no registered version {move.replaced}")
        bundle = bundle_of(
            earlier,
            as_version=next_version(registered),
            author=by,
            reason=(
                f"rolled back to {earlier.version}: step {move.step_id} goes back to the "
                f"language model, undoing the move {move.request_id}"
            ),
        )
        version = await self._registered(tenant, bundle, by)
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=ROLLED_BACK,
                    refs=LedgerRefs(tenant=tenant, process_version=version.ref, actor=by),
                    outcome="restored",
                ),
            )
        await self._record(tenant, maturation.ROLLED_BACK, move, version, "restored", by)
        return version

    async def _registered(self, tenant: Tenant, bundle: dict[str, Any], by: str) -> ProcessVersion:
        try:
            return await self._register.execute(
                RegisterProcessVersion(bundle, tenant=tenant, by=by)
            )
        except InvalidProcess as error:
            raise MoveError("refused", "; ".join(error.findings)) from error

    async def _entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        async with self._work.transaction(tenant):
            return await self._ledger.of_kinds(
                tenant, (PROPOSED, maturation.MOVED, maturation.MEASURED)
            )

    async def _moves(self, entries: Sequence[LedgerEntry]) -> list[Move]:
        return [
            Move.model_validate(await self._document(e))
            for e in entries
            if e.kind == maturation.MOVED and e.content_digest is not None
        ]

    async def _document(self, entry: LedgerEntry) -> Any:
        content = (
            None if entry.content_digest is None else await self._objects.get(entry.content_digest)
        )
        if content is None:
            raise MoveError("unknown", f"the document of {entry.kind} is not in the object store")
        return json.loads(content)

    async def _record(
        self, tenant: Tenant, kind: str, move: Move, version: ProcessVersion, outcome: str, by: str
    ) -> None:
        content = json.dumps(move.document(), ensure_ascii=False, sort_keys=True)
        digest = await self._objects.put(content.encode("utf-8"))
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=version.ref,
                        step_id=move.step_id,
                        decision_request_id=move.request_id,
                        actor=by,
                    ),
                    method=Method.ML,
                    outcome=outcome,
                    content_digest=digest,
                ),
            )


def _proposed(entry: LedgerEntry, request_id: str) -> bool:
    return (
        entry.kind == PROPOSED
        and entry.outcome == "proposed"
        and entry.refs.decision_request_id == request_id
    )


def _replaced(
    steps: list[dict[str, Any]], proposal: Proposal, model: bytes, request_id: str
) -> list[dict[str, Any]]:
    """The bundle's steps with the proposed one moved; ValueError when it is not there."""
    if not any(step.get("id") == proposal.step_id for step in steps):
        raise ValueError(f"the version has no step {proposal.step_id!r}")
    return [
        maturation.moved_step(proposal, step, model, request_id)
        if step.get("id") == proposal.step_id
        else step
        for step in steps
    ]
