"""The hardware report, wired from the settings (ADR-0284): the machine this process runs on, and
every configured model with what it declares it needs. `taktusctl hardware` uses it; it needs
no state and no database."""

from __future__ import annotations

from taktus.adapters.driven.platform import HostHardware
from taktus.components.governance.application.service import (
    ConfiguredModel,
    ReportHardwareHandler,
)
from taktus.composition.settings import ModelSettings
from taktus.ports.clock import Clock
from taktus.ports.hardware import Hardware


def hardware_report(
    models: tuple[ModelSettings, ...], *, clock: Clock, hardware: Hardware | None = None
) -> ReportHardwareHandler:
    return ReportHardwareHandler(
        hardware or HostHardware(clock),
        tuple(ConfiguredModel(m.identifier, m.location, m.needs) for m in models),
    )
