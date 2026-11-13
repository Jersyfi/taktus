"""What the HTTP surface needs from the composition root, as a protocol.

A driving adapter calls application services and never builds them (docs/architecture/
project-structure.md §3). The composition root implements this and hands it to `build_app`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

from taktus.components.accounting.application.service import (
    NamedCase,
    Offer,
    SpendHandler,
    Trial,
    TrialRead,
)
from taktus.components.command.application.service import (
    CompleteIntakeHandler,
    ReceiveIntakeHandler,
)
from taktus.components.command.application.service.coach import Coach
from taktus.components.command.application.service.sessions import Sessions
from taktus.components.command.domain.model import PlanDraft
from taktus.components.command.domain.service.guided import Mode
from taktus.components.decision.application.query import DecisionQueries
from taktus.components.decision.application.service import (
    AnswerRequestHandler,
    ConfirmRequestHandler,
)
from taktus.components.governance.application.service import (
    Confirmed,
    ConnectionGrants,
    Corrections,
    PrepareRequest,
    Stages,
    TenantOrgUnits,
)
from taktus.components.governance.domain.model import Incident, SubjectRequest
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.identity.application.service.structure import OrganisationStructure
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.streams import DeclareStream
from taktus.components.process.application.service.takeover import RecordTrial
from taktus.components.process.domain.model import (
    CorrectedCase,
    Evaluation,
    ProcessVersion,
    Proposal,
    TakeoverTrial,
    ValueStream,
)
from taktus.components.process.domain.service.proposing import ProcessProposal
from taktus.components.reporting.application.query import LevelQueries, ReportQueries
from taktus.components.reporting.application.service import (
    Alerted,
    AnswerInChannelHandler,
    BackupWatched,
    FindingsIntake,
    ProductFindings,
    StepQueries,
    StepTraces,
)
from taktus.components.reporting.domain.model import (
    Change,
    Corridor,
    Judged,
    Reader,
    Scope,
    Snapshot,
)
from taktus.components.reporting.domain.model.acting import (
    Register,
    RemoveView,
    ResidencyView,
    WrongResultView,
)
from taktus.components.reporting.domain.model.live import Reader as LiveReader
from taktus.components.reporting.domain.model.views import (
    OwnView,
    ReportDefinition,
    Shown,
    ViewConfiguration,
)
from taktus.components.reporting.domain.service.catalogue import Catalogue
from taktus.components.reporting.domain.service.explaining import Explanation
from taktus.components.reporting.domain.service.own import OwnRelief
from taktus.components.reporting.domain.service.profiles import RoleIndex, RoleProfile
from taktus.components.reporting.domain.service.reports import Composed
from taktus.components.reporting.domain.service.streams import StreamLanes, StreamMap
from taktus.components.reporting.domain.service.variants import VariantsView
from taktus.components.run.application.service import HandBack, SteerStep, TakeOver
from taktus.components.run.domain.model import Run
from taktus.components.value.application.service import Discoveries, ValueBases
from taktus.components.value.domain.model import Figure, ValueProposal
from taktus.components.value.domain.service.figures import Facts as ValueFacts
from taktus.components.value.domain.service.figures import Index
from taktus.ports.clock import Clock
from taktus.ports.configuration import Secret
from taktus.ports.identity import Resolution
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Queried, Tenant, TenantImported, UnitOfWork
from taktus.shared.v1 import Plan


class StreamsFull(Exception):
    """The replica holds its maximum of open streams; the reader tries again, possibly on
    another replica (ADR-0055 §7)."""

    def __init__(self, maximum: int) -> None:
        super().__init__(f"this replica holds its maximum of {maximum} open streams")


class ChangeStreams(Protocol):
    """The streams of changes this replica holds (ADR-0055)."""

    async def open(
        self,
        reader: Reader,
        scope: Scope,
        position: str | None,
        authenticate: Callable[[], Awaitable[Reader | None]],
    ) -> AsyncIterator[Snapshot | Change | None]:
        """The stream: its snapshot or what the reader missed, then every change as it
        happens; None is a heartbeat. `authenticate` is asked again before every batch and
        every heartbeat; when it answers None the stream ends. `StreamsFull` when the replica
        holds its maximum."""
        ...


class ProposalActs(Protocol):
    """A proposal rehearsed and commissioned, and a process rolled back (ADR-0091 §3 to §5): the
    composition root's, because each act crosses the process, command and run components."""

    async def ask(self, tenant: Tenant, process_id: str, request: str, by: str) -> Run: ...

    async def rehearse(
        self,
        tenant: Tenant,
        process_id: str,
        proposal_id: str,
        by: str,
        inputs: Mapping[str, Any] | None = None,
    ) -> tuple[Proposal, Run]: ...

    async def commission(
        self,
        tenant: Tenant,
        process_id: str,
        proposal_id: str,
        by: str,
        approved_by: str | None = None,
        override: str | None = None,
    ) -> ProcessVersion: ...

    async def rollback(
        self,
        tenant: Tenant,
        process_id: str,
        to_version: str,
        by: str,
        as_version: str | None = None,
        approved_by: str | None = None,
    ) -> ProcessVersion: ...


