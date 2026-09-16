"""What the command line needs from the composition root, as a protocol.

A driving adapter calls application services; it does not build them. The composition root
implements `Wiring` and hands it to the typer application as its context object; each command
opens the services it needs with the options the user gave. The adapter never imports a driven
adapter or the composition root (docs/architecture/project-structure.md §3).
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import Run
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, UnitOfWork


class NotOperable(Exception):
    """The services cannot be opened as configured — no database where one is named, a schema
    that is not at the current revision, a URL that is not one. The message says what to do."""


@dataclass(frozen=True)
class Services:
    register_version: RegisterProcessVersionHandler
    commission: CommissionPlanHandler
    engine: RunEngine
    runs: Repository[Run]
    ledger: Ledger
    work: UnitOfWork
    clock: Clock
    ids: Identifiers
    storage: str
    """Where the state lives, in one line for the user: the command line prints it, so that
    neither the database nor the memory implementation is a silent default."""


class Wiring(Protocol):
    def services(
        self, *, state_dir: Path, worker_endpoint: str
    ) -> AbstractAsyncContextManager[Services]:
        """Open the services against a state directory and one worker endpoint; close what
        needs closing on exit. Raises `NotOperable` when the configuration cannot be served."""
        ...
