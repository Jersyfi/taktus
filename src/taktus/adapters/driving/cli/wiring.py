"""What the command line needs from the composition root, as a protocol.

A driving adapter calls application services; it does not build them. The composition root
implements `Wiring` and hands it to the typer application as its context object; each command
opens the services it needs with the options the user gave. The adapter never imports a driven
adapter or the composition root (docs/architecture/project-structure.md §3).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from taktus.components.accounting.application.service import (
    BottlenecksHandler,
    CostOfRunHandler,
    SpendHandler,
    TaktRateHandler,
)
from taktus.components.catalog.application.service import (
    AgentCatalog,
    CatalogueShares,
    DomainInstances,
    RunConformanceHandler,
    SkillCatalog,
)
from taktus.components.catalog.domain.model import (
    Admitted,
    DomainInstance,
    InvalidSkill,
    Round,
    ShareKind,
    SkillVersion,
)
from taktus.components.catalog.domain.model.blueprint import DomainFigures
from taktus.components.catalog.domain.service.shares import Use
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.command.domain.model import PlanDraft
from taktus.components.governance.application.service import (
    AnchorsInForce,
    ConfigureAnchorsHandler,
    Corrections,
    ExpectedRuns,
    ReportCapacityHandler,
    ReportHardwareHandler,
    ResultDefects,
    Stages,
    SubjectRequests,
    TenantMessages,
    TenantOrgUnits,
    TenantResidency,
    TenantSources,
)
from taktus.components.governance.application.service.domains import (
    ConformityEvidence,
    TenantDomains,
)
from taktus.components.governance.application.service.stop_incidents import StopIncidents
from taktus.components.governance.application.service.tenant_budget import TenantBudgets
from taktus.components.governance.application.service.unit_limits import UnitLimits
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.identity.application.service.structure import OrganisationStructure
from taktus.components.knowledge.application.service import PublishGuidesHandler
from taktus.components.process.application.service.deactivate import DeactivateProcessHandler
from taktus.components.process.application.service.packages import ProcessPackages
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.application.service.takeover import TakeoverTrials
from taktus.components.process.domain.model import Evaluation, ProcessVersion
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
from taktus.ports.persistence import Repository, Tenant, TenantImported, UnitOfWork
from taktus.shared.v1 import Plan


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


@dataclass(frozen=True)
class ShippedConnector:
    """One connector the release ships, as `taktusctl conformance list` prints it by capability:
    its name, what it serves, and the image it is shipped as — None for one that runs inside
    the control plane (ADR-0158)."""

    name: str
    capabilities: tuple[str, ...]
    image: str | None


class Catalogue(Protocol):
    async def entries(self, tenant: Tenant) -> list[CatalogueEntry]:
        """Every adapter the instance is configured with, with its maturity."""
        ...

    def shipped(self) -> list[ShippedConnector]:
        """Every connector the release ships, configured here or not."""
        ...


class CatalogueIndexActs(Protocol):
    """What `taktusctl catalogue` asks of the catalogue the composition root wires (ADR-0175).
    The rows and results are the composition's; the command prints their fields."""

    async def listed(self, tenant: Tenant) -> tuple[list[Any], list[Any]]: ...

    async def install(
        self,
        tenant: Tenant,
        catalogue: str,
        entry_id: str,
        *,
        actor: str,
        adapter: str | None = None,
    ) -> Any: ...


class DomainDialogueActs(Protocol):
    """An instance worked out as a plan draft and instantiated by commissioning it
    (ADR-0289). Each act answers the instance and the draft as it now stands."""

    async def start(
        self, tenant: Tenant, admitted: Admitted, by: str, org_path: tuple[str, ...]
    ) -> tuple[DomainInstance, PlanDraft]: ...

    async def answer(
        self,
        tenant: Tenant,
        admitted: Admitted,
        instance_id: str,
        capability: str,
        adapter: str | None,
        by: str,
    ) -> tuple[DomainInstance, PlanDraft]: ...

    async def leave_out(
        self,
        tenant: Tenant,
        admitted: Admitted,
        instance_id: str,
        processes: Iterable[str],
        by: str,
    ) -> tuple[DomainInstance, PlanDraft]: ...

    async def name_owner(
        self, tenant: Tenant, admitted: Admitted, instance_id: str, owner: str, by: str
    ) -> tuple[DomainInstance, PlanDraft]: ...

    async def name_jurisdiction(
        self, tenant: Tenant, admitted: Admitted, instance_id: str, jurisdiction: str, by: str
    ) -> tuple[DomainInstance, PlanDraft]: ...

    async def due(self, tenant: Tenant, instance_id: str, due: datetime, by: str) -> PlanDraft: ...

    async def draft(self, tenant: Tenant, instance: DomainInstance) -> PlanDraft: ...

    async def commission(
        self, tenant: Tenant, admitted: Admitted, instance_id: str, by: str
    ) -> tuple[DomainInstance, Plan]: ...


