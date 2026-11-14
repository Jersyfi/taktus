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
    processes: Mapping[str, Permitted] = field(default_factory=dict)
    """Adds or replaces the rule of each process it names (ADR-0258)."""
    cleared_processes: tuple[str, ...] = ()
    terms: tuple[str, ...] | None = None
    """The terms demanded for all the tenant's data, in place of the current ones; None keeps
    them (ADR-0334)."""
    class_terms: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """Adds or replaces the terms demanded for each class it names; an empty tuple removes them."""


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

    async def permitted(
        self, tenant: Tenant, data_class: str | None, process: str | None = None
    ) -> Permitted:
        """The run's port: where data of the class may be processed for the tenant, in a run
        of the process."""
        return (await self.rule(tenant)).permitted(data_class, process)

    async def demanded(self, tenant: Tenant, data_class: str | None) -> frozenset[str]:
        """The run's port `ProviderTerms`: the provider's terms a model must declare to be sent
        the tenant's data of the class (ADR-0334)."""
        return (await self.rule(tenant)).demanded(data_class)

    async def configure(self, command: ConfigureResidency, *, by: str) -> ResidencyRule:
        """Set what the command names, keep the rest. A rule that does not hold — a class wider
        than the tenant's own — is refused as a ValueError and changes nothing."""
        current = await self.rule(command.tenant)
        classes = {
            name: location
            for name, location in {**current.classes, **command.classes}.items()
            if name not in command.cleared
        }
        processes = {
            name: location
            for name, location in {**current.processes, **command.processes}.items()
            if name not in command.cleared_processes
        }
        configured = ResidencyRule.model_validate(
            {
                **current.model_dump(),
                "location": command.location or current.location,
                "classes": classes,
                "processes": processes,
                "terms": current.terms if command.terms is None else command.terms,
                "class_terms": {
                    name: terms
                    for name, terms in {**current.class_terms, **command.class_terms}.items()
                    if terms
                },
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
