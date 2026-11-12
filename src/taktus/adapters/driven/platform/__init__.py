"""The platform port's adapters: `host` observes the machine or container this instance runs
on. An adapter for a cluster — what a node or a namespace's quota has left — is added without
touching the port (docs/architecture/platform.md). `hardware` is the hardware port's: what the
machine is — its processors, memory and accelerators (ADR-0284)."""

from taktus.adapters.driven.platform.hardware import HostHardware
from taktus.adapters.driven.platform.host import ADAPTER, HostPlatform

__all__ = ["ADAPTER", "HostHardware", "HostPlatform"]
