"""Use case: the decider confirms, or rejects, how their answer was read (ADR-0008, ADR-0042).

Only the person whose answer was read confirms its reading. A confirmed reading takes effect:
the request becomes `confirmed`, then `applied`, and the decision register gains its entry —
linked to the run, the step and the request — in the same transaction. A rejected reading
takes nothing into effect: the request is open again, and the next answer is read afresh.

What the run does with the decision is the run's: the composition root hands the applied request
to the run engine, which continues or halts the run at the boundary it waits at.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.decision.application.service._ledger import (
    APPLIED,
    CONFIRMED,
    REREAD,
    record,
)
from taktus.components.decision.application.service.errors import (
    NotAnswerable,
    NotTheDecider,
    UnknownRequest,
)
from taktus.components.decision.domain.model import RegisterEntry, Request, entry_id
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import DecisionStatus


@dataclass(frozen=True)
class ConfirmRequest:
    tenant: Tenant
    request_id: str
    identity: str
    confirmed: bool = True
    """False: the reading is wrong; nothing takes effect and the request is open again."""


@dataclass(frozen=True)
class Confirmed:
    request: Request
    entry: RegisterEntry | None
    """The register entry, when the reading was confirmed."""


class ConfirmRequestHandler:
    def __init__(
        self,
        requests: Repository[Request],
        register: Repository[RegisterEntry],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._requests = requests
        self._register = register
        self._work = work
        self._ledger = ledger
        self._clock = clock

    async def execute(self, command: ConfirmRequest) -> Confirmed:
        now = self._clock.now()
        async with self._work.transaction(command.tenant):
            request = await self._requests.get(command.tenant, command.request_id)
            if request is None:
                raise UnknownRequest(command.tenant, command.request_id)
            shaped = request.request
            reading = shaped.answer_interpreted
            if request.status is not DecisionStatus.INTERPRETED or reading is None:
                raise NotAnswerable(
                    f"{request.id} is {request.status}: only a reading sent back is confirmed"
                )
            if request.answered_by != command.identity:
                raise NotTheDecider(
                    f"{command.identity} did not give the answer of {request.id}; the person "
                    "who did confirms how it was read"
                )
            if not command.confirmed:
                reopened = request.model_copy(
                    update={
                        "request": shaped.model_copy(
                            update={
                                "status": DecisionStatus.OPEN,
                                "answer_raw": None,
                                "answer_interpreted": None,
                            }
                        ),
                        "answered_by": None,
                        "answered_at": None,
                        "reflection": None,
                    }
                )
                await self._requests.put(command.tenant, reopened)
                await record(self._ledger, reopened, REREAD, "rejected", actor=command.identity)
                return Confirmed(reopened, None)
            option = next(o for o in shaped.options if o.id == reading.option)
            entry = RegisterEntry.model_validate(
                {
                    "id": entry_id(request.id),
                    "tenant": request.tenant,
                    "request_id": request.id,
                    "run_id": shaped.raised_by.run,
                    "step_id": shaped.raised_by.step,
                    "class": shaped.class_,
                    "anchor": request.anchor,
                    "decider": request.decider,
                    "option": option.id,
                    "proposal": option.proposal,
                    "modifications": reading.modifications,
                    "answer_raw": shaped.answer_raw or option.id,
                    "decided_by": command.identity,
                    "raised_at": request.raised_at,
                    "answered_at": request.answered_at or now,
                    "decided_at": now,
                }
            )
            applied = request.model_copy(
                update={
                    "request": shaped.model_copy(
                        update={"status": DecisionStatus.APPLIED, "outcome": entry.id}
                    ),
                    "decided_by": command.identity,
                    "decided_at": now,
                }
            )
            await self._register.put(command.tenant, entry)
            await self._requests.put(command.tenant, applied)
            outcome = f"option_{option.id.lower()}"
            await record(self._ledger, applied, CONFIRMED, outcome, actor=command.identity)
            await record(
                self._ledger,
                applied,
                APPLIED,
                outcome,
                actor=command.identity,
                document=entry.document(),
            )
        return Confirmed(applied, entry)
