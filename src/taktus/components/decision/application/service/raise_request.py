"""Use case: raise a decision request (ADR-0008, ADR-0042).

The request is built in the one shape of `contracts/shared/v1/DecisionRequest.json`: the
situation, exactly what must be decided, at least two options with their consequences and
exactly one recommended with its reason, what is blocked, and the date an answer is needed by.
A request missing a part, or with a part that does not hold, is not raised: `NotRaised`, and
nothing is stored.

It is addressed to a role and reached on the control plane's own surface, where the identities
holding the role list, answer and confirm it (`CHANNEL`). Rendering it in a chat is the
owner-facing channel's (#85).

Raising is idempotent by the request's identifier: the run derives it from the run, the step,
the anchor and the round, so a run that raises again after a crash meets the request it raised
before and changes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from taktus.components.decision.application.service._ledger import RAISED, record
from taktus.components.decision.application.service.errors import NotRaised
from taktus.components.decision.domain.model import Request
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import DecisionRequest

CHANNEL = "controlplane.decisions"
"""The control plane's own surface, as the capability a request names for its channel."""


@dataclass(frozen=True)
class RaiseRequest:
    tenant: Tenant
    id: str
    run: str
    step: str
    class_: str
    situation: str
    question: str
    options: Sequence[Mapping[str, Any]]
    blocking: Sequence[str]
    due: date
    decider: str
    """The role that decides."""
    anchor: str | None = None


class RaiseRequestHandler:
    def __init__(
        self, requests: Repository[Request], work: UnitOfWork, ledger: Ledger, clock: Clock
    ) -> None:
        self._requests = requests
        self._work = work
        self._ledger = ledger
        self._clock = clock

    async def execute(self, command: RaiseRequest) -> Request:
        if not command.decider.strip():
            raise NotRaised("the request names no role to decide it")
        try:
            shaped = DecisionRequest.model_validate(
                {
                    "id": command.id,
                    "raised_by": {"run": command.run, "step": command.step},
                    "class": command.class_,
                    "situation": command.situation.strip(),
                    "question": command.question.strip(),
                    "options": [dict(o) for o in command.options],
                    "blocking": list(command.blocking),
                    "channel": {"connector": CHANNEL, "address": f"role:{command.decider}"},
                    "due": command.due,
                    "status": "open",
                }
            )
        except ValidationError as error:
            missing = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'request'}: {e['msg']}"
                for e in error.errors()
            )
            raise NotRaised(f"the request is not raised: {missing}") from error
        request = Request(
            id=command.id,
            tenant=command.tenant,
            decider=command.decider,
            anchor=command.anchor,
            raised_at=self._clock.now(),
            request=shaped,
        )
        async with self._work.transaction(command.tenant):
            existing = await self._requests.get(command.tenant, command.id)
            if existing is not None:
                return existing
            await self._requests.put(command.tenant, request)
            await record(
                self._ledger,
                request,
                RAISED,
                str(shaped.class_),
                document=shaped.document(),
            )
        return request
