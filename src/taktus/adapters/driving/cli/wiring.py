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

from taktus.components.accounting.application.service import CostOfRunHandler, TaktRateHandler
from taktus.components.catalog.application.service import RunConformanceHandler
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.governance.application.service import (
    AnchorsInForce,
    ConfigureAnchorsHandler,
    Corrections,
    ExpectedRuns,
    ReportCapacityHandler,
    TenantResidency,
    TenantSources,
)
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.knowledge.application.service import PublishGuidesHandler
from taktus.components.process.application.service.deactivate import DeactivateProcessHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.reporting.application.service import (
    Alerts,
    BrokenInterfaces,
    ChannelOf,
    ConfigureChannelHandler,
    Corridors,
    ProductFindings,
    SignalWatch,
    StepTraces,
)
from taktus.components.run.application.query import ProvenanceQuery, StepMeasures
from taktus.components.run.application.service import (
    CorrectResultHandler,
    ProposeMovesHandler,
    ReviewMovesHandler,
    RunEngine,
)
from taktus.components.run.application.service.deadlines import DeadlineKeeper
from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import Run
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class NotOperable(Exception):
    """The services cannot be opened as configured — no database where one is named, a schema
    that is not at the current revision, a URL that is not one. The message says what to do."""


class Moves(Protocol):
    """A proposal to move a step to a trained model applied once a person accepted it, and a
    move rolled back (ADR-0114). Both raise `MoveError` naming why not."""

    async def apply(self, tenant: Tenant, request_id: str) -> ProcessVersion: ...

    async def rollback(self, tenant: Tenant, process_id: str, *, by: str) -> ProcessVersion: ...


@dataclass(frozen=True)
class CatalogueEntry:
    """One configured adapter as `taktusctl conformance list` prints it."""

    adapter: str
    family: str
    maturity: str | None
    """`experimental`, `verified` or `reference`; None for an adapter that is no integration."""
    missing: tuple[str, ...]
    serves: tuple[str, ...]
    vendor_server: bool = False
    """A connector that serves a vendor's MCP server (ADR-0117)."""
    manifest: str | None = None
    """The digest of the manifest it serves the vendor's server under; None without one."""


class Catalogue(Protocol):
    async def entries(self, tenant: Tenant) -> list[CatalogueEntry]:
        """Every adapter the instance is configured with, with its maturity."""
        ...


@dataclass(frozen=True)
class Services:
    identities: IdentityDirectory
    """The identity component: the identity an invocation names must be one it knows, and the
    administrative acts on identities and links go through it (ADR-0040)."""
    tenants: TenantRegistry
    """The instance's registry of tenants: created, renamed and listed by an administrator
    (`taktusctl tenant`, ADR-0104)."""
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
    takt_rate: TaktRateHandler | None = None
    """A tenant's Takt consumption and rate over the window of the table in force
    (`taktusctl cost` without a run)."""
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
    alerts: Alerts | None = None
    """What needs a person's action, noticed from recorded facts, and what became of its
    reports, to show its operator (`taktusctl alerts`, ADR-0106)."""
    conformance: RunConformanceHandler | None = None
    """The instance runs an adapter's conformance suite and records it (`taktusctl
    conformance record`, ADR-0044)."""
    catalogue: Catalogue | None = None
    """Every configured adapter with its maturity (`taktusctl conformance list`, ADR-0117)."""
    deactivate: DeactivateProcessHandler | None = None
    """A process is switched off: its triggers no longer start runs (`taktusctl deactivate`)."""
    measures: StepMeasures | None = None
    """Every step's measures, at the instance's price table (`taktusctl maturation measures`,
    ADR-0084)."""
    correct_result: CorrectResultHandler | None = None
    """A person's correction of a step's result, recorded (`taktusctl maturation correct`)."""
    propose_moves: ProposeMovesHandler | None = None
    """Proposals to move a step to a trained model, on evidence, through the instance's
    decision port (`taktusctl maturation propose`)."""
    moves: Moves | None = None
    """An accepted proposal applied, and a move rolled back (`taktusctl maturation apply`,
    `rollback`, ADR-0114)."""
    review_moves: ReviewMovesHandler | None = None
    """Every move measured over its first cases (`taktusctl maturation moves`)."""
    expected_runs: ExpectedRuns | None = None
    """The incidents the watch over expected runs raised, closed by a person, and the
    tenant's watch configuration (`taktusctl incident`, ADR-0107)."""
    corridors: Corridors | None = None
    """The tenant's corridors, configured by a person (`taktusctl signal configure`,
    ADR-0109)."""
    signals: SignalWatch | None = None
    """Every signal judged against its corridor now (`taktusctl signal list`)."""
    corrections: Corrections | None = None
    """The decisions on proposals counted per process and action class, and the tenant's
    correction limits (`taktusctl corrections`, ADR-0110)."""
    residency: TenantResidency | None = None
    """The tenant's residency rule, shown and set (`taktusctl residency`, ADR-0116)."""
    sources: TenantSources | None = None
    """The tenant's declaration of its sources, shown and changed (`taktusctl sources`,
    ADR-0130)."""
    deadlines: DeadlineKeeper | None = None
    """The tenant's open deadlines and its working time (`taktusctl deadline`, ADR-0133)."""
    stops: Stops | None = None
    """The tenant's stops of adapters, requested, shown and lifted (`taktusctl stop`,
    ADR-0138)."""
    traces: StepTraces | None = None
    """How long the tenant keeps the trace inside a step, shown and set (`taktusctl trace`,
    ADR-0135)."""


@dataclass(frozen=True)
class CapacityServices:
    """What `taktusctl capacity` needs: the report, and what it is asked about."""

    report: ReportCapacityHandler
    tenants: tuple[str, ...]
    """The tenants the instance serves, read from its registry (ADR-0104): their runs are
    counted."""
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
