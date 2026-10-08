"""The cluster execution adapter (`adapter.py`) and the part of the cluster's API it uses
(`api.py`): one Job per execution unit in the execution namespace, an egress proxy of its own
per job, and nothing it cannot delete again (deploy/k8s/README.md §7)."""

from taktus.adapters.driven.execution.kubernetes.adapter import KubernetesExecution
from taktus.adapters.driven.execution.kubernetes.api import PERMITTED, ClusterApi, Connection

__all__ = ["PERMITTED", "ClusterApi", "Connection", "KubernetesExecution"]
