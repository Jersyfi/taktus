"""Use case: look at the machine, and say for each configured model what it needs and whether
this machine has it (ADR-0284, UC-10.1).

The inventory comes from the hardware port; the models and their declared needs from
configuration, handed in by the composition root. Nothing is recorded and nothing changes:
the report is read by a person or by an install script (`taktusctl hardware`).
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.governance.domain.model.hardware import HardwareReport
from taktus.components.governance.domain.service.hardware import fit
from taktus.ports.hardware import Hardware, HardwareNeeds


@dataclass(frozen=True)
class ConfiguredModel:
    """One model as configured: its adapter identifier, where it runs, what it needs."""

    model: str
    location: str
    needs: HardwareNeeds


class ReportHardwareHandler:
    def __init__(self, hardware: Hardware, models: tuple[ConfiguredModel, ...]) -> None:
        self._hardware = hardware
        self._models = models

    async def execute(self) -> HardwareReport:
        inventory = await self._hardware.inventory()
        return HardwareReport(
            adapter=self._hardware.adapter,
            inventory=inventory,
            models=tuple(fit(m.model, m.location, m.needs, inventory) for m in self._models),
        )