class PlanActs(Protocol):
    """The plan dialogue as the surfaces present it, in either mode (ADR-0237, ADR-0238,
    ADR-0279): the composition root's, because a guided answer that chooses a process takes
    its steps from the process component."""

    async def open(
        self,
        tenant: Tenant,
        identity: str,
        org_path: tuple[str, ...],
        said: str,
        *,
        agent: bool = False,
        describes: str | None = None,
        act: str | None = None,
        arguments: Mapping[str, Any] | None = None,
    ) -> PlanDraft: ...

    async def mine(self, tenant: Tenant, identity: str) -> list[PlanDraft]: ...

    async def get(self, tenant: Tenant, identity: str, draft_id: str) -> PlanDraft: ...

    async def answer(
        self,
        tenant: Tenant,
        identity: str,
        draft_id: str,
        field: str,
        value: Any,
        *,
        step_id: str | None = None,
    ) -> PlanDraft: ...

    async def set(
        self, tenant: Tenant, identity: str, draft_id: str, fields: Mapping[str, Any]
    ) -> PlanDraft: ...

    async def commission(self, tenant: Tenant, identity: str, draft_id: str) -> Plan: ...

    async def commission_and_start(
        self, tenant: Tenant, identity: str, draft_id: str
    ) -> tuple[Plan, Run | None]: ...

    async def templates(self, tenant: Tenant) -> list[dict[str, Any]]: ...

    def view(self, draft: PlanDraft, mode: Mode) -> dict[str, Any]: ...


class GalleryActs(Protocol):
    """The gallery a person chooses a first process from (ADR-0136): the composition root's,
    because it reads the gallery's files and acts on the process component."""

    def listed(self) -> list[dict[str, Any]]:
        """Every gallery blueprint, with its processes as the gallery offers them."""
        ...

    async def propose(
        self,
        tenant: Tenant,
        blueprint_id: str,
        process_id: str,
        choices: Mapping[str, Any],
        by: str,
    ) -> Proposal:
        """The chosen process as a proposal. ProposalError `unknown` for one the gallery does
        not hold; InvalidProcess with every finding where it is refused."""
        ...


class EvaluationActs(Protocol):
    """A process's evaluations and the cases proposed from corrections (ADR-0134): the
    composition root's, because an evaluation crosses the process, command, run and governance
    components."""

    async def get(self, tenant: Tenant, process_id: str, evaluation_id: str) -> Evaluation: ...

    async def of_process(self, tenant: Tenant, process_id: str) -> list[Evaluation]: ...

    async def cases_of(self, tenant: Tenant, process_id: str) -> list[CorrectedCase]: ...

    async def confirm(
        self, tenant: Tenant, process_id: str, case_id: str, by: str, target: Any = None
    ) -> CorrectedCase: ...

    async def reject(
        self, tenant: Tenant, process_id: str, case_id: str, by: str
    ) -> CorrectedCase: ...


