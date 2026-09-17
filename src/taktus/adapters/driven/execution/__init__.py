"""The execution port's adapters (ADR-0002): `process` starts a unit on this machine with no
isolation; `container` starts one per job in a container with limits, a memory-backed
credential store and a network that reaches the allowed hosts and nothing else. A third
adapter for a cluster is added without touching the port."""

from taktus.adapters.driven.execution.container import ContainerExecution
from taktus.adapters.driven.execution.process import ProcessExecution

__all__ = ["ContainerExecution", "ProcessExecution"]