class DomainActs(Protocol):
    """What `taktusctl domain` asks of the domain blueprints the composition root wires
    (ADR-0263): a blueprint's directory read and admitted, exported, and its instances, worked
    out in a plan where the dialogue is wired (ADR-0289)."""

    @property
    def instances(self) -> DomainInstances: ...

    @property
    def dialogue(self) -> DomainDialogueActs | None: ...

    def read(self, directory: Path) -> Any: ...

    def admitted(self, directory: Path) -> Admitted: ...

    def export(self, directory: Path, target: Path) -> list[Path]: ...

    async def figures(self, tenant: Tenant, instance: DomainInstance) -> DomainFigures: ...


class CatalogueAuthor(Protocol):
    """What an author signs an index with (`taktusctl catalogue sign`, `key`). The seed is
    read from a file by the command and never printed."""

    def key(self, seed: bytes) -> str: ...

    def sign(self, index: Path, seed: bytes) -> list[str]: ...


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
    spend: SpendHandler | None = None
    """Where a run or a process spent, per step, and two runs side by side (#449)."""
    takt_rate: TaktRateHandler | None = None
    """A tenant's Takt consumption and rate over the window of the table in force
    (`taktusctl cost` without a run)."""
    bottlenecks: BottlenecksHandler | None = None
    """What a higher limit would have bought, the recommendations, the waits on people by role
    or department, and the ways to wait less on them (`taktusctl bottlenecks`, ADR-0283)."""
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
    catalogue_index: CatalogueIndexActs | None = None
    """The catalogue's entries, verified and installed (`taktusctl catalogue`, ADR-0175)."""
    domains: DomainActs | None = None
    """Domain blueprints admitted, instantiated in dialogue and exported (`taktusctl domain`,
    ADR-0263)."""
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
    defects: ResultDefects | None = None
    """A result reported wrong, bounded, decided on by rule and planned for (`taktusctl
    defect`, ADR-0153)."""
    residency: TenantResidency | None = None
    """The tenant's residency rule, shown and set (`taktusctl residency`, ADR-0116)."""
    budget: TenantBudgets | None = None
    """The tenant's monthly budget across all its runs (`taktusctl budget`, ADR-0260)."""
    sources: TenantSources | None = None
    """The tenant's declaration of its sources, shown and changed (`taktusctl sources`,
    ADR-0130)."""
    messages: TenantMessages | None = None
    """The tenant's rules for outward messages and the cases a person answered in
    (`taktusctl messages`, `taktusctl case`, ADR-0142)."""
    org_units: TenantOrgUnits | None = None
    """The tenant's quotas per organisational unit, shown and set (`taktusctl units`,
    ADR-0166)."""
    structure: OrganisationStructure | None = None
    """The organisation's structure and its projects, shown and shaped (`taktusctl
    structure`, ADR-0275, ADR-0276)."""
    unit_limits: UnitLimits | None = None
    """The tenant's limits per unit of its structure, set, shown and watched (`taktusctl units
    limit`, ADR-0282)."""
    deadlines: DeadlineKeeper | None = None
    """The tenant's open deadlines and its working time (`taktusctl deadline`, ADR-0133)."""
    stops: Stops | None = None
    """The tenant's stops of adapters, requested, shown and lifted (`taktusctl stop`,
    ADR-0138)."""
    stop_incidents: StopIncidents | None = None
    """The incidents and situation packages of the stops a person requested (`taktusctl
    incident package`, ADR-0280)."""
    tenant_domains: TenantDomains | None = None
    """The tenant's domains, their owners, their duties and the conformity evidence of their
    catalogue (`taktusctl domain`, ADR-0259, ADR-0280)."""
    conformity: ConformityEvidence | None = None
    """The conformity evidence of the tenant's domains (`taktusctl domain evidence`,
    ADR-0280 §4)."""
    traces: StepTraces | None = None
    """How long the tenant keeps the trace inside a step, shown and set (`taktusctl trace`,
    ADR-0135)."""
    stages: Stages | None = None
    """The tenant's introduction in stages: declared, shown and opened by a person
    (`taktusctl stage`, ADR-0137)."""
    skills: SkillActs | None = None
    """The skill lifecycle: registered, evaluated, approved and shown (`taktusctl skill`,
    ADR-0162)."""
    subjects: SubjectRequests | None = None
    """Data-protection requests, prepared, carried out by a person and withdrawn
    (`taktusctl subject`, ADR-0176)."""
    evidence: Evidence | None = None
    """The evidence of what is processed, generated from configuration and the ledger
    (`taktusctl evidence`, ADR-0176)."""
    agents: AgentActs | None = None
    """Shared agents with role profiles: called, their core evaluated (`taktusctl agent`,
    ADR-0163)."""
    instructions: TakeoverTrials | None = None
    """A process's takeover instructions shown, and a trial of them recorded
    (`taktusctl takeover`, ADR-0180)."""
    packages: ProcessPackages | None = None
    """A process version exported as one package of plain files (`taktusctl process export`,
    ADR-0285)."""
    exports: TenantExportActs | None = None
    """A tenant exported, and an export imported and checked (`taktusctl tenant export` and
    `import`, ADR-0221); None where the state is files."""
    shares: CatalogueShares | None = None
    """Entries of the catalogue shared with circles, withdrawn, and the callers' own
    credentials bound (`taktusctl catalogue share`, ADR-0246, ADR-0247)."""
    catalogue_use: CatalogueUseActs | None = None
    """An entry's use per organisational unit and the viewer's own (`taktusctl catalogue use`,
    ADR-0246 §6)."""
    planning: AdministrativePlanning | None = None
    """The plan dialogue, for an update of Taktus prepared and commissioned as a plan
    (`taktusctl update`, ADR-0296); None where the wiring has none."""