class TrialActs(Protocol):
    """A model tried on fixed cases (ADR-0149): the composition root's, because a trial crosses
    the process, command, run and accounting components."""

    async def start(
        self,
        tenant: Tenant,
        purpose: str,
        candidates: Sequence[str],
        by: str,
        occasion: str = "asked",
        own: Sequence[NamedCase] = (),
    ) -> Trial: ...

    async def of_tenant(self, tenant: Tenant) -> list[Trial]: ...

    async def read(self, tenant: Tenant, trial_id: str) -> TrialRead: ...

    async def offers(self, tenant: Tenant) -> list[Offer]: ...

    async def decline(
        self, tenant: Tenant, purpose: str, occasion: str, model: str, by: str, reason: str
    ) -> None: ...


class Takeovers(Protocol):
    """A running step taken over and handed back (ADR-0128): the run engine's."""

    async def take_over(self, command: TakeOver) -> str:
        """Asks the take-over; its identifier."""
        ...

    async def takeover_state(self, tenant: Tenant, run_id: str, takeover: str) -> Any:
        """The state the step was taken over in, once the take-over is served."""
        ...

    async def hand_back(self, command: HandBack) -> Run:
        """The person's result, written under the take-over's claim."""
        ...

    async def steer(self, command: SteerStep) -> str:
        """A person's message to a running step, asked on the run's job; its identifier
        (ADR-0156)."""
        ...


class InstructionActs(Protocol):
    """A process's takeover instructions and the trials of them (ADR-0180)."""

    async def read(self, tenant: Tenant, process_id: str) -> dict[str, Any] | None: ...

    async def record(self, command: RecordTrial) -> TakeoverTrial: ...

    async def of_step(
        self, tenant: Tenant, process_version: str, step_id: str
    ) -> dict[str, Any] | None: ...


class ProcessProposalRefused(Exception):
    """A proposal of a process that is not the person's to decide, or is decided already, or
    that no request path on this instance can build (ADR-0270 §5)."""


class NoRequestPath(ProcessProposalRefused):
    """Accepting is refused: no request path builds a process on this instance (ADR-0251)."""


class AcceptedProposal(Protocol):
    @property
    def proposal(self) -> ProcessProposal: ...

    @property
    def run(self) -> Run:
        """The run that builds the proposal of a version (UC-4.1)."""
        ...


class ProcessProposalActs(Protocol):
    """The processes Taktus proposes to a person, and each accepted or declined on its own
    (UC-4.4, ADR-0270): the composition root's, because the list reads the run component's
    records and accepting crosses the command and run components."""

    async def listed(self, tenant: Tenant, viewer: str) -> list[ProcessProposal]:
        """What `viewer` is shown, most often recurring first, none decided already."""
        ...

    async def accept(self, tenant: Tenant, proposal_id: str, by: str) -> AcceptedProposal:
        """`ProcessProposalRefused` when it is not `by`'s to decide."""
        ...

    async def decline(self, tenant: Tenant, proposal_id: str, by: str) -> ProcessProposal:
        """`ProcessProposalRefused` when it is not `by`'s to decide."""
        ...


class StartRefused(Exception):
    """A process was not started from the MCP surface; the message says why, in one sentence
    the person's agent can act on (ADR-0131 §5)."""


