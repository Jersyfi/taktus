"""A process's caps on its open work, seen from the run (ADR-0132, UC-8.12).

The process component owns a version's caps: how many of its outcomes of each kind may wait at
once, how those open outside are read, and how often a waiting run counts again. The run asks
for them before a run starts anything, and the composition root answers from the process
component, because components never import each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Value


class CountReading(Value):
    """One read operation of a connector, with a literal input, and where in its output the
    open outcomes are: a list, counted by its length, or a number."""

    operation: str = Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$")
    input: Mapping[str, Any] = Field(default_factory=dict)
    credentials: tuple[CredentialReference, ...] = ()
    select: str | None = Field(default=None, min_length=1)

    @property
    def capability(self) -> str:
        return self.operation.rsplit(".", 1)[0]


class Cap(Value):
    """The cap on one kind of a process's open outcomes."""

    kind: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    cap: int = Field(ge=1)
    reading: CountReading | None = None
    """How the outcomes open outside are read; None counts only the runs in flight."""
    check_every_seconds: float = Field(gt=0)


class OpenWork(Protocol):
    async def caps(self, tenant: Tenant, process_version: str) -> tuple[Cap, ...]:
        """The caps the version declares, in the order it declares them; none when it declares
        none or is not known."""
        ...