class AdministrativePlanning(Protocol):
    """The plan dialogue as `taktusctl update` uses it (ADR-0237, ADR-0296)."""

    async def open(
        self,
        tenant: Tenant,
        identity: str,
        org_path: tuple[str, ...],
        said: str,
        *,
        act: str | None = None,
        arguments: Mapping[str, Any] | None = None,
    ) -> PlanDraft: ...

    async def set(
        self, tenant: Tenant, identity: str, draft_id: str, fields: Mapping[str, Any]
    ) -> PlanDraft: ...

    async def commission(self, tenant: Tenant, identity: str, draft_id: str) -> Plan: ...


class CatalogueUseActs(Protocol):
    async def of(self, tenant: Tenant, kind: ShareKind, subject: str, viewer: str) -> Use:
        """An entry's calls per organisational unit, and the viewer's own (ADR-0246 §6)."""
        ...


class TenantExportActs(Protocol):
    async def export(self, tenant: Tenant, *, by: str) -> bytes:
        """The tenant's export document."""
        ...

    async def import_(self, content: bytes, *, by: str) -> TenantImported:
        """An export written into this instance, its chains checked here."""
        ...


class Evidence(Protocol):
    async def evidence(self, tenant: Tenant) -> dict[str, Any]:
        """What is processed for the tenant, where, by which adapter and kept how long, as
        one JSON document (ADR-0176 §8)."""
        ...


class SkillActs(Protocol):
    """What `taktusctl skill` asks of the skill lifecycle the composition root wires."""

    @property
    def catalog(self) -> SkillCatalog: ...

    async def register_directory(
        self, tenant: str, root: Path, version: str, by: str | None = None
    ) -> tuple[list[SkillVersion], list[tuple[Path, InvalidSkill]]]: ...

    async def start_round(self, tenant: str, skill_id: str, key: str | None = None) -> Round: ...

    async def approve(self, tenant: str, skill_id: str, by: str | None) -> SkillVersion: ...

    async def produce(self, tenant: str, skill_id: str, by: str | None = None) -> SkillVersion: ...

    async def takeover(self, tenant: str, process_id: str) -> list[dict[str, Any]]: ...

    async def look(self, tenant: str) -> None: ...


class AgentActs(Protocol):
    """What `taktusctl agent` asks of the shared agents the composition root wires."""

    @property
    def catalog(self) -> AgentCatalog: ...

    async def call(
        self,
        tenant: str,
        agent: str,
        *,
        identity: str,
        inputs: Mapping[str, Any] | None = None,
        role: str | None = None,
    ) -> Run: ...

    async def evaluate_core(self, tenant: str, core_id: str) -> list[Evaluation]: ...

    async def advance_core(self, tenant: str, core_id: str) -> list[str]: ...

    async def usage(self, tenant: str, agent: str) -> list[dict[str, Any]]: ...


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

    def hardware(self) -> ReportHardwareHandler:
        """The hardware report: the machine this process runs on and every configured model
        with its declared needs (ADR-0284). No state, no database. Raises `NotOperable` when
        the models' configuration cannot be read."""
        ...

    def catalogue_author(self) -> CatalogueAuthor:
        """What an author signs a catalogue's index with: no state, no database."""
        ...

    def guides(self, *, directory: Path) -> AbstractAsyncContextManager[GuidesServices]:
        """Open the publishing of the guides into a directory of files, the knowledge system
        of an organisation that has none (UC-13.6). No state, no database: the directory is
        the record."""
        ...
