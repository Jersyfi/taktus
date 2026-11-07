"""Ports this component needs beyond the cross-cutting ones."""

from taktus.components.governance.ports.corrections import OpenCorrections
from taktus.components.governance.ports.stages import (
    Identities,
    ProcessLevels,
    RunningLevel,
    StageReports,
    TakeoverInstructions,
)
from taktus.components.governance.ports.subjects import SubjectHoldings

__all__ = [
    "Identities",
    "OpenCorrections",
    "ProcessLevels",
    "RunningLevel",
    "StageReports",
    "SubjectHoldings",
    "TakeoverInstructions",
]
