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

from taktus.components.accounting.application.service import CostOfRunHandler
from taktus.components.catalog.application.service import RunConformanceHandler
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.governance.application.service import (
    AnchorsInForce,
    ConfigureAnchorsHandler,
    ReportCapacityHandler,
)
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.knowledge.application.service import PublishGuidesHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.reporting.application.service import (
    BrokenInterfaces,
    ChannelOf,
    ConfigureChannelHandler,
    ProductFindings,
)
from taktus.components.run.application.query import ProvenanceQuery
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
    identities: IdentityDirectory
    """The identity component: the identity an invocation names must be one it knows, and the
    administrative acts on identities and links go through it (ADR-0040)."""
    register_version: RegisterProcessVersionHandler
    commission: CommissionPlanHandler
    engine: RunEngine
    provenance: ProvenanceQuery
    runs: Repository[Run]
    ledger: Ledger
    work: UnitOfWork
    clock: Clock
    ids: Identifiers
    storage: str
    """Where the state lives, in one line for the user: the command line prints it, so that
    neither the database nor the memory implementation is a silent default."""
    queued: bool = False
    """Whether `engine.submit` has a queue a daemon claims from: true with a database, where
    `taktusd` runs; false in memory, where nothing else executes."""
    cost: CostOfRunHandler | None = None
    """What a run cost, recomputed from the ledger at its price table (`taktusctl cost`)."""
    configure_anchors: ConfigureAnchorsHandler | None = None
    """A tenant's anchors, configured (`taktusctl anchors set`, ADR-0042)."""
    anchors: AnchorsInForce | None = None
    """The anchors a tenant holds now (`taktusctl anchors show`)."""
    configure_owner_channel: ConfigureChannelHandler | None = None
    """A tenant's owner-facing channel, configured (`taktusctl owner-channel set`,
    ADR-0045)."""
    owner_channel: ChannelOf | None = None
    """The owner-facing channel a tenant configured (`taktusctl owner-channel show`)."""
    findings: ProductFindings | None = None
    """The product findings the instance recorded, to show its operator (`taktusctl findings`,
    UC-6.12)."""
    interfaces: BrokenInterfaces | None = None
    """The broken interfaces the instance noticed from its own calls, and what became of their
    reports, to show its operator (`taktusctl interfaces`, ADR-0047)."""
    conformance: RunConformanceHandler | None = None
    """The instance runs an adapter's conformance suite and records it (`taktusctl
    conformance record`, ADR-0044)."""


@dataclass(frozen=True)
class CapacityServices:
    """What `taktusctl capacity` needs: the report, and what it is asked about."""

    report: ReportCapacityHandler
    tenants: tuple[str, ...]
    """The tenants the instance serves (`TAKTUS_TENANTS`): their runs are counted."""
    job_memory_bytes: int | None
    """The memory limit of the unit a worker step starts on this platform, if any."""


@dataclass(frozen=True)
class GuidesServices:
    """What `taktusctl guides publish` needs: the guides put into a knowledge system."""

    publish: PublishGuidesHandler


class Wiring(Protocol):
    def services(
        self, *, state_dir: Path, worker_endpoint: str
    ) -> AbstractAsyncContextManager[Services]:
        """Open the services against a state directory and one worker endpoint; close what
        needs closing on exit. Raises `NotOperable` when the configuration cannot be served."""
        ...

    def capacity(self, *, state_dir: Path) -> AbstractAsyncContextManager[CapacityServices]:
        """Open the capacity report against the state where it is configured — no worker, no
        connector: looking at the platform starts nothing. Raises `NotOperable` as
        `services` does."""
        ...

    def guides(self, *, directory: Path) -> AbstractAsyncContextManager[GuidesServices]:
        """Open the publishing of the guides into a directory of files, the knowledge system
        of an organisation that has none (UC-13.6). No state, no database: the directory is
        the record."""
        ...
