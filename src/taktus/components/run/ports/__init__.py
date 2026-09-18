"""Ports this component needs beyond the cross-cutting ones."""

from taktus.components.run.ports.connectors import ConnectorPool
from taktus.components.run.ports.models import ModelPool
from taktus.components.run.ports.workers import WorkerPool

__all__ = ["ConnectorPool", "ModelPool", "WorkerPool"]
