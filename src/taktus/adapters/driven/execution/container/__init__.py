"""The container execution adapter and what it puts beside every job: `egress.py`, the
job's only way in and out, and `launch.sh`, the launcher that receives the credentials."""

from taktus.adapters.driven.execution.container.adapter import ContainerExecution

__all__ = ["ContainerExecution"]
