"""A tenant's residency rule, kept and changed (ADR-0116 §3, UC-11.1).

The rule says where the tenant's data may be processed, narrowed per data class. The run asks
it through its port `Residency` before it routes a step to a model; a model whose location the
rule does not permit is never chosen. A change is the ledger entry `residency.configured` in
the transaction that stores it, naming who changed it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from taktus.components.governance.domain.model.residency import ResidencyRule, shipped_rule
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.model import Permitted
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

CONFIGURED = "residency.configured"


@dataclass(frozen=True)
class ConfigureResidency:
    """What a tenant sets of its rule. `location` None keeps the tenant's own; `classes` adds
    or replaces the rule of each class it names; `cleared` removes the rule of each class it
    names."""

    tenant: Tenant
    location: Permitted | None = None
    classes: Mapping[str, Permitted] = field(default_factory=dict)
    cleared: tuple[str, ...] = ()


class TenantResidency:
    def __init__(
        self, rules: Repository[ResidencyRule], ledger: Ledger, work: UnitOfWork, clock: Clock
    ) -> None:
        self._rules = rules
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def rule(self, tenant: Tenant) -> ResidencyRule:
        """The tenant's rule, or the shipped default where it set none."""
        async with self._work.transaction(tenant):
            found = await self._rules.get(tenant, tenant)
        return found or shipped_rule(tenant)

    async def permitted(self, tenant: Tenant, data_class: str | None) -> Permitted:
        """The run's port: where data of the class may be processed for the tenant."""
        return (await self.rule(tenant)).permitted(data_class)

    async def configure(self, command: ConfigureResidency, *, by: str) -> ResidencyRule:
        """Set what the command names, keep the rest. A rule that does not hold — a class wider
        than the tenant's own — is refused as a ValueError and changes nothing."""
        current = await self.rule(command.tenant)
        classes = {
            name: location
            for name, location in {**current.classes, **command.classes}.items()
            if name not in command.cleared
        }
        configured = ResidencyRule.model_validate(
            {
                **current.model_dump(),
                "location": command.location or current.location,
                "classes": classes,
                "configured_at": self._clock.now(),
            }
        )
        async with self._work.transaction(command.tenant):
            await self._rules.put(command.tenant, configured)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome=configured.location,
                ),
            )
        return configured
