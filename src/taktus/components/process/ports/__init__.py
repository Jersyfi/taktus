"""Ports this component needs beyond the cross-cutting ones."""

from taktus.components.process.ports.levels import LoweredLevels, LoweredVersions
from taktus.components.process.ports.sources import FreeSources

__all__ = ["FreeSources", "LoweredLevels", "LoweredVersions"]