class AgentActs(Protocol):
    """What the MCP surface needs beyond the HTTP surface's services (ADR-0131), and the
    catalogue of UC-1.13 (ADR-0159): the processes a reader may start, a process started as the
    person on any channel, and every call of the MCP surface recorded. The composition root's,
    because starting a process crosses the process, command and run components."""

    async def processes(self, who: Resolution) -> Sequence[Mapping[str, Any]]:
        """Every process with an active version that `who` may see, with the inputs it takes."""
        ...

    async def catalogue(self, who: Resolution, *, agent_may_start: bool) -> Catalogue:
        """The same processes in plain words, with how to start each on each channel."""
        ...

    async def start(
        self,
        who: Resolution,
        process_id: str,
        inputs: Mapping[str, Any],
        *,
        channel: str = "channel.agent",
        address: str = "ledger",
    ) -> Run:
        """The process's active version started with the inputs, acting as `who`, through the
        one path every channel takes, by the one start command on `channel`. `StartRefused`
        when it cannot be."""
        ...

    async def called(
        self,
        who: Resolution,
        tool: str,
        outcome: str,
        arguments: Mapping[str, Any],
        run_id: str | None = None,
    ) -> None:
        """One call of a tool recorded in the ledger, `agent.<tool>`, with `who` as actor and
        the digest of the arguments, never the arguments (ADR-0131 §6)."""
        ...


class OperationReads(Protocol):
    """What keeps the operation running, each read from the component that owns it (ADR-0121):
    the incidents (ADR-0107), the alerts and the backup's state (ADR-0106), and the signals
    judged against their corridors (ADR-0109)."""

    async def incidents(self, tenant: Tenant) -> Sequence[Incident]:
        """Every incident, open and closed, newest first."""
        ...

    async def alerts(self, tenant: Tenant) -> Sequence[Alerted]:
        """Every alert, in effect, cleared and closed, each with what became of its report."""
        ...

    async def backup(self, tenant: Tenant) -> BackupWatched:
        """The backup's last outcome, by when the next is due, and its alert if one is in
        effect."""
        ...

    async def signals(self, tenant: Tenant) -> Sequence[tuple[Corridor, Judged]]:
        """Every signal in force, judged now against its corridor."""
        ...


class ActingViews(Protocol):
    """What acts for a tenant, what depends on it, and how a process really runs (ADR-0147):
    the composition root's, because the facts cross the catalog, process, governance, run and
    identity components. `visible` names the processes the reader may see."""

    async def register(self, tenant: Tenant, visible: frozenset[str]) -> Register: ...

    async def inventory(self, tenant: Tenant, visible: frozenset[str]) -> dict[str, Any]: ...

    async def stop(self, tenant: Tenant, adapter: str, actor: str) -> Any:
        """ADR-0138's stop of the adapter, by the person. `NotStoppable` for one no step halts
        at."""
        ...

    async def remove(self, tenant: Tenant, adapter: str, visible: frozenset[str]) -> RemoveView: ...

    async def residency(self, tenant: Tenant, visible: frozenset[str]) -> ResidencyView: ...

    async def wrong_result(
        self, tenant: Tenant, run_id: str, step_id: str, visible: frozenset[str]
    ) -> WrongResultView | None: ...

    async def variants(self, tenant: Tenant, process_id: str) -> VariantsView | None: ...


class StreamActs(Protocol):
    """The organisation seen as value streams (ADR-0159): the composition root's, because the
    view gathers the process, run and identity components' records."""

    async def declare(self, command: DeclareStream) -> ValueStream:
        """The process component's declaration. `InvalidProcess` where it is refused."""
        ...

    async def map(self, tenant: Tenant, visible: frozenset[str], days: int) -> StreamMap: ...

    async def lanes(
        self, tenant: Tenant, stream: str, visible: frozenset[str], days: int
    ) -> StreamLanes | None:
        """None where the tenant declared no such stream."""
        ...


class ProfileReads(Protocol):
    """A role's profile (ADR-0167 §3): the composition root's, because it gathers the process,
    governance, decision, run and identity components' records."""

    async def index(
        self, tenant: Tenant, reader: str, held: frozenset[str], visible: frozenset[str], days: int
    ) -> RoleIndex: ...

    async def profile(
        self,
        tenant: Tenant,
        role: str,
        reader: str,
        held: frozenset[str],
        visible: frozenset[str],
        days: int,
    ) -> RoleProfile | None:
        """None where neither the structure nor the processes know the role."""
        ...


