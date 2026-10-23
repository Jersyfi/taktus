"""Ports this component needs beyond the cross-cutting ones."""

from taktus.components.governance.ports.stages import (
    Identities,
    ProcessLevels,
    RunningLevel,
    StageReports,
    TakeoverInstructions,
)

__all__ = [
    "Identities",
    "ProcessLevels",
    "RunningLevel",
    "StageReports",
    "TakeoverInstructions",
]
