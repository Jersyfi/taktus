"""The execution port's adapters (ADR-0002): `process` starts a unit on this machine with no
isolation; `container` starts one per job in a container with limits, a memory-backed
credential store and a network that reaches the allowed hosts and nothing else; `kubernetes`
starts one per job as a Job in a cluster's execution namespace, with limits, credentials from a
Secret that lives as long as the job, and an egress proxy of its own."""

from taktus.adapters.driven.execution.container import ContainerExecution
from taktus.adapters.driven.execution.kubernetes import KubernetesExecution
from taktus.adapters.driven.execution.process import ProcessExecution

__all__ = ["ContainerExecution", "KubernetesExecution", "ProcessExecution"]