class SubjectActs(Protocol):
    """Data-protection requests prepared, carried out by a person and withdrawn
    (ADR-0176)."""

    async def prepare(self, command: PrepareRequest, *, by: str) -> SubjectRequest: ...

    async def get(self, tenant: Tenant, request_id: str) -> SubjectRequest | None: ...

    async def list(self, tenant: Tenant) -> Sequence[SubjectRequest]: ...

    async def confirm(
        self, tenant: Tenant, request_id: str, *, by: str, identity_checked: bool
    ) -> Confirmed: ...

    async def withdraw(self, tenant: Tenant, request_id: str, *, by: str) -> SubjectRequest: ...


class EvidenceReads(Protocol):
    """The processing evidence, generated from configuration and the ledger (ADR-0176 §8)."""

    async def evidence(self, tenant: Tenant) -> dict[str, Any]: ...


class TenantExportActs(Protocol):
    """A tenant exported, and an export imported and checked (ADR-0221)."""

    async def export(self, tenant: Tenant, *, by: str) -> bytes: ...

    async def import_(self, content: bytes, *, by: str) -> TenantImported: ...


class GatheredFigures(Protocol):
    """Every owner's figures, gathered once for one reader (ADR-0241 §1)."""

    @property
    def shown(self) -> Sequence[Shown]: ...

    @property
    def index(self) -> Index: ...

    @property
    def proposals(self) -> Sequence[ValueProposal]: ...

    @property
    def backlog(self) -> Sequence[Mapping[str, Any]]: ...

    @property
    def facts(self) -> ValueFacts: ...

    @property
    def holders(self) -> Mapping[str, int]: ...


class FigureGathering(Protocol):
    async def gather(
        self, reader: LiveReader, visible: frozenset[str], days: int
    ) -> GatheredFigures: ...

    async def warehouse(
        self,
        reader: LiveReader,
        visible: frozenset[str],
        judged: Sequence[tuple[Corridor, Judged]],
    ) -> list[Shown]:
        """The warehouse figures among the signals judged now (ADR-0291 §3)."""
        ...

    async def configuration(self, tenant: Tenant) -> ViewConfiguration: ...

    async def configure(
        self, tenant: Tenant, document: Mapping[str, Any], *, by: str
    ) -> ViewConfiguration: ...


class KnowledgeReads(Protocol):
    """The same work with and without a knowledge source connected, compared on the value
    ledger's figures (ADR-0291)."""

    async def figures(self, tenant: Tenant, visible: frozenset[str], days: int) -> list[Figure]: ...


class ReportReads(Protocol):
    async def every(self, tenant: Tenant) -> list[ReportDefinition]: ...

    async def get(self, tenant: Tenant, id: str) -> ReportDefinition | None: ...

    async def put(
        self, tenant: Tenant, document: Mapping[str, Any], *, by: str
    ) -> ReportDefinition: ...

    async def compose(self, definition: ReportDefinition, visible: frozenset[str]) -> Composed: ...


class ExplanationReads(Protocol):
    async def step(self, reader: LiveReader, run_id: str, step_id: str) -> Explanation | None: ...

    async def summary(
        self, reader: LiveReader, visible: frozenset[str], days: int
    ) -> dict[str, Any]: ...


class OwnViewReads(Protocol):
    async def settings(self, tenant: Tenant, reader: str) -> OwnView | None: ...

    async def set(self, tenant: Tenant, reader: str, document: Mapping[str, Any]) -> OwnView: ...

    async def relief(self, reader: LiveReader, visible: frozenset[str], days: int) -> OwnRelief: ...


