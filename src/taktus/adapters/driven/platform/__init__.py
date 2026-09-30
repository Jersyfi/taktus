"""The platform port's adapters: `host` observes the machine or container this instance runs
on. An adapter for a cluster — what a node or a namespace's quota has left — is added without
touching the port (docs/architecture/platform.md)."""

from taktus.adapters.driven.platform.host import ADAPTER, HostPlatform

__all__ = ["ADAPTER", "HostPlatform"]
