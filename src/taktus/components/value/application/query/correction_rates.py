"""The measured correction rate of a process version, read from the value ledger's projection
(UC-6.9 §3, ADR-0226). A view and a report read it here and never compute it themselves
(ADR-0029)."""

from __future__ import annotations

from collections.abc import Iterable

from taktus.components.value.domain.service.corrections import CORRECTIONS, Measured, measured
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, UnitOfWork


class CorrectionRates:
    def __init__(self, ledger: Ledger, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._work = work

    async def of(self, tenant: Tenant, process_version: str, checked: Iterable[str]) -> Measured:
        """How many results of the steps in `checked` counted, and how many of them a person
        corrected after the checks passed."""
        async with self._work.transaction(tenant):
            state = await self._ledger.project(tenant, CORRECTIONS)
        return measured(state, process_version, checked)
