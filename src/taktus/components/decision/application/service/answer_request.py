"""Use case: a decider answers a request (ADR-0008, ADR-0042).

Only an identity holding the role the request names may answer. The answer is either the
identifier of one option or free text. **Neither is acted on.** It is read
(`domain.service.interpretation`), its reading is sent back in one message, and the request
waits in `interpreted` until the same person confirms the reading (`confirm_request.py`). Free
text from which no single option can be read leaves the request `answered`, and the message asks
for one option. A new answer replaces the one before, as long as nothing was confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.decision.application.service._ledger import ANSWERED, INTERPRETED, record
from taktus.components.decision.application.service.errors import (
    NotAnswerable,
    NotTheDecider,
    UnknownRequest,
)
from taktus.components.decision.domain.model import Request
from taktus.components.decision.domain.service.interpretation import chosen, interpret, reflect
from taktus.components.decision.ports import Deciders
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import AnswerInterpreted, DecisionStatus

ANSWERABLE = frozenset({DecisionStatus.OPEN, DecisionStatus.ANSWERED, DecisionStatus.INTERPRETED})


@dataclass(frozen=True)
class AnswerRequest:
    tenant: Tenant
    request_id: str
    identity: str
    """Who answers: an identity holding the role the request names."""
    text: str | None = None
    """Free text, as the person wrote it."""
    option: str | None = None
    """The identifier of one option, chosen as such."""


@dataclass(frozen=True)
class Answered:
    request: Request
    message: str
    """The one message sent back: the reading to confirm, or why there is none."""


class AnswerRequestHandler:
    def __init__(
        self,
        requests: Repository[Request],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        deciders: Deciders,
    ) -> None:
        self._requests = requests
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._deciders = deciders

    async def execute(self, command: AnswerRequest) -> Answered:
        if (command.text is None) == (command.option is None):
            raise NotAnswerable("answer with an option or with text, not both and not neither")
        raw = command.option if command.option is not None else (command.text or "")
        if not raw.strip():
            raise NotAnswerable("the answer is empty")
        async with self._work.transaction(command.tenant):
            request = await self._requests.get(command.tenant, command.request_id)
        if request is None:
            raise UnknownRequest(command.tenant, command.request_id)
        decider = await self._deciders.place(command.tenant, command.identity)
        if decider is None or request.decider not in decider.roles:
            raise NotTheDecider(
                f"{command.identity} does not hold the role {request.decider!r} that decides "
                f"{request.id}"
            )
        if request.status not in ANSWERABLE:
            raise NotAnswerable(f"{request.id} is {request.status}; its answer took effect")
        shaped = request.request
        reading: AnswerInterpreted | None
        if command.option is not None:
            if command.option not in {o.id for o in shaped.options}:
                raise NotAnswerable(f"{request.id} has no option {command.option!r}")
            reading = chosen(command.option)
        else:
            reading = interpret(raw, shaped.options)
        status = DecisionStatus.ANSWERED if reading is None else DecisionStatus.INTERPRETED
        message = reflect(shaped, reading)
        answered = request.model_copy(
            update={
                "request": shaped.model_copy(
                    update={
                        "status": status,
                        "answer_raw": raw.strip(),
                        "answer_interpreted": reading,
                    }
                ),
                "answered_by": command.identity,
                "answered_at": self._clock.now(),
                "reflection": message,
            }
        )
        async with self._work.transaction(command.tenant):
            await self._requests.put(command.tenant, answered)
            await record(
                self._ledger,
                answered,
                ANSWERED,
                INTERPRETED if reading is not None else "unread",
                actor=command.identity,
                document={"answer_raw": raw.strip(), "reflection": message},
            )
        return Answered(answered, message)
