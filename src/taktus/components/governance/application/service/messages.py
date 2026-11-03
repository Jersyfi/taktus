"""A tenant's rules for its outward messages, and the cases a person answered in, kept and
changed (ADR-0142, UC-7.6).

The run asks both through its port `Messages` before a message step sends. A change of the
rules is the ledger entry `messages.configured`, and an answer in a case `case.answered`, each
in the transaction that stores it and naming who acted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from taktus.components.governance.domain.model.messages import (
    CaseAnswer,
    MessageRules,
    case_key,
    shipped_rules,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

CONFIGURED = "messages.configured"
ANSWERED = "case.answered"

UNSET = "-"
"""What `ConfigureMessages` gives for a value it takes away: the label, or the quiet hours."""


@dataclass(frozen=True)
class ConfigureMessages:
    """What a tenant changes of its rules; None keeps a value as it is. A label or quiet hours
    of `UNSET` take them away."""

    tenant: Tenant
    label: str | None = None
    delay_seconds: int | None = None
    quiet: tuple[time, time] | str | None = None
    zone: str | None = None
    recipient_limit: int | None = None


class TenantMessages:
    def __init__(
        self,
        rules: Repository[MessageRules],
        answers: Repository[CaseAnswer],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._rules = rules
        self._answers = answers
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def rules(self, tenant: Tenant) -> MessageRules:
        """The tenant's rules, or the shipped default where it configured none."""
        async with self._work.transaction(tenant):
            found = await self._rules.get(tenant, tenant)
        return found or shipped_rules(tenant)

    async def configure(self, command: ConfigureMessages, *, by: str) -> MessageRules:
        """Change what the command names and keep the rest. Rules that do not hold are refused
        as a ValueError and change nothing."""
        current = await self.rules(command.tenant)
        changes: dict[str, object] = {"configured_at": self._clock.now()}
        if command.label is not None:
            changes["label"] = None if command.label == UNSET else command.label
        if command.delay_seconds is not None:
            changes["delay_seconds"] = command.delay_seconds
        if command.quiet == UNSET:
            changes["quiet_begins"] = changes["quiet_ends"] = None
        elif isinstance(command.quiet, tuple):
            changes["quiet_begins"], changes["quiet_ends"] = command.quiet
        if command.zone is not None:
            changes["zone"] = command.zone
        if command.recipient_limit is not None:
            changes["recipient_limit"] = command.recipient_limit
        configured = MessageRules.model_validate({**current.document(), **changes})
        async with self._work.transaction(command.tenant):
            await self._rules.put(command.tenant, configured)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome="configured",
                ),
            )
        return configured

    async def answered(self, tenant: Tenant, process: str, case: str) -> bool:
        """The run's port: whether a person answered in the case of the process."""
        async with self._work.transaction(tenant):
            return await self._answers.get(tenant, case_key(process, case)) is not None

    async def answer(self, tenant: Tenant, process: str, case: str, *, by: str) -> CaseAnswer:
        """Record that a person answered in the case: the process sends nothing more in it. An
        answer recorded before stays as it was."""
        key = case_key(process, case)
        async with self._work.transaction(tenant):
            found = await self._answers.get(tenant, key)
            if found is not None:
                return found
            recorded = CaseAnswer(
                id=key, tenant=tenant, process=process, case=case, answered_at=self._clock.now()
            )
            await self._answers.put(tenant, recorded)
            await self._ledger.record(
                tenant,
                Fact(kind=ANSWERED, refs=LedgerRefs(tenant=tenant, actor=by), outcome="answered"),
            )
        return recorded
