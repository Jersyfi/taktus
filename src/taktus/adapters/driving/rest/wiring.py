"""What the HTTP surface needs from the composition root, as a protocol.

A driving adapter calls application services and never builds them (docs/architecture/
project-structure.md §3). The composition root implements this and hands it to `build_app`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

from taktus.components.command.application.service import (
    CompleteIntakeHandler,
    ReceiveIntakeHandler,
)
from taktus.components.decision.application.query import DecisionQueries
from taktus.components.decision.application.service import (
    AnswerRequestHandler,
    ConfirmRequestHandler,
)
from taktus.components.governance.application.service import Corrections
from taktus.components.governance.domain.model import Incident
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.domain.model import (
    CorrectedCase,
    Evaluation,
    ProcessVersion,
    Proposal,
)
from taktus.components.reporting.application.query import LevelQueries, ReportQueries
from taktus.components.reporting.application.service import (
    Alerted,
    AnswerInChannelHandler,
    BackupWatched,
    FindingsIntake,
    ProductFindings,
)
from taktus.components.reporting.domain.model import (
    Change,
    Corridor,
    Judged,
    Reader,
    Scope,
    Snapshot,
)
from taktus.components.run.application.service import HandBack, TakeOver
from taktus.components.run.domain.model import Run
from taktus.ports.configuration import Secret
from taktus.ports.identity import Resolution
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Queried, Tenant, UnitOfWork


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


class StartRefused(Exception):
    """A process was not started from the MCP surface; the message says why, in one sentence
    the person's agent can act on (ADR-0131 §5)."""


class AgentActs(Protocol):
    """What the MCP surface needs beyond the HTTP surface's services (ADR-0131): the processes a
    reader may start, a process started as the person, and every call recorded. The composition
    root's, because starting a process crosses the process, command and run components."""

    async def processes(self, who: Resolution) -> Sequence[Mapping[str, Any]]:
        """Every process with an active version that `who` may see, with the inputs it takes."""
        ...

    async def start(self, who: Resolution, process_id: str, inputs: Mapping[str, Any]) -> Run:
        """The process's active version started with the inputs, acting as `who`, through the
        one path every channel takes. `StartRefused` when it cannot be."""
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
    def takeovers(self) -> Takeovers:
        """A running step taken over and handed back (ADR-0128)."""
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
    def changes(self) -> ChangeStreams:
        """The live stream of changes of state (ADR-0055)."""
        ...

    async def ready(self) -> str | None:
        """None when the process may receive traffic: the database answers and its schema is
        the one this build needs. Otherwise the reason, one sentence, never a secret."""
        ...