class Reading(Protocol):
    """Views, the export, reports, explanations, the value ledger and a person's own view
    (ADR-0241 to ADR-0245): the composition root's, because they gather many components."""

    @property
    def figures(self) -> FigureGathering: ...

    @property
    def reports(self) -> ReportReads: ...

    @property
    def explanations(self) -> ExplanationReads: ...

    @property
    def own(self) -> OwnViewReads: ...

    @property
    def bases(self) -> ValueBases: ...

    @property
    def discoveries(self) -> Discoveries: ...

    @property
    def knowledge(self) -> KnowledgeReads: ...


class RestServices(Protocol):
    @property
    def roles(self) -> Sequence[str]:
        """The roles this process runs, for the readiness answer."""
        ...

    @property
    def leading(self) -> bool:
        """Whether this process holds the scheduler's lead, for the readiness answer."""
        ...

    @property
    def tenants(self) -> TenantRegistry:
        """The instance's registry: the tenants it serves now — the oldest is the one a reply to
        a sender nobody could place is made in — and the administrator's acts on them
        (ADR-0104)."""
        ...

    @property
    def administration_key(self) -> Secret | None:
        """The key that admits a request to the administration of tenants; None when the
        operator configured none (ADR-0104 §4)."""
        ...

    @property
    def findings_intake(self) -> FindingsIntake | None:
        """The intake of other instances' findings; None where the operator opened none
        (ADR-0118)."""
        ...

    @property
    def findings(self) -> ProductFindings | None:
        """The product findings of this instance, classified and reviewed; None where the
        wiring records none (UC-6.12, ADR-0118)."""
        ...

    @property
    def corrections(self) -> Corrections:
        """The corrections of what Taktus proposed, counted per process and action class, and
        the levels a rule lowered (UC-7.5, ADR-0110)."""
        ...

    @property
    def runs(self) -> Queried[Run]:
        """The runs, read a page at a time and counted where they are stored (ADR-0094)."""
        ...

    @property
    def ledger(self) -> Ledger: ...

    @property
    def work(self) -> UnitOfWork: ...

    @property
    def intake(self) -> ReceiveIntakeHandler: ...

    @property
    def complete_intake(self) -> CompleteIntakeHandler: ...

    @property
    def identities(self) -> IdentityDirectory:
        """The identity component: an account key proves an identity, and the identity makes
        the link codes that link its channel accounts (ADR-0040)."""
        ...

    @property
    def decision_queries(self) -> DecisionQueries:
        """The requests addressed to a decider, one request, the response times (ADR-0042)."""
        ...

    @property
    def owner_reports(self) -> ReportQueries:
        """The reports to the owner, read by the owner and whom they named (ADR-0045)."""
        ...

    @property
    def answer_report(self) -> AnswerInChannelHandler:
        """A report answered on its page, by the same rules as in the channel (ADR-0120)."""
        ...

    @property
    def answer_decision(self) -> AnswerRequestHandler: ...

    @property
    def confirm_decision(self) -> ConfirmRequestHandler: ...

    @property
    def proposals(self) -> Proposals:
        """A person's proposals for a changed process (ADR-0091 §1)."""
        ...

    @property
    def proposal_acts(self) -> ProposalActs:
        """A proposal rehearsed and commissioned, and a process rolled back (ADR-0091 §3 to §5)."""
        ...

    @property
    def process_proposals(self) -> ProcessProposalActs:
        """The processes Taktus proposes, to a person, from recurring work (ADR-0270)."""
        ...

    @property
    def gallery(self) -> GalleryActs:
        """The gallery of first processes (UC-10.4, ADR-0136)."""
        ...

    @property
    def planning(self) -> PlanActs:
        """The plan dialogue, guided and expert (ADR-0237, ADR-0238)."""
        ...

    @property
    def coach(self) -> Coach:
        """Each person's own automation coach (ADR-0240)."""
        ...

    @property
    def structure(self) -> OrganisationStructure | None:
        """The organisation's structure and its projects (ADR-0275, ADR-0276); None where the
        instance keeps none."""
        ...

    @property
    def sessions(self) -> Sessions | None:
        """Sessions with a project's knowledge (ADR-0277); None where the instance keeps no
        structure."""
        ...

    @property
    def org_units(self) -> TenantOrgUnits:
        """The quotas per organisational unit (ADR-0166)."""
        ...

    @property
    def evaluations(self) -> EvaluationActs:
        """A process's evaluations on its cases, and the cases proposed from corrections
        (ADR-0134)."""
        ...

    async def decided(
        self, tenant: Tenant, run_id: str, actor: str, request_id: str | None = None
    ) -> None:
        """A request of the run took effect: the run continues from the boundary it waits
        at, or halts there, as the decision says. Nothing happens while another request of
        the run waits. A proposal to move a step, or to roll a move back, that the request
        answers is applied (ADR-0114)."""
        ...

    @property
    def clock(self) -> Clock:
        """The time a window of days ends at (ADR-0148)."""
        ...

    @property
    def spend(self) -> SpendHandler:
        """Where a run and a process spend, per step, and two runs side by side (ADR-0148)."""
        ...

    @property
    def trials(self) -> TrialActs:
        """A model tried on fixed cases, and the trials offered (ADR-0149)."""
        ...

    @property
    def takeovers(self) -> Takeovers:
        """A running step taken over and handed back (ADR-0128)."""
        ...

    @property
    def takeover_instructions(self) -> InstructionActs:
        """A process's takeover instructions and the trials of them (ADR-0180)."""
        ...

    @property
    def tenant_exports(self) -> TenantExportActs | None:
        """A tenant's export and import, for the administration key; None where the state is
        not a database (ADR-0221)."""
        ...

    @property
    def subject_requests(self) -> SubjectActs:
        """Data-protection requests, prepared and carried out by a person (ADR-0176)."""
        ...

    @property
    def processing_evidence(self) -> EvidenceReads:
        """What is processed for a tenant, generated (ADR-0176 §8)."""
        ...

    @property
    def stages(self) -> Stages:
        """A tenant's introduction in stages: the view and a stage opened by a person
        (ADR-0137, ADR-0191)."""
        ...

    @property
    def agent(self) -> AgentActs:
        """What the MCP surface needs beyond these services (ADR-0131)."""
        ...

    @property
    def operation(self) -> OperationReads:
        """Incidents, alerts, the backup and the signals, for the pages that show what keeps
        the operation running (ADR-0121)."""
        ...

    @property
    def levels(self) -> LevelQueries:
        """The levels of the live representation, read for one reader (ADR-0063)."""
        ...

    @property
    def traces(self) -> StepTraces:
        """The trace inside a worker's step, read and shared by role (ADR-0135)."""
        ...

    @property
    def queries(self) -> StepQueries:
        """The queries a step sent, read by a person entitled to the step (ADR-0262 §3)."""
        ...

    @property
    def connection_grants(self) -> ConnectionGrants:
        """Writing on a connection, granted and withdrawn by a person (ADR-0262 §2)."""
        ...

    @property
    def acting(self) -> ActingViews:
        """The register, the dependencies and the variants of a process (ADR-0147)."""
        ...

    @property
    def streams(self) -> StreamActs:
        """The organisation as value streams, and their declaration (ADR-0159)."""
        ...

    @property
    def profiles(self) -> ProfileReads:
        """A role's profile, derived from the processes (ADR-0167)."""
        ...

    @property
    def reading(self) -> Reading:
        """Views, the export, reports, explanations, value and a person's own view."""
        ...

    @property
    def changes(self) -> ChangeStreams:
        """The live stream of changes of state (ADR-0055)."""
        ...

    async def ready(self) -> str | None:
        """None when the process may receive traffic: the database answers and its schema is
        the one this build needs. Otherwise the reason, one sentence, never a secret."""
        ...
