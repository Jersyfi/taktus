"""Ports this component needs beyond the cross-cutting ones."""

from taktus.components.process.ports.domains import DomainOwners
from taktus.components.process.ports.levels import LoweredLevels, LoweredVersions
from taktus.components.process.ports.residency import ResidencyBindings
from taktus.components.process.ports.rights import ProcessRights
from taktus.components.process.ports.sources import FreeSources
from taktus.components.process.ports.stages import StageCeiling, StageCeilings
from taktus.components.process.ports.structure import RoleStructure

__all__ = [
    "DomainOwners",
    "FreeSources",
    "LoweredLevels",
    "LoweredVersions",
    "ProcessRights",
    "ResidencyBindings",
    "RoleStructure",
    "StageCeiling",
    "StageCeilings",
]
