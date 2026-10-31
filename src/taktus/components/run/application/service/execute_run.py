"""Use cases: start a run from a commissioned plan, submit one for a runner, resume a halted
one, request a stop, answer a step that waits for a person, take a running step over and hand
it back.

One engine, eight entry points. `start` creates the run and executes it in this process;
`submit` creates the run and puts a job on the queue, so that a runner — this process or
another — executes it (`runner.py`); `resume` continues a halted or escalated run at its
boundary, starts a submitted one, or recovers a run whose instance stopped without halting it;
`request_stop` asks a running run to stop at its next boundary; `confirm` records a person's
answer to steps that wait for one; `decide` continues a run whose anchored steps were decided;
`take_over` asks that a person take over a running worker step, and `hand_back` records the
result the person hands back. Execution is sequential: one step at a time, in the plan's order.

Before anything of a step starts, the tenant's anchors are asked which of them name the step's
act (ADR-0042, `run/ports/anchors.py`). An anchor holds at every autonomy level: for each one
that applies, a decision request is raised in the decision component — one shape, two options:
perform the act as proposed, or not — and the step waits in `waiting_human`
(`step.anchored`). A person answers the request there and confirms how the answer was read;
only then does `decide` read the applied decision (`step.decided`): a step decided to proceed
continues at its level from the same boundary, and one declined is not run, and the run halts
with cause `declined`. A request that cannot be raised — a part missing — is not raised, the
step fails without its act, and the run escalates. A rehearsal from the tenant's recordings
acts on nothing outside and is asked no anchor (NTC-0079); a replay of a recorded run is
(ADR-0108). A step confirmed with `confirm` is never an anchored one.

A process may hold a step itself (ADR-0088). A step whose `when` does not hold is skipped:
it succeeds with a result that says so, performs nothing and asks nobody. A step that
declares `ask` raises its own decision request beside any anchor's, at every level; with
`on_decline: continue`, a declined act is not performed and the step succeeds with a result
that says who declined it and what they answered, so that the steps after it act on it.

A process may also say what it does when a run escalates (ADR-0097). A step whose work says
`on_escalation: true` is no part of the sequence. When a step fails and the run escalates, the
steps marked so run first, in the plan's order, each once every step it depends on succeeded;
then the run ends escalated for the step that failed. They read the run's own record through
`$run`: its id, and the step that failed with its reason. A run that finishes skips them.

Before a step starts, its autonomy level is applied (ADR-0039, `domain.service.autonomy`): the
lowest of the process's level and the levels of the tool actions the step uses. At level 2 the
step waits until a person confirmed it (`step.awaiting`, then `step.confirmed`); at level 1 a
step that acts is never executed — its proposal is recorded, and it waits until a person
performed the act and reported it (`step.performed`). A waiting step holds back only the steps
that depend on it; the others run on, and the run waits in `waiting_human` once nothing else can
run. From level 3 a step runs only on an adapter at *verified* or above; one below is not run on
it, the step is rejected with a finding that names it and the adapter, and the run halts with
cause `maturity` (NTC-0051). A rehearsal is asked none of this (NTC-0079); a replay is asked
the level, and not the maturity (ADR-0108). At level 4 a step that failed with a failure an
adapter classified as repeatable is healed within the frame (ADR-0160, `domain.service.healing`):
`step.healed` records it, and the step is admitted again at once; past the frame the run
escalates, and its reason says why it was not healed.

A person's answer to a step proposed at level 1 or 2 is a decision on a proposal (ADR-0110):
`released` as proposed, `corrected` — the work as the person released it, which the step then
runs with at level 2 — or `rejected`, which runs nothing of the step and halts the run with
cause `declined`. Each is recorded as `proposal.decided`, with the action class whose level held
the step and the digests of the proposal and of the version released, and no person; the
answer's own entry names who answered. The governance component then applies its rule to the
decisions, through the run's port `Levels`. Before a step's level is applied, the run takes on
the levels its version was lowered to by rule (`run.lowered`). After a step acted, the anchors
are asked again: an anchor that names the act, with no decision to perform it, is a breach, and
the process falls one level before its next step.

What happens around every step is the contract of ADR-0005 and is the same for every method:

1. estimate — every step, whatever its method: a worker step asks the worker; an `llm` step
   counts its prompt through the model adapter and bounds its output by the limit it sets; a
   connector call reserves what its operation declares one call consumes, a wait on one as
   many calls as it can make; a rule or a wait on the clock demands nothing, and that is exact.
   A step that cannot be estimated is refused, never admitted (ADR-0005), and the run halts with
   cause `no_estimate`;
2. admit — the estimate, scaled by the measured error of the adapter that gave it
   (`domain.service.budget`), is reserved against what remains of the line the run is held to —
   the budget less its margin (`domain.service.admission`); a step that does not fit is
   *rejected* before anything starts, and the run halts with cause `limit`. A worker receives its
   reservation as its `limits` and halts at its next boundary before crossing it (W-14). Under a
   currency budget, compute seconds count at the run's price table, and compute the table does
   not price is refused, never admitted as free (ADR-0005, fourth amendment);
3. run — through the worker port, the rule table, the connector port, or the clock;
4. persist — the step run with its checkpoint, artifacts and raw consumption is written before
   the next step is looked at; every state change and the ledger entry that describes it are
   one transaction of the unit of work, and a step that finished with a result gets its
   provenance record in that same transaction (ADR-0021): what it read and when, what it
   produced, the ledger entry it belongs to;
5. boundary — a stop requested meanwhile, or `stop_after`, takes effect here.

A worker step that is stopped mid-way ends `stopped` with the worker's checkpoint; resuming
hands that checkpoint back to the worker, which produces nothing it produced before it, and the
engine records no artifact twice even if it did. The worker's own step boundaries are persisted
as they arrive, so that an instance that dies mid-step loses at most the worker's current inner
step, not the whole step (ADR-0013 A).

A worker that holds as many assignments as it declares answers a new one *at capacity*
(ADR-0037). Nothing started, so this is no failure: the step goes back to the boundary it was
admitted from and gives its reservation back (`step.waiting`), and the run halts there with
cause `capacity`. The runner defers the run's job, and whoever claims it next asks the worker
again. When the worker takes the assignment, `step.waited` records the wait with its account,
cause and duration, and the step runs. A wait that outlasts the step's ceiling ends the step
failed with cause `capacity`, and the run escalates.

A connector step (`rule: connector`) is where ADR-0005's promise meets the outside. The call
carries an idempotency key derived from run, step and the step's attempt — never stored, so a
step recovered after a crash derives the same key and a `marked` connector answers with the
original record. An outward effect the connector reports becomes an `egress.write` or
`egress.delivery` entry in the same transaction as `step.finished` (ADR-0022 §4). A classified
failure ends the step failed with the connector's cause; the engine retries nothing on its
own — a resume is a person's act, and for an operation the connector cannot recognise a repeat
of (`idempotency: none`) the reason says that resuming repeats the call (ADR-0024 §3).

A run can be a *rehearsal* (ADR-0030): an outward connector operation is not called, and the
step answers with the recorded response of the most recent real call of the same operation
through the same adapter (`application/query/recordings.py`); it finishes with outcome
`rehearsed`, writes no egress entry, and every ledger entry of the run carries
`rehearsal: true`. Reads, rules, llm and worker steps run as they do in any run.

An engine given a *replay* (ADR-0108, `ports/replay.py`) replays a recorded run instead: every
rehearsal it executes resolves its workers, connectors and models from the replay, which answers
each step that would leave the engine with the recorded result of the same step. An outward
operation is then sent to the replay, finishes `rehearsed` and writes no egress. Such a rehearsal
asks its step boundaries — anchors, a step's own `ask`, the level — as any run does; the
maturity of an adapter is not asked, because the adapter is the recording.

A run a runner resumes on its claim is written under that claim (#107). Every transaction that
writes the run first asks the queue whether the claim is still the runner's (`Queue.fence`),
and the queue keeps it so until the transaction ends. When another runner has claimed the job
meanwhile — this one was cut off for longer than the lease — the write is refused with
`ClaimLost`, nothing of it lands, and the engine does nothing more for the run. Two runners
therefore never both commit to one run.

A worker step hands its assignment over in four stages: the worker's estimate, the committed
`step.admitted`, the committed `step.assigned` naming the assignment's id, and the worker's
acceptance over HTTP, after which `step.started` is committed. The id is recorded before the
worker sees it, and stays *open* until the step reads the assignment's end (ADR-0038). A step
with an open assignment — its instance died, its stream broke, its runner lost the claim — asks
the worker about it before it hands over another. One the worker holds is *adopted*
(`step.adopted`): followed from the last event the step run holds, never repeated beside it.
One the worker does not know is posted again under the same id, so that a cut-off runner whose
post arrives late meets the worker's 409. A worker that cannot be asked fails the step; nothing
new is handed over. A runner that loses its claim leaves the assignment running for the runner
that holds the claim now.

A person can take over a worker step while it runs (ADR-0128). `take_over` asks it on the run's
job, for the first asker only, and records `step.takeover_asked`; the runner holding the job
reads the ask with its lease (`takeover_asked`) and asks the worker to stop. At the step's
boundary the state it reached becomes an artifact, the step and the run wait for the person,
and in the same transaction the claim passes to the take-over (`step.taken_over`): the person
holds the job until the take-over's lease ends. A step that ends otherwise is not taken over
(`step.takeover_refused`). `hand_back` writes the person's result under the take-over's claim,
fenced as a runner's write is: the step succeeds with method `human`, its provenance names
what it read, and the job is released for the next runner. A runner that claims the job once
the lease has passed gives the step back to its worker at the checkpoint
(`step.takeover_lapsed`).

A person can send a message to a worker step while it runs (ADR-0156). `steer` refuses it unless
the step is a running worker step of a run a runner holds and its worker declares steering;
otherwise it stores the text as an object, records `step.message_asked` with the person as actor
and the text by digest, and places the message on the run's job. The runner holding the job
hands it to the worker under its claim (`messages_asked`, `step.message_handed`). The worker's
`message.received` is recorded as `step.message_received`, and the message joins the step run's
inputs and its provenance. The message reaches the worker as the contract's closed
`SteeringMessage`: nothing of the frame, the limits or the exactness class is read from it.
"""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from taktus.components.run.application.query.recordings import RecordedResponses
from taktus.components.run.application.service.bound_models import BoundModels
from taktus.components.run.application.service.deadlines import DeadlineKeeper
from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import (
    INTERRUPTIBLE,
    PROCEED,
    RESUMABLE,
    RUN_ENDED,
    Anchoring,
    Ask,
    BacklogRule,
    Cause,
    Checkpoint,
    CheckRead,
    CheckRule,
    ClaimLost,
    ClassificationRule,
    CommitTitleRule,
    ConnectorRule,
    ConstantRule,
    Control,
    DeviationStatistic,
    Ended,
    ExtractRule,
    InvoiceRule,
    LlmWork,
    Message,
    MessageRefused,
    MlWork,
    NoConnector,
    NoWorker,
    ParticipantWork,
    ReadyRule,
    ReceivedMessage,
    RoadmapRule,
    RuleFailed,
    Run,
    RunError,
    RunExists,
    RunState,
    ScreenRule,
    SpamRule,
    StepRun,
    StepState,
    Takeover,
    TakeoverRefused,
    TemplateRule,
    UnknownRun,
    UnknownTakeover,
    UnsupportedWork,
    VerifyArtifactRule,
    WaitUntil,
    WaitWork,
    Work,
    WorkerWork,
    artifact_references,
    block,
    control_of,
    empty_markers,
    parse_work,
    referenced_values,
    references,
    resolve,
    select,
)
from taktus.components.run.domain.model.block import Account, Awaited, OpenBlock
from taktus.components.run.domain.model.run import IN_FLIGHT, TAKEOVER_RESULT, TAKEOVER_STATE
from taktus.components.run.domain.model.work import PREDICT, SKILLS
from taktus.components.run.domain.service import (
    anchoring,
    autonomy,
    blocked,
    checking,
    frame,
    healing,
    interfaces,
    invoices,
    messages,
    open_work,
    participants,
    prediction,
    provenance,
    repetition,
    routing,
    rules,
    statistics,
    waiting,
)
from taktus.components.run.domain.service import budget as budgeting
from taktus.components.run.domain.service.admission import admit, remaining
from taktus.components.run.domain.service.capacity import (
    CapacityDemand,
    CapacityRules,
    admit_capacity,
)
from taktus.components.run.domain.service.projections import CALIBRATION, step_key
from taktus.components.run.domain.service.rehearsal import REHEARSED
from taktus.components.run.domain.service.trace import line_of
from taktus.components.run.ports import (
    Anchors,
    Breach,
    Cap,
    ConnectorPool,
    Decisions,
    Draft,
    Guidance,
    Levels,
    Maturities,
    MessageRules,
    Messages,
    ModelPool,
    NotRaised,
    OpenWork,
    ProposalDecided,
    Repeated,
    Repetition,
    Replay,
    Residency,
    Sources,
    Statements,
    Verdict,
    WorkerPool,
)
from taktus.ports.administration import Administration
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.connector import (
    CallContext,
    CallFailed,
    CaseScope,
    ConnectorError,
    ContractBroken,
    Effect,
    EffectReport,
    Operation,
    ResolvedConnector,
    Result,
    idempotency_key,
)
from taktus.ports.connector import (
    Cause as ConnectorCause,
)
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.model import (
    Calculability,
    ModelAtLimit,
    ModelError,
    Permitted,
    PriceTable,
    Prompt,
    WeightingTable,
    price,
)
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import (
    PersistenceError,
    ProvenanceStore,
    Repository,
    Tenant,
    UnitOfWork,
)
from taktus.ports.platform import Platform
from taktus.ports.queue import RUN_EXECUTE, AskedMessage, Claim, Job, Queue, TakeoverAsked
from taktus.ports.telemetry import Span, Telemetry
from taktus.ports.traces import Masking, Traces
from taktus.ports.worker import (
    ArtifactProduced,
    Assignment,
    AssignmentExists,
    AssignmentFinished,
    AssignmentState,
    Callback,
    ConsumptionReported,
    Context,
    Event,
    Frame,
    HandoverRequest,
    Limits,
    MessageReceived,
    ModelCalled,
    NoEstimator,
    Outcome,
    ResolvedWorker,
    SteeringMessage,
    SteeringRefused,
    StepBoundary,
    StopRequest,
    Task,
    ToolCalled,
    UnaskedWorker,
    UnknownAssignment,
    Worker,
    WorkerAtCapacity,
    WorkerError,
)
from taktus.shared.v1 import (
    QUANTITIES,
    Anchor,
    Artifact,
    AutonomyLevel,
    Check,
    CheckKind,
    Consumption,
    ConsumptionQuantities,
    Digest,
    InputKind,
    LedgerEntry,
    LedgerRefs,
    Method,
    Plan,
    PriceKinds,
    ProvenanceInput,
    ProvenanceRoute,
    Step,
    StepId,
    add_tokens_by_model,
)
from taktus.shared.v1.consumption import MODEL_NAME_PATTERN

RECOUNTS = 5
"""How often a run counts its process's open work again when other runs of it pass at the same
moment, before it waits a check instead (ADR-0132 §2)."""

CLAIM_LOST = "run.claim_lost"
"""The ledger kind a runner's lost claim is recorded under (ADR-0106 §2)."""

TAKEOVER_ASKED = "step.takeover_asked"
"""A person asked to take over a running step (ADR-0128 §1). Changes no state."""
TAKEN_OVER = "step.taken_over"
"""The step stopped at its worker's boundary and waits for the person who took it over."""
TAKEOVER_REFUSED = "step.takeover_refused"
"""The step ended another way before it stopped, and was not taken over. Changes no state."""
TAKEOVER_LAPSED = "step.takeover_lapsed"
"""The take-over's lease passed without a hand-back: the step is back at its checkpoint."""
MESSAGE_ASKED = "step.message_asked"
"""A person sent a message to a running step (ADR-0156 §7): the person as actor, the text by
digest. Changes no state."""
MESSAGE_HANDED = "step.message_handed"
"""The runner holding the run handed the message to the worker: `handed`, `refused` or
`not_running`. Changes no state."""
MESSAGE_RECEIVED = "step.message_received"
"""The worker received the message at a boundary; it is an input of the step from there."""
MESSAGE_LENGTH = 8000
"""The longest text a message carries: the contract's `SteeringMessage.text`."""
HOLDER = "takeover:"
"""What the claimant of a take-over's claim starts with; the take-over identifier follows."""

CONTINUATIONS = 3
"""How often one step continues in a new unit after its worker stopped at its wall clock."""

NO_RESULT = b"null"
"""The result of a step a person performed after its model was unsure: nothing (ADR-0076)."""

SOURCE_REF_LENGTH = 200
"""How much of an operation and its input a provenance source reference keeps (ADR-0021 §4
bounds an input to 384 bytes)."""


@dataclass(frozen=True)
class StartRun:
    plan: Plan
    work: Mapping[StepId, Mapping[str, Any]]
    budget: Limits
    process_version: str
    actor: str
    tenant: Tenant
    stop_after: int | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    """What `$input` references in the work resolve to."""
    margin: float | None = None
    """The share of every limit held back from the first step on (ADR-0005); None takes the
    engine's configured margin."""
    rehearsal: bool = False
    """A rehearsal: no outward connector operation acts (ADR-0030)."""
    run_id: str | None = None
    """The run's identifier when the caller derives it — a trigger's firing does, so that the
    same firing names the same run. A run that exists under it is never created again:
    `RunExists`. None draws a fresh one."""
    trigger: Mapping[str, Any] | None = None
    """The trigger that started the run, as its document. Recorded as `run.triggered` beside
    `run.created`, in the same transaction (ADR-0035)."""
    actions: Mapping[str, AutonomyLevel] = field(default_factory=dict)
    """The levels of the process's tool actions (`Autonomy.action_levels`): a step that uses one
    runs at the lowest level that applies to it (ADR-0039). Every caller that starts a run from
    a process version passes them."""
    bindings: Mapping[str, str] = field(default_factory=dict)
    """Purposes bound to one configured model for this run alone (`Run.bindings`): a model
    trial's case run (ADR-0149 §1). Empty for every other run."""
    skills: Mapping[str, str | None] = field(default_factory=dict)
    """Skill versions bound for this run alone, `{name: version}`; None hands the skill over
    at no version. An evaluation of a skill binds them (ADR-0162 §3). A skill not named here is
    pinned at its version in production."""
    profile: str | None = None
    """The role profile of the shared agent the run serves (ADR-0163 §5)."""

    @property
    def identity(self) -> str:
        """On whose behalf the run acts: whoever commissioned the plan, else the actor."""
        commissioned = self.plan.commissioned
        return commissioned.by if commissioned is not None else self.actor


@dataclass(frozen=True)
class ResumeRun:
    """Continue a run at its boundary. A halted or escalated run continues where it stopped; a
    submitted run that never started starts. A run still marked as executing is *recovered*:
    the instance that ran it is taken to be gone, the step it was inside is set back to its
    last persisted boundary, and the run continues. The caller asserts that no instance is
    executing the run: the runner's claim on the run's job asserts it (`runner.py`) and fences
    every write against a runner that lost the claim (`claim`); `taktusctl run --resume` is an
    operator's explicit act."""

    run_id: str
    actor: str
    tenant: Tenant
    budget: Limits | None = None  # a changed limit; None keeps the run's
    reason: str | None = None
    """Why the limit changed, in the person's words: kept in the budget statement the ledger's
    `budget.set` names, never in the ledger itself (ADR-0006, #458)."""
    stop_after: int | None = None
    on_claim: bool = False
    """Resumed because a runner claimed the run's job. A runner can die after the run's last
    state was committed and before it completed the job; the next runner then claims a job
    whose run has already ended. Such a run — finished, escalated, or halted for any cause but
    a stop — is returned as it is, nothing executes, and the runner completes the job: what
    waits for a person stays with the person (issue #73)."""
    claim: Claim | None = None
    """The runner's claim on the run's job. Every write of the run is fenced by it: once
    another runner has claimed the job, the write is refused with `ClaimLost` (#107). None for
    an operator's resume, which no claim stands behind."""
    last_attempt: bool = False
    """The claim is the last its job is given: the queue claims the job no more after it. A
    step that raises then fails with what it raised, and the run escalates for it, instead of
    the exception leaving the engine and the run staying `running` for nobody (#591)."""


@dataclass(frozen=True)
class ConfirmSteps:
    """A person answers steps the run waits for (ADR-0039). At level 2 the answer confirms the
    step, and it starts; at level 1 `performed` reports that the person performed the act
    Taktus proposed, and the step ends without Taktus executing it. The run then continues: in
    this process, or — with `enqueue` — on the runner that claims the job it is given."""

    run_id: str
    steps: tuple[StepId, ...]
    actor: str
    """The person who answers. Who may answer is a right per role (UC-7.3); until rights per role
    exist, any identity the tenant knows may."""
    tenant: Tenant
    performed: bool = False
    enqueue: bool = False
    stop_after: int | None = None
    corrected: Mapping[StepId, Mapping[str, Any]] = field(default_factory=dict)
    """The work a person released in place of what Taktus proposed, per step it answers: at
    level 2 the step runs with it, at level 1 it is what the person performed (ADR-0110)."""
    rejected: bool = False
    """The person rejects what the steps propose: nothing of them runs, and the run halts with
    cause `declined`. Resuming it proposes them again (ADR-0110)."""


@dataclass(frozen=True)
class TakeOver:
    """A person asks to take over a step of a run while it runs (ADR-0128 §1). Who may is any
    identity of the tenant that may see the run, until rights per role exist (UC-7.3)."""

    run_id: str
    step_id: StepId
    actor: str
    """The person who asks; named as the actor of `step.takeover_asked`, for the audit."""
    tenant: Tenant


@dataclass(frozen=True)
class SteerStep:
    """A person sends a message to a step of a run while it runs (ADR-0156 §7). Who may is
    decided by the surface the person uses; the engine checks the step and its worker."""

    run_id: str
    step_id: StepId
    text: str
    actor: str
    """The person who sends it; named as the actor of `step.message_asked`, for the audit."""
    tenant: Tenant


@dataclass(frozen=True)
class HandBack:
    """The person who took a step over hands its result back (ADR-0128 §5)."""

    run_id: str
    takeover: str
    """The take-over identifier the person received when they asked."""
    result: Any
    """The step's result, as one JSON value."""
    actor: str
    tenant: Tenant


@dataclass(frozen=True)
class AnswerParticipant:
    """A participant outside the organisation wrote in the thread a `human` step waits for an
    answer in (ADR-0155). Matched by the channel and the thread, never by an identity: the
    account is the channel's own name for whoever wrote."""

    run_id: str
    step_id: StepId
    tenant: Tenant
    channel: str
    account: str
    text: str
    enqueue: bool = False
    """The run continues on the runner that claims the job it is given; otherwise here."""


@dataclass(frozen=True)
class ParticipantAnswered:
    """What became of a participant's message — `read`, `unread`, `withdrawn`, `recorded`, or
    `other` for a message from another account than the one that answered first, of which
    nothing is kept — and what Taktus says back in the thread."""

    taken: bool
    outcome: str
    say: str | None
    run: Run


PROPOSAL_DECIDED = "proposal.decided"
"""A person's decision on a step proposed at level 1 or 2 (ADR-0110)."""
RUN_LOWERED = "run.lowered"
"""A run took on a level its version was lowered to by rule (ADR-0110)."""
RETRIED = "step.retried"
"""A step admitted again after it failed: a retry, as a fact of its own (ADR-0147 §4)."""


@dataclass(frozen=True)
class _Decision:
    """What a person's answer to a proposed step was, before it is recorded."""

    step_id: StepId
    outcome: Literal["released", "corrected", "rejected"]
    level: AutonomyLevel
    action: str | None
    corrected: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DecideSteps:
    """Continue a run whose anchored steps were decided (ADR-0042). The engine reads each
    request's verdict from the decision component: a step whose requests all took effect with
    "perform it" continues from its boundary; a step any request declined is not run, and the
    run halts. A step whose requests are not all applied keeps waiting. The run continues in this
    process, or — with `enqueue` — on the runner that claims the job it is given."""

    run_id: str
    actor: str
    tenant: Tenant
    enqueue: bool = False
    stop_after: int | None = None


def _ended(run: Run) -> bool:
    """Whether a run has ended in a way a runner's claim does not continue."""
    if run.state in (RunState.FINISHED, RunState.ESCALATED):
        return True
    if run.state is RunState.WAITING_HUMAN:
        # What waits for a person stays with the person, unless a person has answered. A run
        # none of whose steps waits any more — the last one was answered or handed back — is
        # continued, so that it finishes (ADR-0128 §5).
        return run.runnable() is None and bool(run.waiting())
    return run.state is RunState.HALTED and run.cause not in (
        Cause.STOP,
        Cause.CAPACITY,
        Cause.PARKED,
    )


@dataclass(frozen=True)
class Trace:
    """What the provenance record of a step needs beyond the step run itself: what the step
    read, and the version the adapter declared — and, for a connector step whose effect left
    the system, the egress entry to write beside `step.finished` (ADR-0022 §4)."""

    inputs: tuple[ProvenanceInput, ...] = ()
    adapter_version: str | None = None
    egress: EffectReport | None = None
    rehearsed: bool = False
    """The step answered from a recording instead of acting outward (ADR-0030)."""
    route: ProvenanceRoute | None = None
    """For a step on a model: the route it took through its purpose's chain (ADR-0116 §7)."""
    message: Digest | None = None
    """For a message step that sent: the digest of its record, which `message.sent` names
    beside the egress entry (ADR-0142 §10)."""


@dataclass(frozen=True)
class EngineOptions:
    step_ceiling_seconds: int = 300
    """How long a running worker step may take to finish after a stop was requested."""
    prices: PriceTable | None = None
    """The price table money is computed at. None: no model is priced, and a budget in a
    currency says so when it is set."""
    weights: WeightingTable | None = None
    """The weighting table in force, the Takt is computed at (ADR-0010). Its digest is named in
    every run's budget statement when the run starts. None: the run's Takt is not computed, and
    its cost says so."""
    model_classes: Mapping[str, str] = field(default_factory=dict)
    """Which class of the weighting table each model is in, as the operator set it
    (`TAKTUS_TAKT_MODEL_CLASSES`); recorded with the run."""
    margin: float = 0.0
    """The named safety margin a run is held with unless its command names one
    (`TAKTUS_BUDGET_MARGIN`)."""
    seeds: tuple[budgeting.Seed, ...] = budgeting.SEED
    """What calibration starts from for an adapter nothing has measured yet."""
    uncalibrated_margin: float = budgeting.UNCALIBRATED_MARGIN
    """What a worker with no calibration history reserves beyond its estimate (DEC-0034)."""
    capacity: CapacityRules = field(default_factory=CapacityRules)
    """What admission against the platform holds a job to (docs/architecture/platform.md)."""
    unit_memory_bytes: int | None = None
    """The memory limit of the execution unit a worker step starts on this platform; None when
    a worker step starts none here — a worker reached by endpoint runs elsewhere."""
    capacity_ceiling_seconds: int = waiting.CAPACITY_CEILING_SECONDS
    """How long a worker step waits for a free place at its worker when its work names no
    ceiling (ADR-0037)."""
    decision_days: int = 3
    """How many days after it is raised a decision request an anchor raises is due
    (ADR-0042)."""
    model_cool_down_seconds: float = 60.0
    """How long a model is passed over after it failed, or answered at its rate limit without
    naming a delay (`TAKTUS_MODEL_COOL_DOWN_SECONDS`, ADR-0116 §5)."""
    takeover_lease_seconds: float = 8 * 3600.0
    """How long a person holds a step they took over before the step goes back to its worker
    (ADR-0128 §4)."""
    park_waits_after_seconds: float | None = None
    """A `wait` step that would wait longer than this parks its run: the run halts with cause
    `parked`, and its runner defers the job to the wait's next check, holding no place
    meanwhile (ADR-0103). None waits inline, where no runner resumes a halted run — a run
    executed from the command line."""


@dataclass(frozen=True)
class _Demand:
    """What a step is estimated to use, or why it cannot be estimated, and the adapter the
    estimate came from."""

    quantities: ConsumptionQuantities | None
    why_not: str | None = None
    adapter: str | None = None
    capabilities: tuple[str, ...] = ()


NOTHING = ConsumptionQuantities()
"""The demand of a rule or a wait on the clock: nothing, and exactly so."""


class RunEngine:
    def __init__(
        self,
        *,
        runs: Repository[Run],
        work: UnitOfWork,
        objects: ObjectStore,
        ledger: Ledger,
        provenance: ProvenanceStore,
        workers: WorkerPool,
        clock: Clock,
        ids: Identifiers,
        telemetry: Telemetry,
        queue: Queue | None = None,
        options: EngineOptions | None = None,
        connectors: ConnectorPool | None = None,
        models: ModelPool | None = None,
        platform: Platform | None = None,
        recordings: RecordedResponses | None = None,
        maturities: Maturities | None = None,
        anchors: Anchors | None = None,
        decisions: Decisions | None = None,
        administration: Administration | None = None,
        replay: Replay | None = None,
        levels: Levels | None = None,
        residency: Residency | None = None,
        sources: Sources | None = None,
        open_work: OpenWork | None = None,
        repetition: Repetition | None = None,
        deadlines: DeadlineKeeper | None = None,
        traces: Traces | None = None,
        masking: Masking | None = None,
        stops: Stops | None = None,
        messages: Messages | None = None,
        statements: Statements | None = None,
        guidance: Guidance | None = None,
    ) -> None:
        self._guidance = guidance
        """Where a run finds the skills its steps name and the profile it serves (ADR-0162,
        ADR-0163). None: nothing is pinned and nothing is handed over."""
        self._runs = runs
        self._work = work
        self._objects = objects
        self._ledger = ledger
        self._provenance = provenance
        self._workers = workers
        self._connectors = connectors
        self._models = models
        self._platform = platform
        self._maturities = maturities
        """Where a step at level 3 learns its adapter's maturity. None: no record can be read,
        and no step at level 3 runs on an adapter (NTC-0079)."""
        self._anchors = anchors
        """Which of the tenant's anchors name a step's act. None: no anchor is evaluated; every
        composition root wires it (ADR-0042)."""
        self._decisions = decisions
        """Where an anchored step raises its decision requests. None with anchors wired: an
        anchored step cannot ask, and fails without its act."""
        self._residency = residency
        """Where a step on a model learns the location its tenant's rule permits. None: every
        tenant permits `anywhere` (ADR-0116 §3)."""
        self._sources = sources
        """What the tenant declares about the data behind a capability (ADR-0130). None: no
        source is declared free of personal fields, and only a connector's own declaration says
        that a capability serves personal data."""
        self._open_work = open_work
        """The caps a process version declares on its open work (ADR-0132). None: no run waits
        at a cap."""
        self._repetition = repetition
        """The tenant's limits on repetition, and where a stop raises its incident (ADR-0132
        §5). None: no call is counted and no step is stopped for repeating."""
        self._deadlines = deadlines
        """Where a run's deadlines are started and met, in the transaction of the entry that
        starts or meets one (ADR-0133). None: a run carries no deadline."""
        self._traces = traces
        """Where every event a worker reports is kept, masked, as a line of its step's trace
        (ADR-0135). None: no trace is kept."""
        self._masking = masking
        self._stops = stops
        """The tenant's stops of adapters (ADR-0138). None: no adapter is stopped, and a stop
        reaches a run only by its own identifier."""
        self._messages = messages
        self._statements = statements
        """Where `{"$run": "exactness"}` reads the statement of the run's version (UC-6.9). None:
        a step that names it fails, as a reference that cannot be resolved does."""
        """The tenant's rules for outward messages and the cases a person answered in
        (ADR-0142). None: the shipped rules, and no case was answered."""
        """What masks every secret value the instance holds in a line. None: a trace is kept
        only where the composition root hands one, so a store without it keeps no line."""
        self._repeating: set[str] = set()
        """Runs whose current step the rule on repetition stopped: they halt with cause
        `repeated`."""
        self._declining: set[str] = set()
        """Runs whose anchored step a rule from precedent declined as it was raised: they halt
        with cause `declined` (ADR-0161)."""
        self._cooling: dict[str, datetime] = {}
        """Every model cooling down, by adapter, with when its cool-down ends: for every run and
        tenant this engine executes (ADR-0116 §5)."""
        self._moving: set[str] = set()
        """Runs whose current step went back to its boundary to move to the next model of its
        purpose's chain: it runs again at once (ADR-0116 §6)."""
        self._levels = levels
        """Where decisions and breaches are counted, and the lowered levels read (ADR-0110).
        None: nothing is counted, and no level falls by rule."""
        self._settled: set[tuple[str, str]] = set()
        """Steps that ended without their act — skipped or declined — in this process: no
        breach is looked for in them."""
        self._recordings = recordings or RecordedResponses(runs, work, objects)
        self._replay = replay
        """What answers every step of a rehearsal that would leave the engine, from a recorded
        run (ADR-0108). None: a rehearsal answers its outward operations from the tenant's
        recordings and runs everything else as any run does (ADR-0030)."""
        self._clock = clock
        self._ids = ids
        self._telemetry = telemetry
        self._queue = queue
        self._options = options or EngineOptions()
        self._stop_requested: set[str] = set()
        self._inflight: dict[str, tuple[Worker, str]] = {}
        self._inflight_step: dict[str, StepId] = {}
        """The step each run in `_inflight` is inside."""
        self._inflight_adapter: dict[str, tuple[Tenant, str]] = {}
        """The tenant and the adapter of the step each run in `_inflight` is inside: a stop of
        that adapter stops the step at its boundary (ADR-0138)."""
        self._message_digests: dict[str, str] = {}
        """The text's digest of every message this process read on a job, by its identifier:
        what a `message.received` is matched with (ADR-0156 §9)."""
        self._taking_over: dict[str, TakeoverAsked] = {}
        """Runs whose runner read a take-over asked on their job, with the ask (ADR-0128)."""
        self._answered: set[str] = set()
        """The take-overs served or refused in this process: an ask read again late is not
        served twice."""
        self._passed: set[str] = set()
        """Runs whose claim this process passed to a take-over: the runner's lease ends, and
        no claim is lost."""
        self._observed: dict[str, list[budgeting.Observation]] = {}
        self._limit_halts: set[str] = set()
        self._continued: dict[tuple[str, str], int] = {}
        """How often each step continued in a new unit after its worker stopped on its own,
        at its unit's wall clock (ADR-0102); at most CONTINUATIONS times."""
        self._immature: set[str] = set()
        """Runs whose current step was not run on an adapter below *verified*: they halt with
        cause `maturity` (NTC-0051)."""
        self._administration = administration or Administration()
        """The platform this instance runs on and what each credential declares it administers;
        a step naming a credential that administers this platform, or an undeclared one, is not
        run (ADR-0025, ADR-0052). Without a platform named nothing is checked."""
        self._administering: set[str] = set()
        """Runs whose current step was refused for a credential administering this instance's
        own platform: they halt with cause `administration`."""
        self._at_capacity: set[str] = set()
        self._parked: set[str] = set()
        """Runs whose current step met its worker at capacity: they halt, or escalate once the
        step's ceiling passed, with cause `capacity` (ADR-0037)."""
        self._claim: ContextVar[Claim | None] = ContextVar("claim", default=None)
        """The claim the run executing in this task is written under (#107). Held per task,
        not per run: a runner that lost a claim and claimed the same job again executes the
        run twice for a moment, and only the later claim may write."""
        self._last_attempt: ContextVar[bool] = ContextVar("last_attempt", default=False)
        """Whether the run executing in this task is at its job's last attempt (#591)."""

    # --- entry points --------------------------------------------------------------------------

    async def start(self, command: StartRun) -> Run:
        # One trace from the first entry to the last: every entry of this invocation carries it.
        async with self._telemetry.span("run", {"process.version": command.process_version}) as s:
            run = await self._create(command)
            s.set_attribute("run.id", run.id)
            return await self._execute(await self._launch(run), command.stop_after, s)

    async def submit(self, command: StartRun) -> Run:
        """Create the run and hand it to a runner: the run in state `planned` and the job that
        names it land in one transaction, so that a run without a job and a job without a run
        are both impossible. Which runner executes it, and when, is the queue's business."""
        if self._queue is None:
            raise RunError("no queue is wired; submit needs one, start does not")
        async with self._telemetry.span("run.submit", {"process.version": command.process_version}):
            return await self._create(command, enqueue=True)

    async def resume(self, command: ResumeRun) -> Run:
        last = self._last_attempt.set(command.last_attempt)
        try:
            if command.claim is None:
                return await self._resume(command)
            if self._queue is None:
                raise RunError(
                    "a resume under a claim needs the queue that fences it; none is wired"
                )
            token = self._claim.set(command.claim)
            try:
                return await self._resume(command)
            except ClaimLost:
                # The runner that took the job over executes the run; nothing here may.
                self._stop_requested.discard(command.run_id)
                raise
            finally:
                self._claim.reset(token)
        finally:
            self._last_attempt.reset(last)

    async def _resume(self, command: ResumeRun) -> Run:
        self._taking_over.pop(command.run_id, None)
        self._passed.discard(command.run_id)
        async with self._telemetry.span("run", {"run.id": command.run_id}) as span:
            async with self._work.transaction(command.tenant):
                run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            span.set_attribute("process.version", run.process_version)
            if command.on_claim:
                # A claim of a job a take-over held: its lease passed (ADR-0128 §6).
                run = await self._lapsed(run)
            if command.on_claim and _ended(run):
                return run
            if command.budget is not None and command.budget != run.budget:
                before = run.budget
                run = run.model_copy(update={"budget": command.budget})
                await self._state_budget(
                    run, command.actor, changed_from=before, reason=command.reason
                )
            if run.state is RunState.WAITING_HUMAN:
                # A decision applied while nobody continued the run takes effect here.
                run, declined = await self._apply_decisions(run)
                if declined is not None:
                    return await self._end(run, RunState.HALTED, Cause.DECLINED, declined, span)
            if run.state in RESUMABLE:
                run = await self._commit(
                    run.to(RunState.RUNNING), "run.resumed", actor=command.actor
                )
            elif run.state is RunState.PLANNED and run.in_flight() is None:
                run = await self._launch(run)  # submitted, never started: this is its start
            elif run.state in INTERRUPTIBLE:
                run = await self._recover(run, command.actor)
            else:
                raise UnknownRun(f"run {run.id!r} is {run.state} and cannot be resumed")
            return await self._execute(run, command.stop_after, span)

    async def _create(self, command: StartRun, *, enqueue: bool = False) -> Run:
        now = self._clock.now()
        run = Run(
            id=command.run_id or self._ids.new("run"),
            plan_id=command.plan.id,
            process_version=command.process_version,
            tenant=command.tenant,
            identity=command.identity,
            autonomy_level=command.plan.autonomy_level,
            actions=dict(command.actions),
            budget=command.budget,
            margin=self._options.margin if command.margin is None else command.margin,
            steps=command.plan.steps,
            work=command.work,
            inputs=dict(command.inputs),
            deadlines=()
            if self._deadlines is None
            else await self._deadlines.declared(command.tenant, command.process_version),
            rehearsal=command.rehearsal,
            bindings=dict(command.bindings),
            skills=await self._pinned(command),
            profile=command.profile,
            created_at=now,
            updated_at=now,
        )
        self._check_executable(run)
        run = await self._under_ceilings(run)
        job = None
        if enqueue:
            # A derived run gets a derived job: two creators of the same run collide on the
            # job's identifier even when neither saw the other's run (ADR-0035).
            job_id = (
                self._ids.new("job")
                if command.run_id is None
                else "job_" + command.run_id.removeprefix("run_")
            )
            job = Job(id=job_id, kind=RUN_EXECUTE, payload={"run_id": run.id})
        try:
            run = await self._commit(
                run,
                "run.created",
                actor=command.actor,
                enqueue=job,
                new=command.run_id is not None,
                trigger=command.trigger,
            )
        except PersistenceError as error:
            if command.run_id is not None and await self._exists(run.tenant, run.id):
                raise RunExists(run.id) from error
            raise
        await self._state_budget(run, command.actor)
        return run

    async def _pinned(self, command: StartRun) -> dict[str, str]:
        """The version of every skill the work names: the command's binding, else the version
        in production (ADR-0162 §5)."""
        named = sorted(
            {
                name
                for step_work in command.work.values()
                for name in (step_work.get(SKILLS) or ())
                if isinstance(name, str)
            }
        )
        if not named:
            return {}
        bound = {name: command.skills[name] for name in named if name in command.skills}
        found: Mapping[str, str] = {}
        rest = [name for name in named if name not in bound]
        if rest and self._guidance is not None:
            found = await self._guidance.production(command.tenant, rest)
        pinned = {name: version for name, version in bound.items() if version is not None}
        pinned.update({name: found[name] for name in rest if name in found})
        return pinned

    async def _guided(self, run: Run, work: Work, control: Control) -> Work:
        """The step's work with its brief extended by the skills it names, at the run's pins,
        and by the profile the run serves: before a model's system text, after a worker's goal
        (ADR-0162 §5, ADR-0163 §5). Every other kind of work is what it was."""
        if self._guidance is None or not isinstance(work, LlmWork | WorkerWork):
            return work
        blocks: list[str] = []
        if run.profile is not None:
            brief = await self._guidance.profile(run.tenant, run.profile)
            if brief:
                blocks.append(brief.strip())
        for name in control.skills:
            version = run.skills.get(name)
            if version is None:
                continue
            text = await self._guidance.skill(run.tenant, name, version)
            if text:
                blocks.append(f"Skill {name}@{version}:\n\n{text.strip()}")
        if not blocks:
            return work
        guidance = "\n\n".join(blocks)
        if isinstance(work, LlmWork):
            system = guidance if not work.system else f"{guidance}\n\n{work.system}"
            return work.model_copy(update={"system": system})
        task = work.task.model_copy(update={"goal": f"{work.task.goal}\n\n{guidance}"})
        return work.model_copy(update={"task": task})

    async def _exists(self, tenant: Tenant, run_id: str) -> bool:
        async with self._work.transaction(tenant):
            return await self._runs.get(tenant, run_id) is not None

    async def _state_budget(
        self,
        run: Run,
        actor: str | None,
        *,
        changed_from: Limits | None = None,
        reason: str | None = None,
    ) -> None:
        """Say what the budget can promise when it is set, not afterwards (principle 8): the
        budget, the margin, the line the run is held to, how each limited kind is held and
        why, the price table money is computed at, the weighting table the Takt is computed
        at, and the margin a worker without history
        reserves — with the statement, where an operator set it below the floor, that it is
        (DEC-0047) — one document, its digest in the
        ledger as `budget.set`, so that money stays recomputable from the ledger."""
        models: list[tuple[str, Calculability, bool]] = []
        worker_steps: list[str] = []
        for step in run.steps:
            work = parse_work(step, run.work.get(step.id), run.inputs)
            if isinstance(work, WorkerWork):
                worker_steps.append(step.id)
            pool = self._model_pool(run)
            if not isinstance(work, LlmWork) or pool is None:
                continue
            for resolved in await pool.chain(work.purpose):
                if any(m[0] == resolved.adapter for m in models):
                    continue
                prices = self._options.prices
                priced = prices is not None and (resolved.version or "") in prices.prices
                models.append((resolved.adapter, resolved.model.calculability(), priced))
        by_assignment = (
            [f"the worker step(s) {', '.join(worker_steps)}"]
            if worker_steps and run.budget.currency is not None
            else []
        )
        table = self._options.prices
        promises = budgeting.promise(run.budget, models, by_assignment, worker_steps, table)
        table_digest = None
        if table is not None:
            table_digest = await self._objects.put(_canonical(table.document()))
        weights = self._options.weights
        weights_digest = None
        if weights is not None:
            weights_digest = await self._objects.put(_canonical(weights.document()))
        statement = {
            "budget": run.budget.document(),
            "margin": run.margin,
            "held": budgeting.held(run.budget, run.margin).document(),
            "promises": [p.document() for p in promises],
            "models": [
                {"adapter": adapter, "declaration": c.document(), "priced": priced}
                for adapter, c, priced in models
            ],
            "price_table": None
            if table is None
            else {"version": table.version, "digest": table_digest},
            "weighting_table": None
            if weights is None
            else {
                "version": weights.version,
                "digest": weights_digest,
                "model_classes": dict(sorted(self._options.model_classes.items())),
            },
            "uncalibrated_margin": {
                "value": self._options.uncalibrated_margin,
                "floor": budgeting.MARGIN_FLOOR,
                "below_floor": budgeting.below_floor(self._options.uncalibrated_margin),
            },
        }
        if changed_from is not None:
            # A limit changed on resume: from what, and why — who changed it is the entry's actor.
            statement["changed"] = {"from": changed_from.document(), "reason": reason}
        digest = await self._objects.put(_canonical(statement))
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            await self._record(run, "budget.set", actor=actor, digest=digest)

    async def _launch(self, run: Run) -> Run:
        run = await self._commit(run.to(RunState.ADMITTED))
        return await self._commit(run.to(RunState.RUNNING), "run.started")

    async def _recover(self, run: Run, actor: str) -> Run:
        """The instance executing this run stopped without halting it. The step it was inside
        goes back to its last persisted boundary — the worker's checkpoint if one arrived, its
        start otherwise — and is admitted again; steps before it are kept as they are. That is
        the "at most one step of work is lost" of ADR-0005, made true across a restart.

        A worker step whose assignment was handed over keeps it open: before the step hands
        over another, the worker is asked about it, and an assignment it still holds is adopted
        instead of repeated (ADR-0038)."""
        interrupted = run.in_flight()
        if interrupted is not None:
            reason = "the instance stopped while this step was in flight"
            if interrupted.assignment_open:
                reason += (
                    f"; its assignment {interrupted.assignment_id} is asked about before "
                    "another is handed over"
                )
            interrupted = interrupted.to(
                StepState.STOPPED, reason=reason, finished_at=self._clock.now()
            )
            run = run.with_step_run(interrupted)
        if run.state is RunState.PLANNED:
            run = run.to(RunState.ADMITTED)
        if run.state is RunState.ADMITTED:
            run = run.to(RunState.RUNNING)
        return await self._commit(run, "run.recovered", step=interrupted, actor=actor)

    async def request_stop(self, run_id: str, tenant: Tenant | None = None) -> None:
        """Takes effect at the next step boundary. A running worker step is asked to stop as
        well and may finish up to the ceiling. With the tenant, a run that waits for a person
        halts at once: the stop applies at every autonomy level (UC-7.1)."""
        if tenant is not None:
            async with self._work.transaction(tenant):
                waiting_run = await self._runs.get(tenant, run_id)
            if waiting_run is not None and waiting_run.state is RunState.WAITING_HUMAN:
                await self._commit(
                    waiting_run.to(
                        RunState.HALTED, Cause.STOP, "stop requested while waiting for a person"
                    ),
                    "run.halted",
                    outcome=str(Cause.STOP),
                )
                return
        self._stop_requested.add(run_id)
        inflight = self._inflight.get(run_id)
        if inflight is not None:
            worker, assignment_id = inflight
            await worker.stop(
                assignment_id,
                StopRequest(
                    reason="stop requested", ceiling_seconds=self._options.step_ceiling_seconds
                ),
            )

    async def confirm(self, command: ConfirmSteps) -> Run:
        """A person's answer to steps the run waits for, each recorded with the person as its
        actor; then the run continues. Refused, changing nothing, when the run does not wait,
        when a step does not wait, or when the answer is not the one its level asks for."""
        async with self._telemetry.span("run", {"run.id": command.run_id}) as span:
            async with self._work.transaction(command.tenant):
                run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            span.set_attribute("process.version", run.process_version)
            if run.state is not RunState.WAITING_HUMAN:
                raise RunError(
                    f"run {run.id!r} is {run.state}: a step is answered while its run waits "
                    "for a person"
                )
            if not command.steps:
                raise RunError("name the step(s) to answer")
            if command.enqueue and self._queue is None:
                raise RunError("no queue is wired; a run is handed to a runner through one")
            if command.performed and command.rejected:
                raise RunError("a step is either performed or rejected; one at a time")
            unknown = sorted(set(command.corrected) - set(command.steps))
            if unknown:
                raise RunError(f"a correction names a step it does not answer: {unknown}")
            if command.rejected and command.corrected:
                raise RunError("a rejected step runs nothing, so nothing of it is corrected")
            if command.performed:
                # What a step a person performed hands on: nothing of Taktus's (ADR-0076).
                await self._objects.put(NO_RESULT)
            decisions: dict[StepId, _Decision] = {}
            answered: list[tuple[str, StepRun]] = []
            for step_id in dict.fromkeys(command.steps):
                kind, step_run, decision = self._answer(run, step_id, command)
                answered.append((kind, step_run))
                if decision is not None:
                    decisions[step_id] = decision
            run = self._corrected(run, decisions)
            for _, step_run in answered:
                # The wait on a person ends with the answer. Its record names no one; the
                # answer's own entry names who answered (ADR-0015, protective rule).
                run, _ = await self._close_block(run, run.step_run(step_run.step_id))
            answered = [(k, s.model_copy(update={"block": None})) for k, s in answered]
            for _, step_run in answered:
                run = run.with_step_run(step_run)
            for index, (kind, step_run) in enumerate(answered):
                job = None
                if command.enqueue and index == len(answered) - 1 and not command.rejected:
                    job = Job(id=self._ids.new("job"), kind=RUN_EXECUTE, payload={"run_id": run.id})
                decision = decisions.get(step_run.step_id)
                proposal = None if decision is None else await self._decision_record(run, decision)
                run = await self._commit(
                    run,
                    kind,
                    step=step_run,
                    actor=command.actor,
                    enqueue=job,
                    proposal=proposal,
                )
            for decision in decisions.values():
                await self._counted(run, decision)
            if command.rejected:
                reason = (
                    f"rejected by {command.actor}: "
                    + ", ".join(dict.fromkeys(command.steps))
                    + " not performed; resuming the run proposes it again"
                )
                return await self._end(run, RunState.HALTED, Cause.DECLINED, reason, span)
            if command.enqueue:
                return run
            run = await self._commit(run.to(RunState.RUNNING), "run.resumed", actor=command.actor)
            return await self._execute(run, command.stop_after, span)

    def _answer(
        self, run: Run, step_id: StepId, command: ConfirmSteps
    ) -> tuple[str, StepRun, _Decision | None]:
        """The step run as the person's answer leaves it, the kind of the answer's entry, and
        the decision on a proposal it is; None for an answer that decides no proposal."""
        try:
            step_run = run.step_run(step_id)
        except KeyError:
            raise RunError(f"run {run.id!r} has no step {step_id!r}") from None
        if step_run.state is not StepState.WAITING_HUMAN:
            raise RunError(f"step {step_id!r} is {step_run.state}; it does not wait for a person")
        if step_run.block is not None and step_run.block.awaited is not None:
            raise RunError(
                f"step {step_id!r} waits for its participant, {step_run.block.role}, to answer in "
                "their own channel: the answer is theirs, and nobody answers it here (ADR-0155)"
            )
        if step_run.anchoring is not None and not step_run.anchoring.proceeds:
            raise RunError(
                f"step {step_id!r} is anchored and waits for the decision request(s) "
                f"{', '.join(step_run.anchoring.requests)}: an anchored act is decided there, "
                "by the person the anchor names, not confirmed here (ADR-0042)"
            )
        if step_run.block is not None and step_run.block.cause == block.FELL_BACK:
            if command.rejected or step_id in command.corrected:
                raise RunError(
                    f"step {step_id!r} fell back to a person because its model was unsure: "
                    "there is no proposal to correct or reject. Perform it and report it "
                    "performed"
                )
            kind, performed = self._performed_after_fallback(step_run, command)
            return kind, performed, None
        held = self._held(run, run.step(step_id))
        level = held.level
        corrected = command.corrected.get(step_id)
        outcome: Literal["released", "corrected", "rejected"] = (
            "rejected" if command.rejected else "corrected" if corrected is not None else "released"
        )
        decision = _Decision(
            step_id=step_id,
            outcome=outcome,
            level=level,
            action=held.action,
            corrected=corrected,
        )
        if command.rejected:
            return (
                "step.declined",
                step_run.to(
                    StepState.PLANNED,
                    confirmed_by=None,
                    reason=f"rejected by {command.actor}: not performed; resuming the run "
                    "proposes it again",
                ),
                decision,
            )
        if level == 1 and not command.performed:
            raise RunError(
                f"step {step_id!r} runs at level 1: Taktus executes no act of it. Perform it "
                "yourself and report it performed"
            )
        if level != 1 and command.performed:
            raise RunError(
                f"step {step_id!r} runs at level {level}: it waits for a confirmation, and "
                "Taktus runs it once confirmed"
            )
        if command.performed:
            now = self._clock.now()
            how = "as Taktus proposed it" if corrected is None else "as the person corrected it"
            return (
                "step.performed",
                step_run.to(
                    StepState.SUCCEEDED,
                    confirmed_by=command.actor,
                    reason=f"performed by {command.actor}, {how} (level 1)",
                    started_at=now,
                    finished_at=now,
                ),
                decision,
            )
        return (
            "step.confirmed",
            step_run.to(StepState.PLANNED, confirmed_by=command.actor, reason=None),
            decision,
        )

    def _corrected(self, run: Run, decisions: Mapping[StepId, _Decision]) -> Run:
        """The run with the work a person released in place of a step proposed at level 2: the
        step runs with it. Refused, changing nothing, when the work does not hold to the
        step's method. At level 1 the person performed the act, and the work stays."""
        work = dict(run.work)
        for decision in decisions.values():
            if decision.corrected is None or decision.level == 1:
                continue
            step = run.step(decision.step_id)
            try:
                parse_work(step, decision.corrected, run.inputs)
            except (UnsupportedWork, ValueError) as error:
                raise RunError(
                    f"the correction of step {step.id!r} is no work its method runs: {error}"
                ) from error
            work[step.id] = dict(decision.corrected)
        return run if work == dict(run.work) else run.model_copy(update={"work": work})

    async def _decision_record(self, run: Run, decision: _Decision) -> tuple[str, str | None, str]:
        """The outcome, the action class and the digest of the decision's document: the
        proposal as `step.awaiting` put it down, and for a correction the version the person
        released, so that the change can be seen (UC-7.5 §2)."""
        async with self._work.transaction(run.tenant):
            entries = await self._ledger.entries(run.tenant, run.id)
        proposed = next(
            (
                e.content_digest
                for e in reversed(entries)
                if e.kind == "step.awaiting" and e.refs.step_id == decision.step_id
            ),
            None,
        )
        released: str | None = None
        if decision.corrected is not None:
            document: dict[str, Any] = {}
            if proposed is not None:
                stored = await self._objects.get(proposed)
                if stored is not None:
                    document = dict(json.loads(stored))
            document["work"] = dict(decision.corrected)
            released = await self._objects.put(_canonical(document))
        record = {
            "run_id": run.id,
            "step_id": decision.step_id,
            "outcome": decision.outcome,
            "level": decision.level,
            "action": decision.action,
            "proposal": proposed,
            "released": released,
        }
        digest = await self._objects.put(_canonical(record))
        return decision.outcome, decision.action, digest

    async def _counted(self, run: Run, decision: _Decision) -> None:
        """The governance component applies its rule to the decision (ADR-0110)."""
        if self._levels is None:
            return
        await self._levels.decided(
            run.tenant,
            ProposalDecided(
                process_version=run.process_version,
                run_id=run.id,
                step_id=decision.step_id,
                action=decision.action,
                level=decision.level,
            ),
        )

    def _performed_after_fallback(
        self, step_run: StepRun, command: ConfirmSteps
    ) -> tuple[str, StepRun]:
        """A step whose model was unsure went to its fallback, a person, at whatever level it
        runs (ADR-0076). The person performs it; nothing is confirmed, because confirming would
        pass on the answer the model did not stand behind. The step ends with no result of
        Taktus's: a dependant that reads it receives nothing, and its predictions stay an
        artifact nobody reads."""
        if not command.performed:
            raise RunError(
                f"step {step_run.step_id!r} fell back to a person because its model was unsure, "
                "and its answer leaves the step for nothing. Perform it yourself and report it "
                "performed"
            )
        now = self._clock.now()
        return "step.performed", step_run.to(
            StepState.SUCCEEDED,
            confirmed_by=command.actor,
            reason=f"performed by {command.actor}: its model was unsure, and it fell back to a "
            "person (ADR-0076)",
            finished_at=now,
            checkpoint=Checkpoint(
                ref=f"ckpt/{command.run_id}/{step_run.step_id}",
                step_id=step_run.step_id,
                taken_at=now,
                artifact_ids=tuple(a.id for a in step_run.artifacts),
                result_digest=_digest(NO_RESULT),
            ),
        )

    def _held(self, run: Run, step: Step) -> autonomy.Held:
        work = parse_work(step, run.work.get(step.id), run.inputs)
        return autonomy.held(run.autonomy_level, run.actions, autonomy.actions_of(step, work))

    async def decide(self, command: DecideSteps) -> Run:
        """Continue a run whose anchored steps were decided. A run that does not wait, or whose
        requests are not all applied yet, is returned as it is: a decision that took effect is
        never lost, and one that has not yet changes nothing."""
        async with self._telemetry.span("run", {"run.id": command.run_id}) as span:
            async with self._work.transaction(command.tenant):
                run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            span.set_attribute("process.version", run.process_version)
            if run.state is not RunState.WAITING_HUMAN:
                return run
            if command.enqueue and self._queue is None:
                raise RunError("no queue is wired; a run is handed to a runner through one")
            before = run
            run, declined = await self._apply_decisions(run)
            if declined is not None:
                return await self._end(run, RunState.HALTED, Cause.DECLINED, declined, span)
            if run is before or run.runnable() is None:
                return run
            if command.enqueue:
                job = Job(id=self._ids.new("job"), kind=RUN_EXECUTE, payload={"run_id": run.id})
                return await self._commit(run, enqueue=job)
            run = await self._commit(run.to(RunState.RUNNING), "run.resumed", actor=command.actor)
            return await self._execute(run, command.stop_after, span)

    async def _apply_decisions(self, run: Run) -> tuple[Run, str | None]:
        """Every anchored step whose requests have all taken effect gets its verdict, each
        recorded as `step.decided` with the decider as actor. Returns the run and, when a step
        was declined, why the run halts."""
        if self._decisions is None:
            return run, None
        declined: list[str] = []
        for step_run in run.waiting():
            held = step_run.anchoring
            if held is None or held.verdict is not None:
                continue
            verdicts: list[Verdict] = []
            for request in held.requests:
                verdict = await self._decisions.verdict(run.tenant, request)
                if verdict is None or not verdict.applied:
                    break
                verdicts.append(verdict)
            if len(verdicts) != len(held.requests):
                continue
            decided = anchoring.verdict_of([v.option or "" for v in verdicts])
            by = verdicts[-1].decided_by
            settled = held.model_copy(update={"verdict": decided, "decided_by": by})
            entries = ", ".join(v.entry or "?" for v in verdicts)
            # The wait on the decision ends with the verdict, whichever it is (ADR-0043). A
            # declined act is then a person's choice, not a block.
            run, step_run = await self._close_block(run, step_run)
            if decided == PROCEED:
                level = self._held(run, run.step(step_run.step_id)).level
                updated = step_run.to(
                    StepState.PLANNED,
                    anchoring=settled,
                    reason=None,
                    # The decision is the person's confirmation of the step (level 2 and up);
                    # at level 1 the person still performs the act. A rule's is no person's.
                    confirmed_by=by
                    if level >= 2 and not any(v.by_rule for v in verdicts)
                    else step_run.confirmed_by,
                )
            elif self._continues(run, step_run.step_id):
                # The process acts on a decline itself (ADR-0088): the act is not performed,
                # and the step ends with what the person decided and answered.
                answers = [v.answer for v in verdicts if v.option != anchoring.PERFORM and v.answer]
                updated = step_run.model_copy(update={"anchoring": settled})
                run = run.with_step_run(updated)
                run, updated = await self._settle(
                    run,
                    updated,
                    {"declined": True, "by": by, "answer": "\n".join(answers) or None},
                    "declined",
                )
                for request, verdict in zip(held.requests, verdicts, strict=True):
                    run = await self._commit(
                        run,
                        "step.decided",
                        step=updated,
                        outcome=decided,
                        actor=verdict.decided_by,
                        decision=request,
                    )
                continue
            else:
                reason = (
                    f"declined by {by} ({entries}): the act of step {step_run.step_id} was "
                    "not performed; resuming the run asks again"
                )
                updated = step_run.to(StepState.REJECTED, anchoring=settled, reason=reason)
                declined.append(reason)
            run = run.with_step_run(updated)
            for request, verdict in zip(held.requests, verdicts, strict=True):
                run = await self._commit(
                    run,
                    "step.decided",
                    step=updated,
                    outcome=decided,
                    actor=verdict.decided_by,
                    decision=request,
                )
        return run, "; ".join(declined) or None

    async def _conditions(
        self, run: Run, control: Control
    ) -> tuple[list[Any], tuple[ProvenanceInput, ...]]:
        """The values a step's `when` tests. A part the referenced result does not carry is
        null: a skipped or an approved step's result has no `declined`, and a condition over it
        then does not hold rather than fail the step (ADR-0088)."""
        values: list[Any] = []
        read: list[ProvenanceInput] = []
        for condition in control.when:
            try:
                (value,), inputs = await self._resolved(run, [condition.value])
            except RuleFailed:
                value, inputs = None, ()
            values.append(value)
            read.extend(i for i in inputs if i not in read)
        return values, tuple(read)

    def _continues(self, run: Run, step_id: StepId) -> bool:
        """Whether the step asks with `on_decline: continue` (ADR-0088)."""
        control = control_of(run.step(step_id), run.work.get(step_id), run.inputs)
        return control.ask is not None and control.ask.on_decline == "continue"

    def relinquish(self, run_id: str) -> None:
        """The runner's claim on the run is lost. The run stops at its next boundary, where the
        fence refuses whatever it would still write. The worker's assignment is not stopped:
        the runner that holds the claim now adopts it (ADR-0038). A claim this process passed to
        a take-over is not lost: nothing is asked of the run (ADR-0128)."""
        if run_id in self._passed:
            return
        self._stop_requested.add(run_id)

    async def record_claim_lost(self, tenant: Tenant, run_id: str) -> None:
        """A runner learned that it lost its claim on the run: `run.claim_lost` in the run's
        chain, with outcome `lost` (ADR-0106 §2). Written outside the claim: the run is another
        runner's now, and the entry changes nothing of it. It names the run and nothing that
        could name a runner, a host or a person."""
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
            if run is not None:
                await self._record(run, CLAIM_LOST, outcome="lost")

    # --- steering (ADR-0156) ----------------------------------------------------------------------

    async def steer(self, command: SteerStep) -> str:
        """A person's message to a running step (ADR-0156 §7). Returns the message's
        identifier. Refused with `MessageRefused`, writing nothing, unless the step is a running
        `worker` step of a run a runner holds and its worker declares steering."""
        if self._queue is None:
            raise MessageRefused(
                "no queue is wired: a message reaches a step through the runner that holds its run"
            )
        if not command.text.strip() or len(command.text) > MESSAGE_LENGTH:
            raise MessageRefused(
                f"a message carries a text of 1 to {MESSAGE_LENGTH} characters, not "
                f"{len(command.text)}"
            )
        async with self._work.transaction(command.tenant):
            run = await self._runs.get(command.tenant, command.run_id)
        if run is None:
            raise UnknownRun(command.run_id)
        step_run = self._steerable(run, command.step_id)
        step = run.step(command.step_id)
        try:
            resolved = await self._worker_pool(run).resolve(step.required_capabilities)
            supports = None if resolved is None else (await resolved.worker.capabilities()).supports
        except WorkerError as error:
            raise MessageRefused(
                f"the worker of step {step.id!r} could not be asked whether it takes messages: "
                f"{error}"
            ) from error
        if resolved is None or supports is None or not supports.steering:
            named = step_run.adapter or ("none" if resolved is None else resolved.adapter)
            raise MessageRefused(
                f"the worker {named} of step {step.id!r} declares no steering: it takes no "
                "message while it runs"
            )
        digest = await self._objects.put(command.text.encode())
        message_id = self._ids.new("msg")
        async with self._work.transaction(command.tenant):
            run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            step_run = self._steerable(run, command.step_id)
            placed = await self._queue.ask_message(
                run.tenant,
                run.id,
                AskedMessage(
                    message_id=message_id,
                    step_id=step_run.step_id,
                    digest=digest,
                    text=command.text,
                ),
            )
            if not placed:
                raise MessageRefused(
                    f"run {run.id!r} is not held by a runner, or a person holds it: a message "
                    "reaches a step only through the runner that executes it"
                )
            await self._record(
                run,
                MESSAGE_ASKED,
                step=step_run,
                outcome="asked",
                actor=command.actor,
                digest=digest,
                bare=True,
            )
        return message_id

    @staticmethod
    def _steerable(run: Run, step_id: StepId) -> StepRun:
        try:
            step_run = run.step_run(step_id)
        except KeyError:
            raise UnknownRun(f"run {run.id!r} has no step {step_id!r}") from None
        method = run.step(step_id).method
        if method is not Method.WORKER:
            raise MessageRefused(
                f"step {step_id!r} is a {method} step: only a worker step takes a message while "
                "it runs"
            )
        if run.state is not RunState.RUNNING or step_run.state is not StepState.RUNNING:
            raise MessageRefused(
                f"step {step_id!r} is {step_run.state} in a run that is {run.state}: a message "
                "reaches a step while it runs"
            )
        return step_run

    async def messages_asked(
        self, tenant: Tenant, run_id: str, claim: Claim, messages: Sequence[AskedMessage]
    ) -> None:
        """The runner holding the run read messages placed on its job (ADR-0156 §8). Each is
        handed to the worker of the step it is for, once, and marked handed in the transaction
        that records it, fenced by the claim."""
        if self._queue is None:
            return
        inflight = self._inflight.get(run_id)
        inside = self._inflight_step.get(run_id)
        for message in messages:
            self._message_digests[message.message_id] = message.digest
            outcome = "not_running"
            if inflight is not None and inside == message.step_id:
                worker, assignment_id = inflight
                # The text is kept here too, under the digest the ledger names it by.
                await self._objects.put(message.text.encode())
                try:
                    await worker.steer(
                        assignment_id,
                        SteeringMessage(message_id=message.message_id, text=message.text),
                    )
                    outcome = "handed"
                except SteeringRefused:
                    outcome = "refused"
                except WorkerError:
                    continue  # unreachable for now: handed at the next renewal
            async with self._work.transaction(tenant):
                if not await self._queue.fence(tenant, claim):
                    return
                run = await self._runs.get(tenant, run_id)
                if run is None:
                    return
                named = next((s for s in run.step_runs if s.step_id == message.step_id), None)
                await self._queue.message_handed(tenant, claim.job_id, message.message_id)
                await self._record(
                    run,
                    MESSAGE_HANDED,
                    step=named,
                    outcome=outcome,
                    digest=message.digest,
                    bare=True,
                )

    async def _received(self, run: Run, step_run: StepRun, event: MessageReceived) -> StepRun:
        """The worker received a message at its boundary: it is an input of the step from here
        (ADR-0156 §9). A message the step run holds already is not counted twice."""
        if any(m.message_id == event.message_id for m in step_run.messages):
            return step_run
        digest = self._message_digests.get(event.message_id)
        if digest is None:
            digest = await self._asked_digest(run, event.message_id)
        if digest is None:
            return step_run  # no person sent it through this run: it is not an input of ours
        return step_run.model_copy(
            update={
                "messages": (
                    *step_run.messages,
                    ReceivedMessage(
                        message_id=event.message_id, digest=digest, received_at=event.ts
                    ),
                )
            }
        )

    async def _asked_digest(self, run: Run, message_id: str) -> str | None:
        """The digest of a message asked on the run's job, read from the queue: what a runner
        that adopted the step knows of a message another runner handed."""
        claim = self._claim.get()
        if claim is None or self._queue is None:
            return None
        async with self._work.transaction(run.tenant):
            asked = await self._queue.messages_asked(run.tenant, claim.job_id)
        return next((m.digest for m in asked if m.message_id == message_id), None)

    # --- take-over (ADR-0128) ---------------------------------------------------------------------

    async def take_over(self, command: TakeOver) -> str:
        """A person asks to take over a step while it runs (ADR-0128 §1). The ask is written on
        the run's job, for the first asker only; the runner that holds the job serves it at the
        step's next boundary. Returns the take-over identifier the person hands the result back
        under. Refused, writing nothing, unless the step is a running `worker` step of a run a
        runner holds and no take-over of the run is asked or held."""
        if self._queue is None:
            raise TakeoverRefused(
                "no queue is wired: a step is taken over from the runner that holds its run"
            )
        async with self._work.transaction(command.tenant):
            run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            try:
                step_run = run.step_run(command.step_id)
            except KeyError:
                raise UnknownRun(f"run {run.id!r} has no step {command.step_id!r}") from None
            method = run.step(command.step_id).method
            if method is not Method.WORKER:
                raise TakeoverRefused(
                    f"step {command.step_id!r} is a {method} step: only a worker step is taken "
                    "over while it runs"
                )
            if run.state is not RunState.RUNNING or step_run.state not in IN_FLIGHT:
                raise TakeoverRefused(
                    f"step {command.step_id!r} is {step_run.state} in a run that is {run.state}: "
                    "a step is taken over while it runs"
                )
            takeover_id = self._ids.new("tko")
            asked = await self._queue.ask_takeover(
                run.tenant, run.id, step_run.step_id, HOLDER + takeover_id
            )
            if not asked:
                raise TakeoverRefused(
                    f"run {run.id!r} is not held by a runner, or a take-over of it is asked or "
                    "held already"
                )
            await self._record(
                run, TAKEOVER_ASKED, step=step_run, outcome="asked", actor=command.actor, bare=True
            )
        return takeover_id

    async def takeover_asked(self, run_id: str, asked: TakeoverAsked) -> None:
        """The runner holding the run read a take-over asked on its job (ADR-0128 §2). The
        step asked for is stopped at its worker's next boundary, where the take-over is served
        or, if the step ended another way first, refused."""
        if asked.holder in self._answered or run_id in self._taking_over:
            return
        self._taking_over[run_id] = asked
        inflight = self._inflight.get(run_id)
        if inflight is not None and self._inflight_step.get(run_id) == asked.step_id:
            await self._stop_for_takeover(*inflight)

    async def stops_held(self, run_id: str) -> bool:
        """The runner holding the run reads the tenant's stops of adapters with every renewal
        of its lease (ADR-0138 §2). A run inside a step on a stopped adapter is asked to stop at
        its boundary; a running step is never aborted. Whether it was asked."""
        inside = self._inflight_adapter.get(run_id)
        if inside is None or run_id in self._stop_requested:
            return False
        tenant, adapter = inside
        if adapter not in await self._held_stops(tenant):
            return False
        await self.request_stop(run_id)
        return True

    async def _held_stops(self, tenant: Tenant) -> frozenset[str]:
        return frozenset() if self._stops is None else await self._stops.held(tenant)

    async def _not_stopped(
        self, run: Run, adapter: str, consumption: Consumption | None = None
    ) -> None:
        """Before every call to a connector and every question to a model: a held stop of the
        adapter keeps the call from being made, and the step stops at its boundary (ADR-0138,
        amendment)."""
        if adapter in await self._held_stops(run.tenant):
            raise _AdapterStopped(adapter, consumption)

    async def _at_stopped_adapter(
        self,
        run: Run,
        step_run: StepRun,
        adapter: str,
        span: Span,
        *,
        consumption: Consumption | None = None,
        handed: bool = True,
    ) -> tuple[Run, StepRun]:
        """The step is not handed to its stopped adapter, or does not call it: it stops at the
        boundary it was admitted from, keeping the checkpoint it had, and the run halts with
        cause `stop`. A wait stopped between two checks keeps its block, as a parked wait does,
        so that a resume counts its time from when it began and keeps what its checks used."""
        span.record_failure("adapter stopped")
        self._stop_requested.add(run.id)
        if step_run.block is not None and step_run.state is StepState.RUNNING:
            step_run = step_run.model_copy(
                update={
                    "block": step_run.block.model_copy(update={"next_check_at": self._clock.now()})
                }
            )
        step_run = step_run.to(
            StepState.STOPPED,
            adapter=adapter,
            consumption=consumption if consumption is not None else step_run.consumption,
            reason=f"the adapter {adapter} is stopped: the step was not handed to it"
            if handed
            else f"the adapter {adapter} is stopped: the step stopped before calling it",
            finished_at=self._clock.now(),
        )
        run = await self._commit(
            run.with_step_run(step_run), "step.finished", step=step_run, outcome="stopped"
        )
        return run, step_run

    def passed(self, run_id: str) -> bool:
        """Whether this process passed the run's claim to a take-over in its last execution: the
        job is the person's now, and the runner leaves it alone (ADR-0128 §4)."""
        return run_id in self._passed

    async def takeover_state(self, tenant: Tenant, run_id: str, takeover: str) -> Any:
        """The state a step was taken over in, as the person receives it (ADR-0128 §3). Refused
        with `UnknownTakeover` while the take-over is asked and not yet served, and once it was
        handed back or its lease lapsed."""
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
        if run is None:
            raise UnknownRun(run_id)
        for step_run in run.step_runs:
            held = None if step_run.block is None else step_run.block.takeover
            if held is None or held.id != takeover:
                continue
            artifact = step_run.artifact(held.state)
            content = None if artifact is None else await self._objects.get(artifact.digest)
            if content is None:
                raise UnknownTakeover(f"the state of {takeover!r} is not available here")
            return json.loads(content)
        raise UnknownTakeover(
            f"no step of run {run_id!r} is held under {takeover!r}: it is asked and not yet "
            "served, was handed back, or its lease lapsed"
        )

    async def _stop_for_takeover(self, worker: Worker, assignment_id: str) -> None:
        """Stop the step at its worker's next boundary. A worker that declares handover is
        asked for one instead: it stops there as well and leaves a `handover.state` artifact,
        which joins the step's artifacts and so the take-over's state. The person then
        receives what the worker knew, not only its checkpoint reference (ADR-0139 §4). A
        worker that cannot be asked, or refuses, is stopped as before."""
        reason = "a person takes the step over"
        ceiling = self._options.step_ceiling_seconds
        try:
            if (await worker.capabilities()).supports.handover:
                await worker.hand_over(
                    assignment_id, HandoverRequest(reason=reason, ceiling_seconds=ceiling)
                )
                return
        except WorkerError:
            pass
        await worker.stop(assignment_id, StopRequest(reason=reason, ceiling_seconds=ceiling))

    async def _taken_over(
        self, run: Run, step_run: StepRun, asked: TakeoverAsked, span: Span
    ) -> Run:
        """The step stopped at its worker's boundary: its state becomes an artifact, the step
        and the run wait for the person, and the claim passes to the take-over — one
        transaction under the runner's claim (ADR-0128 §2 to §4)."""
        claim = self._claim.get()
        queue = self._queue
        if claim is None or queue is None:
            await self._takeover_refused(run, asked, step_run)
            return await self._end(
                run, RunState.HALTED, Cause.STOP, "stopped for a take-over", span
            )
        if step_run.block is not None:
            run, step_run = await self._close_block(run, step_run)
        now = self._clock.now()
        seconds = self._options.takeover_lease_seconds
        until = now + timedelta(seconds=seconds)
        takeover_id = asked.holder.removeprefix(HOLDER)
        step = run.step(step_run.step_id)
        work = parse_work(step, run.work.get(step.id), run.inputs)
        inputs: Any = None
        if isinstance(work, WorkerWork):
            (inputs,), _ = await self._resolved(run, [work.task.inputs])
        state = {
            "kind": TAKEOVER_STATE,
            "takeover": takeover_id,
            "run_id": run.id,
            "step_id": step.id,
            "process_version": run.process_version,
            "held_until": until.isoformat(),
            "goal": work.task.goal if isinstance(work, WorkerWork) else None,
            "acceptance": list(work.task.acceptance) if isinstance(work, WorkerWork) else [],
            "inputs": inputs,
            "credentials": _credential_names(work),
            "checkpoint": None if step_run.checkpoint is None else step_run.checkpoint.ref,
            "artifacts": [
                {
                    "id": a.id,
                    "kind": a.kind,
                    "digest": a.digest,
                    "media_type": a.media_type,
                    "title": a.title,
                }
                for a in step_run.artifacts
            ],
        }
        content = _canonical(state)
        digest = await self._objects.put(content)
        artifact = Artifact(
            id=f"{takeover_id}.state",
            kind=TAKEOVER_STATE,
            digest=digest,
            media_type="application/json",
            size_bytes=len(content),
            title=f"The state of step {step.id} when a person took it over",
            created_at=now,
        )
        opened = OpenBlock(
            account="wait.human",
            cause=block.TAKEN_OVER,
            since=now,
            takeover=Takeover(
                id=takeover_id,
                job_id=claim.job_id,
                attempt=claim.attempt + 1,
                until=until,
                state=artifact.id,
            ),
        )
        held = step_run.to(
            StepState.WAITING_HUMAN,
            artifacts=(*step_run.artifacts, artifact),
            block=opened,
            reason=f"taken over by a person until {until:%Y-%m-%d %H:%M} UTC, under {takeover_id}",
        )
        run = run.with_step_run(held).to(
            RunState.WAITING_HUMAN,
            Cause.PERSON,
            f"waiting for a person: {step.id} — taken over",
        )

        async def passing() -> None:
            if not await queue.pass_claim(run.tenant, claim, asked.holder, seconds):
                raise ClaimLost(
                    f"run {run.id!r}: the claim on job {claim.job_id!r} could not pass to the "
                    "take-over; the write is refused"
                )

        run = await self._commit(
            run,
            TAKEN_OVER,
            step=held,
            outcome="taken_over",
            digest=digest,
            after=({"kind": "run.waiting_human", "outcome": str(Cause.PERSON)},),
            inside=passing,
        )
        self._taking_over.pop(run.id, None)
        self._answered.add(asked.holder)
        self._passed.add(run.id)
        self._stop_requested.discard(run.id)
        span.set_attribute("run.state", run.state)
        span.set_attribute("run.cause", Cause.PERSON)
        return run

    async def _takeover_refused(
        self, run: Run, asked: TakeoverAsked, step_run: StepRun | None
    ) -> None:
        """The step asked for ended another way before it stopped, or was not running when the
        runner read the ask: the ask is withdrawn, and the run goes on (ADR-0128 §2)."""
        self._taking_over.pop(run.id, None)
        self._answered.add(asked.holder)
        if step_run is not None and step_run.step_id == asked.step_id:
            outcome = str(step_run.state)
        else:
            outcome = "not_running"
        named = next((s for s in run.step_runs if s.step_id == asked.step_id), None)
        claim = self._claim.get()
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            if claim is not None and self._queue is not None:
                await self._queue.withdraw_takeover(run.tenant, claim.job_id, asked.holder)
            await self._record(run, TAKEOVER_REFUSED, step=named, outcome=outcome, bare=True)

    async def _lapsed(self, run: Run) -> Run:
        """A runner claimed a job a take-over held: the lease passed without a hand-back. The
        step goes back to its worker's checkpoint and continues there (ADR-0128 §6)."""
        for held in run.step_runs:
            if held.block is None or held.block.takeover is None:
                continue
            takeover = held.block.takeover
            now = self._clock.now()
            record = blocked.record(
                held.block,
                run_id=run.id,
                step_id=held.step_id,
                process_version=run.process_version,
                until=now,
            )
            digest = await self._objects.put(_canonical(record))
            back = held.to(
                StepState.STOPPED,
                block=None,
                reason=f"the take-over {takeover.id} lapsed at {takeover.until:%Y-%m-%d %H:%M} "
                "UTC without a hand-back: the step continues in its worker from its checkpoint",
                finished_at=now,
            )
            run = await self._commit(
                run.with_step_run(back),
                TAKEOVER_LAPSED,
                step=back,
                outcome="lapsed",
                before=(
                    {
                        "kind": blocked.RECORD_KIND,
                        "step": back,
                        "outcome": block.TAKEN_OVER,
                        "digest": digest,
                    },
                ),
            )
        return run

    async def hand_back(self, command: HandBack) -> Run:
        """The person hands back the result of a step they took over (ADR-0128 §5). Written
        under the take-over's claim, fenced as a runner's write is, in one transaction: the
        result as the step's artifact, the step succeeded with method `human`, its provenance,
        the end of its block, and the job released for the next runner. Refused, writing
        nothing, when no step is held under the take-over, or its lease lapsed and a runner
        took the step back."""
        queue = self._queue
        if queue is None:
            raise TakeoverRefused("no queue is wired: a step is handed back through the run's job")
        async with self._telemetry.span("run", {"run.id": command.run_id}) as span:
            async with self._work.transaction(command.tenant):
                run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            span.set_attribute("process.version", run.process_version)
            held = next(
                (
                    s
                    for s in run.step_runs
                    if s.block is not None
                    and s.block.takeover is not None
                    and s.block.takeover.id == command.takeover
                ),
                None,
            )
            if held is None or held.block is None or held.block.takeover is None:
                raise UnknownTakeover(
                    f"no step of run {run.id!r} is held under {command.takeover!r}: it was "
                    "handed back, or its lease lapsed and the step went back to its worker"
                )
            opened = held.block
            takeover = held.block.takeover
            step = run.step(held.step_id)
            work = parse_work(step, run.work.get(step.id), run.inputs)
            read: tuple[ProvenanceInput, ...] = ()
            if isinstance(work, WorkerWork):
                _, read = await self._resolved(run, [work.task.inputs])
            now = self._clock.now()
            content = _canonical(command.result)
            result = Artifact(
                id=f"{takeover.id}.result",
                kind=TAKEOVER_RESULT,
                digest=await self._objects.put(content),
                media_type="application/json",
                size_bytes=len(content),
                title=f"The result of step {step.id}, handed back by the person who took it over",
                created_at=now,
            )
            record = blocked.record(
                opened,
                run_id=run.id,
                step_id=held.step_id,
                process_version=run.process_version,
                until=now,
            )
            record_digest = await self._objects.put(_canonical(record))
            artifacts = (*held.artifacts, result)
            done = held.to(
                StepState.SUCCEEDED,
                method=Method.HUMAN,
                adapter=None,
                artifacts=artifacts,
                block=None,
                waiting_since=None,
                waits=0,
                confirmed_by=command.actor,
                reason=f"handed back by {command.actor} after a take-over",
                finished_at=now,
                checkpoint=Checkpoint(
                    ref=held.checkpoint.ref
                    if held.checkpoint is not None
                    else f"ckpt/{run.id}/{held.step_id}",
                    step_id=held.step_id,
                    taken_at=now,
                    artifact_ids=tuple(a.id for a in artifacts),
                ),
            )
            claim = Claim(
                job_id=takeover.job_id, claimant=HOLDER + takeover.id, attempt=takeover.attempt
            )

            async def releasing() -> None:
                await queue.release(run.tenant, claim.job_id, claim.claimant)

            token = self._claim.set(claim)
            try:
                return await self._commit(
                    run.with_step_run(done),
                    "step.finished",
                    step=done,
                    outcome="succeeded",
                    actor=command.actor,
                    trace=Trace(inputs=read),
                    before=(
                        {
                            "kind": blocked.RECORD_KIND,
                            "step": done,
                            "outcome": block.TAKEN_OVER,
                            "digest": record_digest,
                        },
                    ),
                    inside=releasing,
                )
            except ClaimLost as lost:
                raise TakeoverRefused(
                    f"the lease of {takeover.id} lapsed and a runner took step {step.id!r} back "
                    "to its worker; nothing was handed back"
                ) from lost
            finally:
                self._claim.reset(token)

    # --- the loop ------------------------------------------------------------------------------

    # --- replay (ADR-0108) -----------------------------------------------------------------------

    def _replaying(self, run: Run) -> bool:
        """Whether the run is a rehearsal this engine replays from a recorded run: every step
        that would leave the engine is resolved from the replay, never from a configured pool."""
        return run.rehearsal and self._replay is not None

    def _worker_pool(self, run: Run) -> WorkerPool:
        return self._replay.workers if self._replay is not None and run.rehearsal else self._workers

    def _connector_pool(self, run: Run) -> ConnectorPool | None:
        if self._replay is not None and run.rehearsal:
            return self._replay.connectors
        return self._connectors

    def _model_pool(self, run: Run) -> ModelPool | None:
        if self._replay is not None and run.rehearsal:
            return self._replay.models
        if self._models is None or not run.bindings:
            return self._models
        return BoundModels(self._models, run.bindings)

    # --- end of replay -----------------------------------------------------------------------

    def _check_executable(self, run: Run) -> None:
        """Every step has an executor and every `$from` names a dependency, before anything
        runs: a run never fails in the middle for a reason known at the start."""
        ancestors: dict[StepId, set[StepId]] = {}
        parsed: dict[StepId, tuple[Work, Control, list[Any]]] = {}
        for step in run.steps:
            ancestors[step.id] = set()
            for dependency in step.dependencies:
                ancestors[step.id] |= {dependency, *ancestors[dependency]}
            work = parse_work(step, run.work.get(step.id), run.inputs)
            control = control_of(step, run.work.get(step.id), run.inputs)
            values = [*referenced_values(work), *control.referenced()]
            parsed[step.id] = (work, control, values)
            for value in values:
                for referenced in references(value):
                    if referenced not in ancestors[step.id]:
                        raise UnsupportedWork(
                            step.id, f"$from {referenced!r} is not a dependency of this step"
                        )
        # What a step may see, as far as the process tells it (ADR-0130).
        analytic = frame.analytic_steps({step: control for step, (_, control, _) in parsed.items()})
        for step_id, (work, control, values) in parsed.items():
            found = frame.findings(work, control, values, analytic)
            if found:
                raise UnsupportedWork(step_id, "; ".join(found))
        # What an outward message is held to, as far as the process tells it (ADR-0142).
        worked = {step_id: referenced_values(work) for step_id, (work, _, _) in parsed.items()}
        methods = {step.id: step.method for step in run.steps}
        calling = frozenset(
            s for s, (work, _, _) in parsed.items() if isinstance(work, ConnectorRule)
        )
        for step_id, (_, control, _) in parsed.items():
            if control.message is None:
                continue
            checker = control.message.check
            checked = parsed.get(checker)
            found = messages.findings(
                control.message,
                ancestors=ancestors[step_id],
                drafts=messages.drafting(step_id, worked, methods),
                checked_reads=frozenset()
                if checked is None
                else frozenset(r for v in checked[2] for r in references(v)),
                connector_steps=calling,
            )
            if found:
                raise UnsupportedWork(step_id, "; ".join(found))
        aside = run.on_escalation()
        for step in run.steps:
            if step.id not in aside and ancestors[step.id] & aside:
                raise UnsupportedWork(
                    step.id,
                    "depends on a step that runs on escalation, which a run that does not "
                    "escalate never runs (ADR-0097)",
                )

    async def _execute(self, run: Run, stop_after: int | None, span: Span) -> Run:
        try:
            self._observed[run.id] = await self._observations(run.tenant)
            return await self._steps(run, stop_after, span)
        finally:
            self._observed.pop(run.id, None)
            self._taking_over.pop(run.id, None)
            self._limit_halts.discard(run.id)
            self._at_capacity.discard(run.id)
            self._moving.discard(run.id)
            self._immature.discard(run.id)
            self._administering.discard(run.id)
            self._repeating.discard(run.id)

    def _in_a_new_unit(self, run: Run, step_run: StepRun) -> bool:
        """Whether a step its worker stopped on its own continues in a new unit: at most
        CONTINUATIONS times a step, so that a worker that stops at once cannot loop. The run's
        money remains the bound on what the continuations spend."""
        key = (run.id, step_run.step_id)
        done = self._continued.get(key, 0)
        if step_run.checkpoint is None or done >= CONTINUATIONS:
            return False
        self._continued[key] = done + 1
        return True

    async def _steps(self, run: Run, stop_after: int | None, span: Span) -> Run:
        refused = await self._platform_refuses(None)
        if refused is not None:
            held_up = run.runnable()
            if held_up is not None:
                run, held_up = await self._open_block(
                    run, held_up, "limit.compute", block.REJECTED_BY_CAPACITY
                )
                run = run.with_step_run(held_up)
            return await self._end(run, RunState.HALTED, Cause.LIMIT, refused, span)
        capped = await self._capped(run, span)
        if isinstance(capped, tuple):
            return await self._end(capped[0], RunState.HALTED, Cause.PARKED, capped[1], span)
        run = capped
        completed_now = 0
        while (step_run := run.runnable()) is not None:
            step = run.step(step_run.step_id)
            run, step_run = await self._step_or_failed(run, step, step_run)
            asked = self._taking_over.get(run.id)
            if asked is not None:
                if (
                    asked.step_id == step_run.step_id
                    and step_run.state is StepState.STOPPED
                    and run.id not in self._at_capacity
                    and run.id not in self._parked
                    and run.id not in self._limit_halts
                ):
                    # Stopped at its worker's boundary for the person who takes it over.
                    return await self._taken_over(run, step_run, asked, span)
                await self._takeover_refused(run, asked, step_run)
            if step_run.state is StepState.WAITING_HUMAN:
                # The step waits for a person; the steps that do not depend on it run on.
                if run.id in self._stop_requested:
                    return await self._end(
                        run, RunState.HALTED, Cause.STOP, "stop requested at the boundary", span
                    )
                continue
            if step_run.state is StepState.REJECTED:
                if run.id in self._declining:
                    cause = Cause.DECLINED
                elif run.id in self._administering:
                    cause = Cause.ADMINISTRATION
                elif run.id in self._repeating:
                    cause = Cause.REPEATED
                elif run.id in self._immature:
                    cause = Cause.MATURITY
                else:
                    cause = Cause.NO_ESTIMATE if step_run.estimate is None else Cause.LIMIT
                self._immature.discard(run.id)
                self._administering.discard(run.id)
                self._repeating.discard(run.id)
                self._declining.discard(run.id)
                return await self._end(run, RunState.HALTED, cause, step_run.reason, span)
            if run.id in self._moving:
                # The step went back to its boundary to move to the next model of its
                # purpose's chain: it is admitted again at once (ADR-0116 §6).
                self._moving.discard(run.id)
                continue
            capacity = run.id in self._at_capacity
            self._at_capacity.discard(run.id)
            if step_run.state is StepState.FAILED:
                verdict = None if capacity else await self._healing(run, step, step_run)
                if verdict is not None and verdict.heals:
                    # Level 4: a known failure inside the frame is healed by Taktus, and the
                    # step is admitted again at once (ADR-0160).
                    run = await self._heal(run, step_run)
                    continue
                cause = Cause.CAPACITY if capacity else Cause.FAILURE
                reason = step_run.reason
                if verdict is not None and verdict.why_not is not None:
                    reason = f"{reason}; not healed: {verdict.why_not}"
                run = await self._escalating(run)
                return await self._end(run, RunState.ESCALATED, cause, reason, span)
            parked = run.id in self._parked
            self._parked.discard(run.id)
            if step_run.state is StepState.STOPPED:
                if capacity:
                    # Waiting at the boundary: the runner tries again after a delay (ADR-0037).
                    cause = Cause.CAPACITY
                elif parked:
                    # A wait step parked: the runner defers the job to its next check (ADR-0103).
                    cause = Cause.PARKED
                elif run.id in self._repeating:
                    cause = Cause.REPEATED
                elif run.id in self._limit_halts:
                    cause = Cause.LIMIT
                elif run.id not in self._stop_requested and self._in_a_new_unit(run, step_run):
                    # Its worker stopped on its own, at its unit's wall clock, with the work at
                    # its checkpoint: the step continues there in a new unit (ADR-0102).
                    continue
                else:
                    cause = Cause.STOP
                self._limit_halts.discard(run.id)
                self._repeating.discard(run.id)
                return await self._end(run, RunState.HALTED, cause, step_run.reason, span)
            completed_now += 1
            await self._breach(run, step, step_run)
            # The boundary: a stop requested meanwhile takes effect here.
            if run.id in self._stop_requested or (
                stop_after is not None and completed_now >= stop_after
            ):
                return await self._end(
                    run, RunState.HALTED, Cause.STOP, "stop requested at the boundary", span
                )
        waiting_for = run.waiting()
        if waiting_for:
            return await self._end(
                run,
                RunState.WAITING_HUMAN,
                Cause.PERSON,
                "waiting for a person: "
                + "; ".join(f"{s.step_id} — {s.reason}" for s in waiting_for),
                span,
            )
        for step_id in self._aside(run):
            aside = run.step_run(step_id)
            if aside.state in (StepState.PLANNED, StepState.REJECTED):
                run, _ = await self._settle(
                    run, aside, {"skipped": True, "because": "the run did not escalate"}, "skipped"
                )
        return await self._end(run, RunState.FINISHED, None, None, span)

    async def _healing(self, run: Run, step: Step, step_run: StepRun) -> healing.Healing:
        """Whether Taktus heals the step that failed: at level 4, a known failure inside the
        frame (ADR-0160, `domain.service.healing`)."""
        work = parse_work(step, run.work.get(step.id), run.inputs)
        held = autonomy.held(run.autonomy_level, run.actions, autonomy.actions_of(step, work))
        if held.level < healing.UNATTENDED or run.rehearsal:
            return healing.Healing(heals=False)
        healed = sum(
            1
            for entry in await self._entries(run)
            if entry.kind == healing.HEALED and entry.refs.step_id == step.id
        )
        return healing.healing(
            held.level,
            rehearsal=run.rehearsal,
            retryable=step_run.retryable,
            blocked=step_run.block is not None,
            repeatable=await self._repeatable(run, work),
            stop_requested=run.id in self._stop_requested,
            healed=healed,
        )

    async def _repeatable(self, run: Run, work: Work) -> bool:
        """Whether the step's call may be made again without a second effect: true for a step
        that calls nothing outward, and for an outward operation that recognises a repeat. An
        operation whose declaration cannot be read is not (ADR-0024)."""
        if isinstance(work, ConnectorRule):
            capability, name = work.capability, work.operation
        elif isinstance(work, WaitWork) and work.until is not None:
            capability, name = work.until.capability, work.until.operation
        else:
            return True
        pool = self._connector_pool(run)
        resolved = None if pool is None else await pool.resolve(capability)
        operation = None if resolved is None else resolved.declaration.operation(name)
        if operation is None:
            return False
        return not operation.outward or operation.repeatable

    async def _heal(self, run: Run, step_run: StepRun) -> Run:
        """The heal recorded as `step.healed`, with the failure it answered by digest; the step
        stays failed, and the loop admits it again, through admission as any retry
        (`step.retried`, ADR-0147 §4). What it led to is the step's next `step.finished`."""
        answered = {
            "failure": step_run.reason,
            "action": healing.RETRY,
            "attempt": step_run.attempt,
        }
        content = json.dumps(answered, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = await self._objects.put(content)
        return await self._commit(
            run, healing.HEALED, step=step_run, outcome=healing.RETRY, digest=digest
        )

    @staticmethod
    def _aside(run: Run) -> list[StepId]:
        """The steps that run on escalation, in the plan's order (ADR-0097)."""
        aside = run.on_escalation()
        return [step.id for step in run.steps if step.id in aside]

    async def _escalating(self, run: Run) -> Run:
        """The steps that run on escalation (ADR-0097), in the plan's order, after the step
        that failed and before the run ends escalated. A step runs when every step it depends
        on succeeded, and stays planned otherwise, for a later escalation of the same run. Each
        runs as any step does, through its boundary. One that fails, is refused or waits keeps
        none of the others from running, and the run escalates for the step that failed first
        all the same."""
        for step_id in self._aside(run):
            step_run = run.step_run(step_id)
            if step_run.done or step_run.state is StepState.WAITING_HUMAN:
                continue
            step = run.step(step_id)
            done = {s.step_id for s in run.step_runs if s.done}
            if any(dependency not in done for dependency in step.dependencies):
                continue
            run, _ = await self._step_or_failed(run, step, step_run)
        self._at_capacity.discard(run.id)
        self._limit_halts.discard(run.id)
        self._immature.discard(run.id)
        self._administering.discard(run.id)
        self._repeating.discard(run.id)
        return run

    async def _end(
        self, run: Run, state: RunState, cause: Cause | None, reason: str | None, span: Span
    ) -> Run:
        self._stop_requested.discard(run.id)
        asked = self._taking_over.get(run.id)
        if asked is not None:
            # The run ends this pass before the step asked for reached a boundary.
            await self._takeover_refused(run, asked, None)
        span.set_attribute("run.state", state)
        if cause is not None:
            span.set_attribute("run.cause", cause)
        outcome = "succeeded" if state is RunState.FINISHED else str(cause)
        ended: str | None = None
        if state is RunState.ESCALATED:
            ended = Ended.ERROR  # whatever its steps returned (ADR-0107 §2)
        elif state is RunState.FINISHED:
            ended = Ended.EMPTY if await self._found_nothing(run) else Ended.OK
        return await self._commit(
            run.to(state, cause, reason), f"run.{state}", outcome=outcome, ended=ended
        )

    async def _found_nothing(self, run: Run) -> bool:
        """Whether a step that marks its run empty was skipped because its `when` did not
        hold: the result it settled with says so (ADR-0088, ADR-0107 §2)."""
        marked = empty_markers(run.work)
        if not marked:
            return False
        results, _ = await self._results(run, set(marked))
        return any(
            isinstance(result, Mapping) and result.get("skipped") is True
            for result in results.values()
        )

    async def _step_or_failed(self, run: Run, step: Step, step_run: StepRun) -> tuple[Run, StepRun]:
        """The step executed; at the job's last attempt, a step that raises ends failed with
        what it raised. Before the last attempt the exception leaves the engine, the runner
        releases the job, and the next claim recovers the run (#591)."""
        try:
            return await self._execute_step(run, step, step_run)
        except ClaimLost:
            raise
        except Exception as error:
            if not self._last_attempt.get():
                raise
            failed = await self._raised(run, step.id, error)
            if failed is None:
                raise
            return failed

    async def _raised(
        self, run: Run, step_id: StepId, error: Exception
    ) -> tuple[Run, StepRun] | None:
        """The step that raised `error`, failed with it, as the store holds the run now: the
        step may have committed its start before it raised. None when the store no longer
        holds the run or the step has already ended otherwise."""
        async with self._work.transaction(run.tenant):
            stored = await self._runs.get(run.tenant, run.id)
        if stored is None:
            return None
        step_run = stored.step_run(step_id)
        if step_run.done and step_run.state is not StepState.FAILED:
            return None
        for flags in (
            self._at_capacity,
            self._parked,
            self._limit_halts,
            self._moving,
            self._immature,
            self._administering,
            self._repeating,
        ):
            flags.discard(run.id)
        step_run = step_run.to(
            StepState.FAILED,
            reason=(
                f"step {step_id} raised {type(error).__name__}: {error}, at the last attempt "
                "its job is given"
            ),
            finished_at=self._clock.now(),
        )
        run = await self._commit(
            stored.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
        )
        return run, step_run

    async def _execute_step(self, run: Run, step: Step, step_run: StepRun) -> tuple[Run, StepRun]:
        try:
            return await self._step_in_span(run, step, step_run)
        except Exception as error:
            # Whoever hears of it — the runner, its log — learns the step it came from (#589).
            error.add_note(f"in step {step.id} of run {run.id}")
            raise

    async def _step_in_span(self, run: Run, step: Step, step_run: StepRun) -> tuple[Run, StepRun]:
        async with self._telemetry.span(
            "step", {"run.id": run.id, "step.id": step.id, "step.method": step.method}
        ) as span:
            if step_run.block is not None and step_run.block.cause == block.HELD_BACK:
                # What it depended on no longer waits: the step can start (ADR-0043).
                run, step_run = await self._close_block(run, step_run)
            run = await self._take_lowered(run)
            work = parse_work(step, run.work.get(step.id), run.inputs)
            refusal = self._administration.refusal(step.id, _credential_names(work))
            if refusal is not None:
                return await self._refuse_administering(run, step_run, refusal, span)
            used = autonomy.actions_of(step, work)
            held = autonomy.held(run.autonomy_level, run.actions, used)
            span.set_attribute("autonomy.level", held.level)
            control = control_of(step, run.work.get(step.id), run.inputs)
            work = await self._guided(run, work, control)
            if control.when and step_run.state in (StepState.PLANNED, StepState.REJECTED):
                # Whether the step runs at all, before anything asks about it (ADR-0088).
                values, read = await self._conditions(run, control)
                because = rules.unheld(control.when, values)
                if because is not None:
                    return await self._settle(
                        run, step_run, {"skipped": True, "because": because}, "skipped", read
                    )
            # A replay asks the step's boundary as any run does (ADR-0108); a rehearsal from
            # the tenant's recordings asks none of it (NTC-0079).
            asks = not run.rehearsal or self._replaying(run)
            # An outward message's frame, before anyone is asked about it: a message the checks
            # or the independent check refuse is sent to nobody, and asks nobody (ADR-0142). A
            # rehearsal sends nothing and asks none of it.
            gate = (
                await self._message_gate(run, step, work, control)
                if isinstance(work, ConnectorRule) and not run.rehearsal
                else None
            )
            if gate is not None and gate.refused is not None:
                return await self._message_refused(run, step_run, *gate.refused, span)
            if asks and step_run.state in (StepState.PLANNED, StepState.REJECTED):
                # The step boundary, first: an anchor holds at every level (ADR-0042), and so
                # does what the process itself asks (ADR-0088).
                decided = step_run.anchoring is not None and step_run.anchoring.proceeds
                anchors = () if decided else await self._applying(run, used)
                if not decided and (framed := await self._outside_a_case(run, work, control)):
                    # Personal data outside a specific case: the frame's own anchor, at every
                    # level and whatever the tenant configured (ADR-0130).
                    anchors = (*anchors, framed)
                if not decided and gate is not None:
                    # A promise, a message that cannot be classified and mass sending: the
                    # frame's own anchors, at every level (ADR-0142 §5, §6).
                    anchors = (*anchors, *gate.anchors)
                asked = None if decided else control.ask
                if anchors or asked is not None:
                    return await self._anchor(run, step, step_run, held, anchors, asked)
            if isinstance(work, ParticipantWork) and step_run.state is StepState.PLANNED:
                # Asked of a participant outside the organisation, who answers in its own
                # channel; no level asks a person of the tenant about it (ADR-0155).
                return await self._participant(run, step, step_run, work, span)
            if asks and step_run.state is StepState.PLANNED:
                # The step boundary: what the level asks of a person, before anything starts.
                acting = held.level == 1 and autonomy.acts(work, await self._outward(run, work))
                awaited = autonomy.awaits(
                    held.level, acting=acting, confirmed=step_run.confirmed_by is not None
                )
                if awaited is not None:
                    return await self._await(run, step, step_run, held, awaited)
            if gate is not None and gate.message is not None:
                # Approved: a person who answered in the case stops it, and the delay and the
                # quiet hours hold it (ADR-0142 §8, §9).
                if await self._case_answered(run, gate):
                    return await self._message_answered(run, step_run, gate)
                if step_run.state is StepState.PLANNED or _holding(step_run):
                    held_until = self._held_until(step_run, gate.rules)
                    if held_until is not None:
                        return await self._hold_message(run, step_run, *held_until)
                if _holding(step_run):
                    run, step_run = await self._close_block(run, step_run)
            if isinstance(work, WorkerWork):
                return await self._worker_step(run, step, step_run, work, span, held)
            return await self._local_step(run, step, step_run, work, span, held)

    async def _under_ceilings(self, run: Run) -> Run:
        """The run with the ceilings the tenant's risk classes set on the tool actions its steps
        use, where they are lower than the run's own levels (ADR-0170). A ceiling is taken on
        when the run is created, as its levels are; a rehearsal is asked no level."""
        if self._anchors is None or run.rehearsal:
            return run
        used: list[str] = []
        for step in run.steps:
            try:
                work = parse_work(step, run.work.get(step.id), run.inputs)
            except (UnsupportedWork, ValueError):
                continue  # refused where the step runs, with the reason
            used.extend(autonomy.actions_of(step, work))
        ceilings = await self._anchors.ceilings(run.tenant, tuple(dict.fromkeys(used)))
        actions = dict(run.actions)
        for action, ceiling in sorted(ceilings.items()):
            if ceiling < min(actions.get(action, run.autonomy_level), run.autonomy_level):
                actions[action] = ceiling  # type: ignore[assignment]
        if actions == dict(run.actions):
            return run
        return run.model_copy(update={"actions": actions})

    async def _take_lowered(self, run: Run) -> Run:
        """The run with the levels its version was lowered to by rule, where they are lower
        than its own; each change recorded as `run.lowered` (ADR-0110). A rehearsal is asked
        no level, and takes on none."""
        if self._levels is None or run.rehearsal:
            return run
        lowered = await self._levels.lowered(run.tenant, run.process_version)
        changes: list[tuple[str | None, AutonomyLevel]] = []
        level = run.autonomy_level
        if lowered.level is not None and lowered.level < level:
            level = lowered.level
            changes.append((None, level))
        actions = dict(run.actions)
        for action, lower in sorted(lowered.actions.items()):
            if lower < min(actions.get(action, level), level):
                actions[action] = lower
                changes.append((action, lower))
        if not changes:
            return run
        run = run.model_copy(update={"autonomy_level": level, "actions": actions})
        for held_by, lower in changes:
            run = await self._commit(run, RUN_LOWERED, outcome=f"level_{lower}", action=held_by)
        return run

    async def _breach(self, run: Run, step: Step, step_run: StepRun) -> None:
        """After a step that acted: an anchor that names its act now, with no decision to
        perform it, is a breach, and the process falls one level (ADR-0110). A rehearsal acts
        on nothing outside; a step that ended without its act performed none."""
        if self._levels is None or self._anchors is None or run.rehearsal:
            return
        if (run.id, step.id) in self._settled:
            return
        if step_run.anchoring is not None and step_run.anchoring.proceeds:
            return
        work = parse_work(step, run.work.get(step.id), run.inputs)
        if not autonomy.acts(work, await self._outward(run, work)):
            return
        named = await self._applying(run, autonomy.actions_of(step, work))
        if not named:
            return
        await self._levels.breached(
            run.tenant,
            Breach(
                process_version=run.process_version,
                run_id=run.id,
                step_id=step.id,
                level=run.autonomy_level,
                anchors=tuple(a.id for a in named),
            ),
        )

    async def _applying(self, run: Run, used: tuple[str, ...]) -> tuple[Anchor, ...]:
        if self._anchors is None:
            return ()
        return await self._anchors.applying(run.tenant, anchoring.process_of(run), used)

    async def _anchor(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        held: autonomy.Held,
        anchors: tuple[Anchor, ...],
        asked: Ask | None = None,
        drafted: Callable[[int, date], Sequence[Draft]] | None = None,
    ) -> tuple[Run, StepRun]:
        """The step's act is anchored: one decision request per anchor, and one more where the
        process asks itself (ADR-0088), and the step waits before anything of it starts. A
        request that cannot be raised fails the step, without its act: the run escalates
        rather than run an anchored act or wait on nothing."""
        round = 1 if step_run.anchoring is None else step_run.anchoring.round + 1
        due = self._clock.now().date() + timedelta(days=self._options.decision_days)
        drafts = [anchoring.draft(run, step, held, a, round=round, due=due) for a in anchors]
        named = "; ".join(f"{a.class_} anchor {a.id}: {a.act}" for a in anchors)
        if drafted is not None:
            # A value above an approval's threshold, held for its role (ADR-0152).
            approvals = list(drafted(round, due))
            drafts.extend(approvals)
            named = "; ".join(
                filter(None, [named, *(f"approval by the role {d.decider}" for d in approvals)])
            )
        try:
            if self._decisions is None:
                raise NotRaised("no decision requests can be raised here")
            if asked is not None:
                (values,), _ = await self._resolved(run, [asked.values])
                try:
                    drafts.append(
                        anchoring.asked(run, step, held, asked, values, round=round, due=due)
                    )
                except RuleFailed as error:
                    raise NotRaised(f"what the step asks cannot be put: {error}") from error
                named = "; ".join(
                    filter(None, [named, f"asked by the process of the role {asked.role}"])
                )
            for draft in drafts:
                await self._decisions.raise_request(run.tenant, draft)
        except NotRaised as error:
            failed = step_run.to(
                StepState.FAILED,
                reason=f"anchored ({named}), and its decision request was not raised: {error}. "
                "The act was not performed",
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(failed), "step.failed", step=failed, outcome="not_raised"
            )
            return run, failed
        waiting_on = Anchoring(requests=tuple(d.id for d in drafts), round=round)
        roles = sorted({d.decider for d in drafts})
        addressed = ", ".join(f"the role {r}" for r in roles)
        # The anchored step waits for a person: a block on `wait.human`, addressed to the role
        # where one role decides it, and the steps behind it held back (ADR-0043).
        run, step_run = await self._open_block(
            run,
            step_run,
            "wait.human",
            block.AWAITING_DECISION,
            role=roles[0] if len(roles) == 1 else None,
        )
        step_run = step_run.to(
            StepState.WAITING_HUMAN,
            anchoring=waiting_on,
            reason=f"anchored ({named}): waits for the decision request(s) "
            f"{', '.join(waiting_on.requests)}, addressed to {addressed}, due {due.isoformat()}",
        )
        run = self._hold_back(run.with_step_run(step_run), step.id)
        for draft in drafts:
            run = await self._commit(
                run,
                "step.anchored",
                step=step_run,
                outcome=draft.class_,
                decision=draft.id,
            )
        return await self._answered_at_once(run, step, step_run)

    async def _answered_at_once(
        self, run: Run, step: Step, step_run: StepRun
    ) -> tuple[Run, StepRun]:
        """An anchored step whose every request took effect as it was raised — each answered by
        a rule from precedent a person adopted (ADR-0161) — is decided at once: it continues
        from its boundary, ends declined, or halts the run, as a person's decision would have
        it. One request still open, and the step waits."""
        held = step_run.anchoring
        if held is None or self._decisions is None:
            return run, step_run
        for request in held.requests:
            verdict = await self._decisions.verdict(run.tenant, request)
            if verdict is None or not verdict.applied:
                return run, step_run
        run, declined = await self._apply_decisions(run)
        decided = run.step_run(step.id)
        if declined is not None:
            self._declining.add(run.id)
            return run, decided
        if decided.state is StepState.PLANNED:
            return await self._execute_step(run, step, decided)
        return run, decided

    async def _settle(
        self,
        run: Run,
        step_run: StepRun,
        value: dict[str, Any],
        outcome: str,
        read: tuple[ProvenanceInput, ...] = (),
    ) -> tuple[Run, StepRun]:
        """The step ends without its act, with a result that says why (ADR-0088): skipped
        because its `when` did not hold, or declined by the person it asked. The result is
        stored as any result is, so that the steps after it read it through `$from`."""
        self._settled.add((run.id, step_run.step_id))
        content = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = await self._objects.put(content)
        now = self._clock.now()
        result = Artifact(
            id="result",
            kind="result",
            digest=digest,
            media_type="application/json",
            size_bytes=len(content),
            created_at=now,
        )
        settled = step_run.to(
            StepState.SUCCEEDED,
            artifacts=(result,),
            checkpoint=Checkpoint(
                ref=f"ckpt/{run.id}/{step_run.step_id}",
                step_id=step_run.step_id,
                taken_at=now,
                artifact_ids=(result.id,),
                result_digest=digest,
            ),
            reason=str(value.get("because") or value.get("answer") or outcome),
            started_at=step_run.started_at or now,
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(settled),
            "step.finished",
            step=settled,
            outcome=outcome,
            trace=Trace(inputs=read),
        )
        return run, settled

    async def _outside_a_case(self, run: Run, work: Work, control: Control) -> Anchor | None:
        """The frame's anchor where the step reads personal data outside a specific case: it
        has no case scope, is not analytic, and calls a capability its connector declares
        scoped or its tenant declares personal (ADR-0130). None otherwise."""
        if control.scope is not None or control.analytic is not None:
            return None
        for capability in frame.capabilities_of(work):
            pool = self._connector_pool(run)
            resolved = None if pool is None else await pool.resolve(capability)
            if frame.anchored(
                control, capability, personal=await self._personal(run, resolved, capability)
            ):
                return frame.personal_data(capability)
        return None

    async def _personal(
        self, run: Run, resolved: ResolvedConnector | None, capability: str
    ) -> bool:
        """Whether the capability serves personal data: its connector declares it scoped, or
        the tenant declares it personal."""
        if resolved is not None and resolved.declaration.honours_scope(capability):
            return True
        return self._sources is not None and await self._sources.personal(run.tenant, capability)

    async def _frame(
        self, run: Run, step_id: StepId, resolved: ResolvedConnector, operation: Operation
    ) -> CaseScope | None:
        """The case scope the call carries, once the frame admits the call; a refusal fails
        the step before anything is called, and is recorded as `frame.refused` (ADR-0130)."""
        control = control_of(run.step(step_id), run.work.get(step_id), run.inputs)
        if control.scope is None and control.analytic is None:
            return None
        capability = operation.capability
        free = (
            control.analytic is not None
            and self._sources is not None
            and await self._sources.free_of_personal_fields(run.tenant, capability)
        )
        refused = frame.refusal(
            control,
            capability,
            outward=operation.outward,
            personal=await self._personal(run, resolved, capability),
            honours_scope=resolved.declaration.honours_scope(capability),
            free=free,
        )
        if refused is not None:
            token, why = refused
            raise _StepFailed(
                reason=f"{operation.name} was not called: {why} (ADR-0130)",
                retryable=False,
                consumption=None,
                adapter=resolved.adapter,
                outcome="refused by the frame",
                frame=token,
            )
        return control.scope

    # --- an outward message (ADR-0142) ----------------------------------------------------------

    async def _message_rules(self, run: Run) -> MessageRules:
        if self._messages is None:
            return messages.SHIPPED
        return await self._messages.rules(run.tenant)

    def _drafts(self, run: Run, step_id: StepId) -> frozenset[StepId]:
        """The `llm` steps whose answers the step's work reads (ADR-0142 §1)."""
        values = {
            step.id: referenced_values(parse_work(step, run.work.get(step.id), run.inputs))
            for step in run.steps
        }
        return messages.drafting(step_id, values, {step.id: step.method for step in run.steps})

    async def _value(self, run: Run, value: Any) -> Any:
        """The value with its references resolved; None where one cannot be."""
        try:
            (resolved,), _ = await self._resolved(run, [value])
        except RuleFailed:
            return None
        return resolved

    async def _message_gate(
        self, run: Run, step: Step, work: ConnectorRule, control: Control
    ) -> _Gate | None:
        """What the frame of ADR-0142 holds an outward connector step to, read from the results
        before it and the tenant's rules; None for a step it does not hold."""
        pool = self._connector_pool(run)
        resolved = None if pool is None else await pool.resolve(work.capability)
        operation = None if resolved is None else resolved.declaration.operation(work.operation)
        if operation is None or not operation.outward:
            return None
        rules_ = await self._message_rules(run)
        recipients = messages.count(await self._value(run, control.recipients))
        anchors: list[Anchor] = []
        if messages.over_limit(recipients, rules_.recipient_limit):
            anchors.append(
                messages.mass_anchor(operation.capability, recipients, rules_.recipient_limit)
            )
        drafts = self._drafts(run, step.id)
        declared = control.message
        if declared is None and not (operation.effect is Effect.DELIVERY and drafts):
            if not anchors:
                return None
            return _Gate(rules=rules_, anchors=tuple(anchors))
        if declared is None:
            return _Gate(
                rules=rules_,
                refused=(
                    messages.UNDECLARED,
                    f"{operation.name} delivers what {', '.join(sorted(drafts))} drafted, and "
                    "the step declares no message frame: a message a model wrote is checked, "
                    "labelled and held by rule before it is sent (ADR-0142 §1)",
                ),
            )
        checks: dict[str, bool] = {}
        failing: list[str] = []
        for name, condition in declared.checks.items():
            why = rules.violated(condition, await self._value(run, condition.value))
            checks[name] = why is None
            if why is not None:
                failing.append(f"{name}: {why}")
        verdict = messages.verdict(await self._value(run, {"$from": declared.check}))
        promises = (
            None
            if declared.classification is None
            else messages.promised(await self._value(run, {"$from": declared.classification}))
        )
        case = declared.case or (None if control.scope is None else control.scope.subject)
        gate = _Gate(
            rules=rules_,
            message=declared,
            drafted=bool(drafts),
            case=case,
            record=messages.record(
                case=case,
                checks=checks,
                check=declared.check,
                verdict=verdict,
                classification=declared.classification,
                promises=promises,
                recipients=recipients,
                label=rules_.label if drafts else None,
                drafted=bool(drafts),
            ),
        )
        if failing:
            return gate.refusing(
                messages.CHECKS,
                "the send decision is the rule over the step's named checks, and "
                + "; ".join(failing)
                + ": nothing was sent (ADR-0142 §3)",
            )
        if verdict != messages.SEND:
            return gate.refusing(
                messages.REJECTED,
                f"the independent check {declared.check} answered "
                + ("reject" if verdict == messages.REJECT else "neither send nor reject")
                + ": nothing was sent (ADR-0142 §4)",
            )
        if drafts and rules_.label is None:
            return gate.refusing(
                messages.UNLABELLED,
                "a model drafted the message, and the tenant configured no label to send it "
                "with (taktusctl messages set --label): nothing was sent (ADR-0142 §7)",
            )
        if promises is None or promises:
            anchors.append(messages.promise_anchor(operation.capability, promises))
        return gate.anchored(tuple(anchors))

    async def _message_refused(
        self, run: Run, step_run: StepRun, token: str, reason: str, span: Span
    ) -> tuple[Run, StepRun]:
        """The message is sent to nobody: the step fails without its act and without a retry,
        and the run escalates to a person (ADR-0142)."""
        span.record_failure("message held")
        if _holding(step_run):
            run, step_run = await self._close_block(run, step_run)
        failed = step_run.to(
            StepState.FAILED, reason=reason, retryable=False, finished_at=self._clock.now()
        )
        run = await self._commit(
            run.with_step_run(failed),
            "step.finished",
            step=failed,
            outcome="failed",
            after=({"kind": messages.HELD, "step": failed, "outcome": token},),
        )
        return run, failed

    async def _case_answered(self, run: Run, gate: _Gate) -> bool:
        if self._messages is None or gate.case is None:
            return False
        return await self._messages.answered(run.tenant, anchoring.process_of(run), gate.case)

    async def _message_answered(
        self, run: Run, step_run: StepRun, gate: _Gate
    ) -> tuple[Run, StepRun]:
        """A person answered in the case: the message is not sent, and the step ends without
        its act (ADR-0142 §9)."""
        if _holding(step_run):
            run, step_run = await self._close_block(run, step_run)
        run, settled = await self._settle(
            run,
            step_run,
            {
                "sent": False,
                "because": "a person answered in the case, and the process sends nothing more "
                "in it (ADR-0142 §9)",
            },
            "held",
        )
        run = await self._commit(run, messages.HELD, step=settled, outcome=messages.ANSWERED)
        return run, settled

    def _held_until(
        self, step_run: StepRun, rules_: MessageRules
    ) -> tuple[datetime, str, datetime] | None:
        """When an approved message may be sent, what holds it, and since when it was
        approved, while that is still to come; None once it may be sent now. The hold counts
        from its block's start, so a restart or an early wake loses nothing; a wake inside the
        quiet hours holds it again until they end (ADR-0142 §8)."""
        now = self._clock.now()
        if _holding(step_run) and step_run.block is not None:
            moment = step_run.block.next_check_at or now
            held_by = messages.DELAY
            if moment <= now:
                ends = messages.quiet_until(now, rules_.quiet)
                if ends is None:
                    return None
                moment, held_by = ends, messages.QUIET_HOURS
            return moment, held_by, step_run.block.since
        moment, held_by = messages.send_at(now, rules_.delay_seconds, rules_.quiet)
        return None if moment <= now else (moment, held_by, now)

    async def _hold_message(
        self, run: Run, step_run: StepRun, until: datetime, held_by: str, approved: datetime
    ) -> tuple[Run, StepRun]:
        """The approved message waits at its boundary until `until`: its block, from the
        moment it was approved, is booked to `wait.external`, and the run parks for its runner
        to defer the job (ADR-0103)."""
        run, step_run = await self._open_block(
            run, step_run, "wait.external", block.HOLDING_MESSAGE, since=approved
        )
        if step_run.block is not None:
            step_run = step_run.model_copy(
                update={"block": step_run.block.model_copy(update={"next_check_at": until})}
            )
        self._parked.add(run.id)
        step_run = step_run.to(
            StepState.STOPPED,
            reason=f"an approved message, held until {until.isoformat()} by the tenant's "
            f"{'quiet hours' if held_by == messages.QUIET_HOURS else 'sending delay'} "
            "(ADR-0142 §8)",
            finished_at=self._clock.now(),
        )
        run = await self._commit(
            run.with_step_run(step_run), messages.DELAYED, step=step_run, outcome=held_by
        )
        return run, step_run

    async def _outward(self, run: Run, work: Work) -> bool | None:
        """Whether a connector call's operation is declared outward; None when it cannot be
        read, and for any other step."""
        pool = self._connector_pool(run)
        if not isinstance(work, ConnectorRule) or pool is None:
            return None
        resolved = await pool.resolve(work.capability)
        operation = None if resolved is None else resolved.declaration.operation(work.operation)
        return None if operation is None else operation.outward

    async def _await(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        held: autonomy.Held,
        awaited: autonomy.Awaits,
    ) -> tuple[Run, StepRun]:
        """The step waits for a person before anything of it starts. What it proposes is put
        down as a document — the step, its method, its work as declared, the level and what
        holds it — and `step.awaiting` names it by digest, with what the step waits for."""
        if awaited == autonomy.CONFIRMATION:
            reason = f"waits for a person to confirm it before it starts ({held.describe()})"
        else:
            reason = (
                f"Taktus proposes this act and does not execute it ({held.describe()}); a "
                "person performs it and reports it performed"
            )
        proposal = {
            "run_id": run.id,
            "step_id": step.id,
            "method": str(step.method),
            "level": held.level,
            "held_by": held.action or "process",
            "awaits": awaited,
            "work": dict(run.work.get(step.id) or {}),
        }
        digest = await self._objects.put(_canonical(proposal))
        cause = (
            block.AWAITING_CONFIRMATION
            if awaited == autonomy.CONFIRMATION
            else block.AWAITING_PERFORMANCE
        )
        run, step_run = await self._open_block(run, step_run, "wait.human", cause)
        step_run = step_run.to(StepState.WAITING_HUMAN, reason=reason)
        run = await self._commit(
            self._hold_back(run.with_step_run(step_run), step.id),
            "step.awaiting",
            step=step_run,
            outcome=awaited,
            digest=digest,
        )
        return run, step_run

    # --- an outside participant (ADR-0155) -------------------------------------------------------

    async def _participant(
        self, run: Run, step: Step, step_run: StepRun, work: ParticipantWork, span: Span
    ) -> tuple[Run, StepRun]:
        """The step waits for its participant to answer in the thread the step before it
        opened. A rehearsal asks nobody: the step ends rehearsed."""
        if run.rehearsal:
            return await self._settle(
                run, step_run, {"participant": work.participant, "rehearsed": True}, REHEARSED
            )
        try:
            (thread,), _ = await self._resolved(run, [work.thread])
        except RuleFailed as failure:
            return await self._failed_before(run, step_run, span, str(failure), None, None)
        if not isinstance(thread, str) or not thread.strip():
            return await self._failed_before(
                run,
                step_run,
                span,
                f"the thread {work.participant} answers in resolved to {thread!r}, not a text "
                "(ADR-0155)",
                None,
                None,
            )
        run, step_run = await self._open_block(
            run,
            step_run,
            "wait.external",
            block.AWAITING_PARTICIPANT,
            role=work.participant,
            awaited=Awaited(channel=work.channel, thread=thread.strip()),
        )
        step_run = step_run.to(
            StepState.WAITING_HUMAN,
            reason=f"waits for {work.participant} to answer in {work.channel} (ADR-0155)",
        )
        run = await self._commit(
            self._hold_back(run.with_step_run(step_run), step.id),
            "step.awaiting",
            step=step_run,
            outcome=participants.OUTCOME,
        )
        return run, step_run

    async def answer_participant(self, command: AnswerParticipant) -> ParticipantAnswered:
        """A participant's message in the thread a step waits in: read and said back, withdrawn,
        or — the same account's `yes` to a reading — recorded as the step's result, and the run
        continues (ADR-0155, ADR-0008). Refused, changing nothing, when the step does not wait
        for a participant in that channel."""
        async with self._telemetry.span("run", {"run.id": command.run_id}) as span:
            async with self._work.transaction(command.tenant):
                run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            try:
                step_run = run.step_run(command.step_id)
            except KeyError:
                raise RunError(f"run {run.id!r} has no step {command.step_id!r}") from None
            opened = step_run.block
            awaited = None if opened is None else opened.awaited
            if (
                opened is None
                or awaited is None
                or step_run.state is not StepState.WAITING_HUMAN
                or awaited.channel != command.channel
            ):
                raise RunError(
                    f"step {command.step_id!r} of run {run.id!r} does not wait for a participant "
                    f"in {command.channel}"
                )
            if command.enqueue and self._queue is None:
                raise RunError("no queue is wired; a run is handed to a runner through one")
            account = participants.account_digest(command.channel, command.account)
            if awaited.account is not None and awaited.account != account:
                return ParticipantAnswered(taken=False, outcome="other", say=None, run=run)
            role = opened.role or "participant"
            actor = f"participant:{role}"
            label = None
            if self._messages is not None:
                label = (await self._messages.rules(run.tenant)).label
            step = run.step(command.step_id)
            work = parse_work(step, run.work.get(command.step_id), run.inputs)
            options = work.options if isinstance(work, ParticipantWork) else ()
            said = participants.said(command.text)
            if said == "yes" and awaited.reading is not None:
                return await self._participant_recorded(
                    run, step_run, awaited, role, actor, command, label, span
                )
            if said == "no" and awaited.reading is not None:
                kept = awaited.model_copy(update={"reading": None})
                step_run = step_run.model_copy(
                    update={"block": opened.model_copy(update={"awaited": kept})}
                )
                run = await self._commit(
                    run.with_step_run(step_run),
                    participants.ANSWER_READ,
                    step=step_run,
                    outcome=participants.WITHDRAWN,
                    actor=actor,
                )
                say = participants.labelled(participants.withdrawn(), label)
                return ParticipantAnswered(
                    taken=True, outcome=participants.WITHDRAWN, say=say, run=run
                )
            reading = participants.read(command.text, options)
            if reading is None:
                kept = awaited.model_copy(update={"account": account, "reading": None})
                step_run = step_run.model_copy(
                    update={"block": opened.model_copy(update={"awaited": kept})}
                )
                run = await self._commit(
                    run.with_step_run(step_run),
                    participants.ANSWER_READ,
                    step=step_run,
                    outcome=participants.UNREAD,
                    actor=actor,
                )
                say = participants.labelled(participants.asked_back(options), label)
                return ParticipantAnswered(
                    taken=True, outcome=participants.UNREAD, say=say, run=run
                )
            document = {
                "participant": role,
                "answer": reading.answer,
                "option": reading.option,
                "answered_by": {"channel": command.channel, "account": command.account},
            }
            digest = await self._objects.put(_canonical(document))
            kept = awaited.model_copy(update={"account": account, "reading": digest})
            step_run = step_run.model_copy(
                update={"block": opened.model_copy(update={"awaited": kept})}
            )
            run = await self._commit(
                run.with_step_run(step_run),
                participants.ANSWER_READ,
                step=step_run,
                outcome=participants.READ,
                actor=actor,
                digest=digest,
            )
            say = participants.labelled(participants.reflected(reading), label)
            return ParticipantAnswered(taken=True, outcome=participants.READ, say=say, run=run)

    async def _participant_recorded(
        self,
        run: Run,
        step_run: StepRun,
        awaited: Awaited,
        role: str,
        actor: str,
        command: AnswerParticipant,
        label: str | None,
        span: Span,
    ) -> ParticipantAnswered:
        """The reading the participant confirmed becomes the step's result; the step succeeds
        with method `human`, and the run continues."""
        reading = awaited.reading
        if reading is None:  # unreachable: only a pending reading is confirmed
            raise RunError("there is no reading to confirm")
        content = await self._objects.get(reading) or b""
        run, step_run = await self._close_block(run, step_run)
        step_run = step_run.model_copy(update={"block": None})
        now = self._clock.now()
        result = Artifact(
            id="result",
            kind="result",
            digest=reading,
            media_type="application/json",
            size_bytes=len(content),
            created_at=now,
        )
        done = step_run.to(
            StepState.SUCCEEDED,
            method=Method.HUMAN,
            adapter=None,
            artifacts=(result,),
            confirmed_by=actor,
            reason=f"answered by {role} in {command.channel}, and confirmed there (ADR-0155)",
            started_at=step_run.started_at or now,
            finished_at=now,
            checkpoint=Checkpoint(
                ref=f"ckpt/{run.id}/{step_run.step_id}",
                step_id=step_run.step_id,
                taken_at=now,
                artifact_ids=(result.id,),
                result_digest=reading,
            ),
        )
        job = (
            Job(id=self._ids.new("job"), kind=RUN_EXECUTE, payload={"run_id": run.id})
            if command.enqueue
            else None
        )
        run = await self._commit(
            run.with_step_run(done),
            "step.finished",
            step=done,
            outcome="succeeded",
            actor=actor,
            enqueue=job,
        )
        say = participants.labelled(participants.recorded(), label)
        if not command.enqueue and run.state is RunState.WAITING_HUMAN and not run.waiting():
            run = await self._commit(run.to(RunState.RUNNING), "run.resumed", actor=actor)
            run = await self._execute(run, None, span)
        return ParticipantAnswered(taken=True, outcome="recorded", say=say, run=run)

    async def _unverified(
        self, run: Run, step: Step, adapter: str | None, held: autonomy.Held
    ) -> str | None:
        """Why a step at level 3 or above is not run on its adapter, or None when it may be:
        the adapter is *verified* or above, or no integration at all (NTC-0051, NTC-0079)."""
        if run.rehearsal or adapter is None or not autonomy.needs_verified(held.level):
            return None
        if self._maturities is None:
            return (
                f"step {step.id!r} runs at {held.describe()} on {adapter}, and no maturity "
                "record can be read here; from level 3 a step runs only on an adapter at "
                "verified or above (NTC-0051)"
            )
        standing = await self._maturities.standing(run.tenant, adapter)
        if standing.serves_from_level_three:
            return None
        missing = "; ".join(standing.missing) or "nothing recorded"
        return (
            f"step {step.id!r} runs at {held.describe()}, and its adapter {adapter} is "
            f"{standing.maturity}, below verified: {missing}. From level 3 a step runs only "
            "on an adapter at verified or above (NTC-0051)"
        )

    async def _refuse_unverified(
        self, run: Run, step_run: StepRun, adapter: str, reason: str, span: Span
    ) -> tuple[Run, StepRun]:
        """The step is not run on the adapter: rejected before anything starts, with the
        finding that names the step and the adapter."""
        span.record_failure("adapter below verified")
        self._immature.add(run.id)
        step_run = step_run.to(StepState.REJECTED, adapter=adapter, reason=reason)
        run = await self._commit(
            run.with_step_run(step_run),
            "step.rejected",
            step=step_run,
            outcome="rejected_by_maturity",
        )
        return run, step_run

    async def _refuse_administering(
        self, run: Run, step_run: StepRun, reason: str, span: Span
    ) -> tuple[Run, StepRun]:
        """The step names a credential that administers this instance's own platform, or one
        declared about nothing: rejected before anything starts (ADR-0052)."""
        span.record_failure("credential administers this platform")
        self._administering.add(run.id)
        step_run = step_run.to(StepState.REJECTED, reason=reason)
        run = await self._commit(
            run.with_step_run(step_run),
            "step.rejected",
            step=step_run,
            outcome="rejected_by_administration",
        )
        return run, step_run

    # --- a cap on open work (ADR-0132) ----------------------------------------------------------

    async def _capped(self, run: Run, span: Span) -> Run | tuple[Run, str]:
        """Before a run starts anything: the run as it may go on, or, where a cap of its
        process is reached, the run waiting at its first step with the reason (ADR-0132 §2).

        The run counts per kind the outcomes open outside, read through the cap's connector,
        and the process's runs in flight. A kind at its cap, or one whose count cannot be read,
        holds the run: its first step is blocked, booked to `wait.external` with cause
        `at_open_work_cap`, the facts are recorded as `open_work.capped`, and the run halts
        with cause `parked` until the cap's next check. A run that passes is recorded as
        `open_work.admitted` and is in flight until it ends. Recording it takes the tenant's
        ledger lock, and the runs in flight are read again under it: a run of the same process
        that passed meanwhile is counted, and the count is made again."""
        if self._open_work is None or run.rehearsal:
            return run
        if any(s.state is not StepState.PLANNED for s in run.step_runs):
            return run  # it started: it passed its caps before
        held_up = run.runnable()
        if held_up is None:
            return run
        caps = await self._open_work.caps(run.tenant, run.process_version)
        if not caps:
            return run
        process = open_work.process_of(run.process_version)
        flying = await self._in_flight(run, process)
        if run.id in flying:
            return run  # it passed before the instance stopped
        readings = {cap.kind: await self._count(run, held_up.step_id, cap) for cap in caps}
        for _ in range(RECOUNTS):
            counts = [
                open_work.Counted(
                    kind=cap.kind,
                    cap=cap.cap,
                    read=readings[cap.kind][0],
                    unread=readings[cap.kind][1],
                    in_flight=len(flying - {run.id}),
                )
                for cap in caps
            ]
            facts = open_work.document(
                counts, run_id=run.id, process_version=run.process_version, at=self._clock.now()
            )
            digest = await self._objects.put(_canonical(facts))
            reached = [c for c in counts if c.reached]
            if reached:
                return await self._wait_at_cap(run, held_up, caps, reached, digest)
            try:
                async with self._work.transaction(run.tenant):
                    await self._fence(run)
                    await self._record(run, open_work.ADMITTED, outcome="admitted", digest=digest)
                    now_flying = (await self._ledger.project(run.tenant, open_work.IN_FLIGHT)).of(
                        process
                    ) - {run.id}
                    if now_flying != flying - {run.id}:
                        raise _Recount(now_flying)
            except _Recount as recount:
                flying = recount.flying
                continue
            span.set_attribute("open_work", "admitted")
            if held_up.block is not None and held_up.block.cause == block.AT_OPEN_WORK_CAP:
                run, _ = await self._close_block(
                    run, held_up, open_work={c.kind: c.open for c in counts}
                )
            return run
        # Other runs of the process kept passing while this one counted: it waits a check.
        counts = [
            open_work.Counted(kind=c.kind, cap=c.cap, in_flight=len(flying), unread="recounting")
            for c in caps
        ]
        facts = open_work.document(
            counts, run_id=run.id, process_version=run.process_version, at=self._clock.now()
        )
        digest = await self._objects.put(_canonical(facts))
        return await self._wait_at_cap(run, held_up, caps, counts, digest)

    async def _in_flight(self, run: Run, process: str) -> frozenset[str]:
        async with self._work.transaction(run.tenant):
            return (await self._ledger.project(run.tenant, open_work.IN_FLIGHT)).of(process)

    async def _count(self, run: Run, step_id: StepId, cap: Cap) -> tuple[int | None, str | None]:
        """What the cap's reading answers as open outside, or why it could not be read. A
        reading is a read: an operation declared outward is never called for a count."""
        reading = cap.reading
        if reading is None:
            return None, None
        pool = self._connector_pool(run)
        resolved = None if pool is None else await pool.resolve(reading.capability)
        if resolved is None:
            return None, f"no connector serves {reading.capability}"
        operation = resolved.declaration.operation(reading.operation)
        if operation is None:
            return None, f"{resolved.adapter} does not offer {reading.operation}"
        if operation.outward:
            return None, f"{reading.operation} is not a read"
        if resolved.adapter in await self._held_stops(run.tenant):
            # A stopped connector is not called for a count either: the count is unread, and
            # the run waits at the cap until its next check (ADR-0138, amendment).
            return None, f"{resolved.adapter} is stopped"
        context = CallContext(
            tenant=run.tenant,
            identity=run.identity,
            run_id=run.id,
            step_id=step_id,
            attempt=1,
            idempotency_key=idempotency_key(run.id, step_id, 1),
            credentials=reading.credentials,
            autonomy_level=run.autonomy_level,
        )
        try:
            result = await resolved.connector.call(operation.name, context, dict(reading.input))
            return open_work.counted_from(result.output, reading.select), None
        except (CallFailed, ConnectorError, ValueError) as error:
            return None, f"{reading.operation}: {error}"[:300]

    async def _wait_at_cap(
        self,
        run: Run,
        held_up: StepRun,
        caps: Sequence[Cap],
        reached: Sequence[open_work.Counted],
        digest: Digest,
    ) -> tuple[Run, str]:
        """The run waits at its first step until the cap's next check; the facts are booked."""
        every = min(c.check_every_seconds for c in caps if c.kind in {r.kind for r in reached})
        now = self._clock.now()
        check_at = now + timedelta(seconds=every)
        run, held_up = await self._open_block(
            run, held_up, "wait.external", block.AT_OPEN_WORK_CAP, since=now
        )
        if held_up.block is not None:
            held_up = held_up.model_copy(
                update={"block": held_up.block.model_copy(update={"next_check_at": check_at})}
            )
        run = await self._commit(
            run.with_step_run(held_up),
            open_work.CAPPED,
            step=held_up,
            outcome="capped",
            digest=digest,
        )
        reason = (
            "the process's open work is at its cap — "
            + "; ".join(r.describe() for r in reached)
            + f". It counts again at {check_at.isoformat()} (ADR-0132)"
        )
        return run, reason

    # --- a stop to repetition (ADR-0132 §5) ----------------------------------------------------

    async def _book_call(
        self, run: Run, step_run: StepRun, operation: str, arguments: Mapping[str, Any]
    ) -> None:
        """An outward call is made now: its identity — the operation and the digest of its
        arguments — goes into the ledger first, so that a call that fails counts too."""
        if self._repetition is None:
            return
        digest = await self._objects.put(_canonical(repetition.identity(operation, arguments)))
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            await self._record(
                run, repetition.CONNECTOR_CALLED, step=step_run, outcome="called", digest=digest
            )

    async def _book_answer(self, run: Run, step_run: StepRun) -> None:
        """A language model answered the step."""
        if self._repetition is None:
            return
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            await self._record(run, repetition.MODEL_CALLED, step=step_run, outcome="answered")

    async def _repeated(self, run: Run, step_run: StepRun, work: Work) -> repetition.Stop | None:
        """At the step's boundary: whether the call it is about to make would cross the
        tenant's limit on repetition in this run. A rule over the run's ledger (ADR-0023)."""
        if self._repetition is None or run.rehearsal:
            return None
        if isinstance(work, ConnectorRule):
            if await self._outward(run, work) is not True:
                return None
            try:
                (arguments,), _ = await self._resolved(run, [work.input])
            except RuleFailed:
                return None  # the call fails at its own resolution, and is not made
            digest = _digest(_canonical(repetition.identity(work.operation, arguments)))
            limits = await self._repetition.limits(run.tenant)
            entries = await self._entries(run)
            made = repetition.calls(entries, digest)
            return repetition.stop("calls", work.operation, made, limits.calls)
        if isinstance(work, LlmWork):
            limits = await self._repetition.limits(run.tenant)
            entries = await self._entries(run)
            answered = repetition.answers(entries, step_run.step_id)
            return repetition.stop(
                "model_calls", f"purpose {work.purpose}", answered, limits.model_calls
            )
        return None

    async def _watch(self, run: Run, step_run: StepRun) -> repetition.Watch | None:
        """The rule over a worker's reports, seeded from the run's ledger (ADR-0144)."""
        if self._repetition is None or run.rehearsal:
            return None
        limits = await self._repetition.limits(run.tenant)
        return repetition.Watch.of(
            await self._entries(run),
            step_run.step_id,
            calls_limit=limits.calls,
            model_calls_limit=limits.model_calls,
        )

    async def _reported(
        self,
        run: Run,
        step_run: StepRun,
        watch: repetition.Watch,
        event: ToolCalled | ModelCalled,
    ) -> repetition.Stop | None:
        """A worker reported a call: its entry goes into the run's ledger, and the rule counts
        it. A local call, or one that says nothing of its effect, counts as a tool result only;
        a refused call was not made."""
        if isinstance(event, ModelCalled):
            await self._record_fenced(run, repetition.MODEL_CALLED, step_run, "answered")
            return watch.answered(f"worker {step_run.adapter or 'unnamed'}")
        if event.refused:
            return None
        if watch.resulted():
            await self._record_fenced(run, repetition.TOOL_RESULT, step_run, "returned")
        if event.effect != "outward":
            return None
        identity = repetition.reported(event.tool, event.arguments_digest)
        digest = await self._objects.put(_canonical(identity))
        await self._record_fenced(run, repetition.CONNECTOR_CALLED, step_run, "called", digest)
        return watch.called(digest, event.tool)

    async def _record_fenced(
        self, run: Run, kind: str, step_run: StepRun, outcome: str, digest: Digest | None = None
    ) -> None:
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            await self._record(run, kind, step=step_run, outcome=outcome, digest=digest)

    async def _stop_reporting(
        self,
        run: Run,
        step_run: StepRun,
        worker: Worker,
        assignment_id: str,
        stopped: repetition.Stop,
    ) -> None:
        """The rule fired on a worker's reports: the facts are recorded as
        `repetition.stopped`, the stop raises an incident, and the worker is asked to stop at
        its next boundary (ADR-0144). An assignment that ends before it keeps its end."""
        document = stopped.document(
            run_id=run.id, step_id=step_run.step_id, process_version=run.process_version
        )
        digest = await self._objects.put(_canonical(document))
        await self._record_fenced(run, repetition.STOPPED, step_run, stopped.rule, digest)
        if self._repetition is not None:
            await self._repetition.stopped(
                run.tenant,
                Repeated(
                    process_version=run.process_version,
                    run_id=run.id,
                    step_id=step_run.step_id,
                    rule="calls" if stopped.rule == "calls" else "model_calls",
                    action=stopped.action,
                    count=stopped.count,
                    limit=stopped.limit,
                ),
            )
        with contextlib.suppress(WorkerError):
            await worker.stop(
                assignment_id,
                StopRequest(
                    reason=stopped.reason(step_run.step_id)[:200],
                    ceiling_seconds=self._options.step_ceiling_seconds,
                ),
            )

    async def _entries(self, run: Run) -> Sequence[LedgerEntry]:
        async with self._work.transaction(run.tenant):
            return await self._ledger.entries(run.tenant, run.id)

    async def _stop_repeating(
        self, run: Run, step_run: StepRun, stopped: repetition.Stop, span: Span
    ) -> tuple[Run, StepRun]:
        """The rule fired: the step is stopped at its boundary before the call, the facts are
        recorded as `repetition.stopped`, and the stop raises an incident. The run halts with
        cause `repeated`. A resume stops it again until the tenant's limit allows the call."""
        span.record_failure("repeated")
        self._repeating.add(run.id)
        reason = stopped.reason(step_run.step_id)
        document = stopped.document(
            run_id=run.id, step_id=step_run.step_id, process_version=run.process_version
        )
        digest = await self._objects.put(_canonical(document))
        step_run = step_run.to(StepState.REJECTED, reason=reason)
        run = await self._commit(
            run.with_step_run(step_run),
            "step.rejected",
            step=step_run,
            outcome=repetition.REJECTED,
            after=(
                {
                    "kind": repetition.STOPPED,
                    "step": step_run,
                    "outcome": stopped.rule,
                    "digest": digest,
                },
            ),
        )
        if self._repetition is not None:
            await self._repetition.stopped(
                run.tenant,
                Repeated(
                    process_version=run.process_version,
                    run_id=run.id,
                    step_id=step_run.step_id,
                    rule="calls" if stopped.rule == "calls" else "model_calls",
                    action=stopped.action,
                    count=stopped.count,
                    limit=stopped.limit,
                ),
            )
        return run, step_run

    # --- blocked-time accounts ------------------------------------------------------------------

    async def _open_block(
        self,
        run: Run,
        step_run: StepRun,
        account: Account,
        cause: str,
        *,
        since: datetime | None = None,
        on: StepId | None = None,
        role: str | None = None,
        lacking: str | None = None,
        awaited: Awaited | None = None,
    ) -> tuple[Run, StepRun]:
        """The step is blocked from now — or from `since` — for this cause, unless it is
        already. A block it is in for another cause, or for another lack, ends first, with its
        record. The block is carried by the step run the caller commits (ADR-0043)."""
        if (
            step_run.block is not None
            and step_run.block.cause == cause
            and step_run.block.lacking == lacking
        ):
            return run, step_run
        if step_run.block is not None:
            run, step_run = await self._close_block(run, step_run)
        opened = OpenBlock(
            account=account,
            cause=cause,
            since=since or self._clock.now(),
            on=on,
            role=role,
            lacking=lacking,
            awaited=awaited,
        )
        return run, step_run.model_copy(update={"block": opened})

    async def _close_block(self, run: Run, step_run: StepRun, **more: Any) -> tuple[Run, StepRun]:
        """The block the step is in ended now. Its record goes into the object store, and
        `step.waited` names it by digest with the cause as outcome, in the transaction that
        clears it from the step run. Nothing happens for a step that is not blocked."""
        open_block = step_run.block
        if open_block is None and step_run.waiting_since is not None:
            # A wait at capacity begun before a step run carried its block (migration 0018).
            open_block = OpenBlock(
                account=waiting.ACCOUNT, cause=block.AT_CAPACITY, since=step_run.waiting_since
            )
        if open_block is None:
            return run, step_run
        document = blocked.record(
            open_block,
            run_id=run.id,
            step_id=step_run.step_id,
            process_version=run.process_version,
            until=self._clock.now(),
            **more,
        )
        digest = await self._objects.put(_canonical(document))
        step_run = step_run.model_copy(update={"block": None, "waiting_since": None, "waits": 0})
        run = await self._commit(
            run.with_step_run(step_run),
            blocked.RECORD_KIND,
            step=step_run,
            outcome=open_block.cause,
            digest=digest,
        )
        return run, step_run

    async def _lacking(
        self, run: Run, step_run: StepRun, lack: tuple[str, str] | None
    ) -> tuple[Run, StepRun]:
        """A step that failed for want of an adapter is blocked from now until it can start;
        one that failed for anything else is not (ADR-0046). A step met by the same lack again
        on a retry keeps the block it is in, so that its waiting is one stretch."""
        if lack is None:
            return run, step_run
        cause, lacking = lack
        return await self._open_block(run, step_run, block.LACK_ACCOUNT, cause, lacking=lacking)

    async def _lack_ends(self, run: Run, step_run: StepRun) -> tuple[Run, StepRun]:
        """The adapter the step lacked is there now: its block ends here, with its record."""
        if step_run.block is None or step_run.block.cause not in block.LACKS:
            return run, step_run
        return await self._close_block(run, step_run)

    def _hold_back(self, run: Run, waiting_on: StepId) -> Run:
        """Every step that depends on `waiting_on`, directly or through another, cannot start
        while it waits: each planned one not yet blocked is blocked from now, booked to
        `wait.dependency` (ADR-0043). A step already blocked keeps its block, so that no time is
        counted twice."""
        now = self._clock.now()
        behind = {waiting_on}
        for step in run.steps:  # in execution order: a dependency comes before its dependents
            if not any(d in behind for d in step.dependencies):
                continue
            behind.add(step.id)
            step_run = run.step_run(step.id)
            if step_run.state is StepState.PLANNED and step_run.block is None:
                held_back = OpenBlock(
                    account="wait.dependency", cause=block.HELD_BACK, since=now, on=waiting_on
                )
                run = run.with_step_run(step_run.model_copy(update={"block": held_back}))
        return run

    def _ended(self, step_run: StepRun, answered_by: str | None = None) -> dict[str, Any]:
        """What the end of a local step's block adds to its record: for a wait on a provider's
        limit, that the provider answered — and, where the step moved to another model of its
        purpose's chain, which one answered (ADR-0116 §6)."""
        if step_run.block is None or step_run.block.cause != block.AT_PROVIDER_LIMIT:
            return {}
        details = waiting.details(
            adapter=step_run.adapter,
            waits=step_run.waits,
            ended="answered",
            ceiling_seconds=self._options.capacity_ceiling_seconds,
        )
        if answered_by is not None and answered_by != step_run.adapter:
            details["answered_by"] = answered_by
        return details

    async def _at_limit(
        self, run: Run, step_run: StepRun, limited: _AtLimit, span: Span
    ) -> tuple[Run, StepRun]:
        """The model's provider answered at its rate limit. Nothing was produced: the step goes
        back to its boundary, and the run halts there with cause `capacity` for its runner to
        try again later, as for a worker at capacity (ADR-0037). The wait is booked to
        `limit.provider`. Past the ceiling the step fails, and the run escalates (ADR-0043).

        A provider that names its delay (`Retry-After`) has it recorded with the block, and the
        runner defers the job by it. A delay that reaches past the ceiling ends the wait now:
        the provider has said it will not answer within it (ADR-0043, amendment)."""
        span.record_failure("provider at its rate limit")
        if limited.moves:
            self._moving.add(run.id)
        else:
            self._at_capacity.add(run.id)
        now = self._clock.now()
        since = step_run.waiting_since or now
        waits = step_run.waits + 1
        ceiling = self._options.capacity_ceiling_seconds
        retry_after = limited.retry_after_seconds
        run, step_run = await self._open_block(
            run, step_run, "limit.provider", block.AT_PROVIDER_LIMIT, since=since
        )
        if step_run.block is not None:
            step_run = step_run.model_copy(
                update={
                    "block": step_run.block.model_copy(update={"retry_after_seconds": retry_after})
                }
            )
        step_run = step_run.model_copy(
            update={"adapter": limited.adapter, "waiting_since": since, "waits": waits}
        )
        past = waiting.over(since, now, ceiling)
        named_past = retry_after is not None and waiting.over(
            since, now + timedelta(seconds=retry_after), ceiling
        )
        if (past or named_past) and not limited.moves:
            run, step_run = await self._close_block(
                run,
                step_run,
                **waiting.details(
                    adapter=limited.adapter, waits=waits, ended="ceiling", ceiling_seconds=ceiling
                ),
            )
            stayed = (
                f"stayed at its rate limit for {(now - since).total_seconds():.0f}s"
                if past
                else f"asks to be asked again in {retry_after:.0f}s, past the ceiling"
            )
            step_run = step_run.to(
                StepState.FAILED,
                reason=f"the provider of {limited.adapter} {stayed}, {waits} times asked; the "
                f"ceiling is {ceiling}s: {limited.reason}",
                retryable=True,
                finished_at=now,
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.finished",
                step=step_run,
                outcome=block.AT_PROVIDER_LIMIT,
            )
            return run, step_run
        moving = " — moving to the next model of the purpose's chain" if limited.moves else ""
        step_run = step_run.to(
            StepState.STOPPED,
            reason=f"waiting for the provider of {limited.adapter} since {since.isoformat()} "
            f"({waits} times asked; ceiling {ceiling}s){moving}: {limited.reason}",
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(step_run),
            "step.waiting",
            step=step_run,
            outcome=block.AT_PROVIDER_LIMIT,
        )
        return run, step_run

    # --- rule and wait steps ---------------------------------------------------------------------

    async def _local_step(
        self, run: Run, step: Step, step_run: StepRun, work: Work, span: Span, held: autonomy.Held
    ) -> tuple[Run, StepRun]:
        # A rule, a wait or a connector call demands nothing of any limit that could be
        # estimated: admission is a formality, recorded so that every step run reads the same
        # in the ledger. A retry after a failure the connector called not retryable is a new
        # attempt with a new idempotency key; every other resume continues the attempt.
        attempt = step_run.attempt
        if step_run.state is StepState.FAILED and not step_run.retryable:
            attempt += 1
        # The model a wait at a provider's limit asked, before admission names the one the
        # step is routed to now (ADR-0116 §6).
        waited_on = step_run.adapter
        # A wait resumed — parked, or recovered after a restart — counts from when it began,
        # and what its earlier checks used stays counted (ADR-0103).
        resumed = step_run.state in (StepState.STOPPED, StepState.RUNNING)
        before = (
            step_run.consumption
            if step_run.state is StepState.STOPPED and _parked_wait(step_run)
            else None
        )
        try:
            demand = await self._demand(run, step, work)
        except _AdapterStopped as halted:
            # The connector or the model the step would call is stopped: nothing is called,
            # and the run halts at the step's boundary (ADR-0138, amendment).
            run, step_run = await self._lack_ends(run, step_run)
            return await self._at_stopped_adapter(run, step_run, halted.adapter, span, handed=False)
        except RuleFailed as failure:
            return await self._failed_before(run, step_run, span, str(failure), None, None)
        except _StepFailed as failure:
            return await self._failed_before(
                run,
                step_run,
                span,
                failure.reason,
                failure.adapter,
                failure.retryable,
                lack=failure.lack,
            )
        run, step_run = await self._lack_ends(run, step_run)
        unverified = await self._unverified(run, step, demand.adapter, held)
        if unverified is not None and demand.adapter is not None:
            return await self._refuse_unverified(run, step_run, demand.adapter, unverified, span)
        stopped = await self._repeated(run, step_run, work)
        if stopped is not None:
            return await self._stop_repeating(run, step_run, stopped, span)
        run, step_run, admitted = await self._admit(
            run, step, step_run, demand, span, retryable=None, attempt=attempt
        )
        if not admitted:
            return run, step_run
        step_run = step_run.to(StepState.RUNNING, started_at=self._clock.now())
        if isinstance(work, WaitWork):
            # A wait step's whole time is a block on the outside (ADR-0043). A recovered wait
            # keeps the block it began, so a restart loses none of its time.
            run, step_run = await self._open_block(
                run,
                step_run,
                "wait.external",
                block.WAITING_ON_CLOCK if work.until is None else block.WAITING_ON_STATE,
            )
        run = await self._commit(run.with_step_run(step_run), "step.started", step=step_run)
        trace = Trace()
        consumption: Consumption | None = None
        answered_by: str | None = None
        try:
            result_digest: str | None = None
            artifacts: tuple[Artifact, ...] = ()
            if isinstance(work, WaitWork):
                if work.until is None:
                    await self._wait_for(step_run, work.seconds, resumed=resumed)
                else:
                    step_run, consumption = await self._wait_until(
                        run, step_run, work.until, span, before, resumed=resumed
                    )
            else:
                value, trace, consumption, adapter = await self._evaluate(run, step_run, work, span)
                answered_by = adapter
                if adapter is not None:
                    step_run = step_run.model_copy(update={"adapter": adapter})
                if step.checks:
                    # The value counts only when the checks it declares pass (ADR-0152).
                    trace = await self._checked(run, step, step_run, work, value, trace, span)
                content = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
                result_digest = await self._objects.put(content)
                artifacts = (
                    Artifact(
                        id="result",
                        kind="result",
                        digest=result_digest,
                        media_type="application/json",
                        size_bytes=len(content),
                        created_at=self._clock.now(),
                    ),
                )
        except _AtLimit as limited:
            return await self._at_limit(run, step_run, limited, span)
        except _Parked as parked:
            return await self._park(run, step_run, parked)
        except _AdapterStopped as halted:
            # Stopped since the step was admitted, or between two checks of a wait: the next
            # call is not made (ADR-0138, amendment).
            return await self._at_stopped_adapter(
                run, step_run, halted.adapter, span, consumption=halted.consumption, handed=False
            )
        except RuleFailed as failure:
            span.record_failure("rule failed")
            run, step_run = await self._close_block(run, step_run, **self._ended(step_run))
            step_run = step_run.to(
                StepState.FAILED, reason=str(failure), finished_at=self._clock.now()
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        except _ChecksFailed as failure:
            # A check disagreed: nothing counts, no dependent step reads the value, and the
            # run escalates with the check, its parameters and what it compared (ADR-0014).
            span.record_failure("check failed")
            run, step_run = await self._close_block(run, step_run, **self._ended(step_run))
            step_run = step_run.to(
                StepState.FAILED,
                reason=failure.reason,
                consumption=consumption,
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome=CHECK_FAILED
            )
            return run, step_run
        except _ToApprove as approval:
            # The value is above an approval's threshold: it counts once a person of the role
            # confirms it, and the step waits at its boundary until then (UC-4.13).
            run, step_run = await self._close_block(run, step_run, **self._ended(step_run))
            step_run = step_run.model_copy(update={"consumption": consumption})
            return await self._anchor(run, step, step_run, held, (), drafted=approval.drafts)
        except _StepFailed as failure:
            span.record_failure(failure.outcome)
            run, step_run = await self._close_block(run, step_run, **self._ended(step_run))
            run, step_run = await self._lacking(run, step_run, failure.lack)
            if failure.moves:
                # The attempt failed on one model of the chain; the step moves to the next at
                # its boundary. A failure is not a block: none is booked (ADR-0116 §6).
                self._moving.add(run.id)
            step_run = step_run.to(
                StepState.FAILED,
                adapter=failure.adapter,
                consumption=failure.consumption,
                reason=failure.reason,
                retryable=failure.retryable,
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.finished",
                step=step_run,
                outcome="failed",
                interface=failure.interface,
                after=(
                    *(
                        ()
                        if failure.frame is None
                        else ({"kind": frame.REFUSED, "step": step_run, "outcome": failure.frame},)
                    ),
                    *(
                        ()
                        if failure.held is None
                        else ({"kind": messages.HELD, "step": step_run, "outcome": failure.held},)
                    ),
                ),
            )
            return run, step_run
        ended = self._ended(step_run.model_copy(update={"adapter": waited_on}), answered_by)
        run, step_run = await self._close_block(run, step_run, **ended)
        now = self._clock.now()
        checkpoint = Checkpoint(
            ref=f"ckpt/{run.id}/{step.id}",
            step_id=step.id,
            taken_at=now,
            artifact_ids=tuple(a.id for a in artifacts),
            result_digest=result_digest,
        )
        step_run = step_run.to(
            StepState.SUCCEEDED,
            artifacts=artifacts,
            checkpoint=checkpoint,
            consumption=consumption,
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(step_run),
            "step.finished",
            step=step_run,
            outcome=REHEARSED if trace.rehearsed else "succeeded",
            trace=trace,
        )
        if step.checks and not run.rehearsal:
            run = await self._sample(run, step, step_run)
        _measured(span, step_run)
        return run, step_run

    async def _checked(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        work: Work,
        value: Any,
        trace: Trace,
        span: Span,
    ) -> Trace:
        """The step's declared checks, applied to its value before it counts (ADR-0152). Every
        check a rule decides runs; one that fails raises `_ChecksFailed` naming every failure.
        Once all of them pass, an approval whose threshold the value exceeds raises `_ToApprove`
        unless a person already confirmed this very value. What a check read through a
        connector joins the step's trace, so that its provenance record names it with the
        moment it was read (ADR-0021)."""
        control = control_of(step, run.work.get(step.id), run.inputs)
        given = control.checking.select if control.checking is not None else None
        reads = control.checking.reads if control.checking is not None else {}
        digest = _digest(_canonical(value))
        try:
            judged = select(value, given)
        except KeyError:
            raise _ChecksFailed(
                f"step {step.id}: its checks judge the part {given!r} of its result, which it "
                "does not carry. Nothing counts (ADR-0014)"
            ) from None
        findings: list[checking.Finding] = []
        inputs = list(trace.inputs)
        approvals: list[tuple[int, Check]] = []
        for position, check in enumerate(step.checks or (), start=1):
            match check.kind:
                case CheckKind.BOUNDS:
                    findings.append(checking.bounds(position, check, judged))
                case CheckKind.RECONCILIATION | CheckKind.AGREEMENT:
                    read = await self._check_read(run, step_run, check, reads, span)
                    if isinstance(read, str):
                        findings.append(checking.Finding(position, check, False, read))
                        continue
                    other, source = read
                    inputs.append(source)
                    if check.kind is CheckKind.RECONCILIATION:
                        findings.append(checking.reconciliation(position, check, judged, other))
                    else:
                        findings.append(checking.agreement(position, check, judged, other))
                case CheckKind.RECOMPUTATION:
                    findings.append(
                        await self._recomputed(
                            run, step_run, work, position, check, value, trace, span
                        )
                    )
                case CheckKind.APPROVAL:
                    approvals.append((position, check))
                case CheckKind.SAMPLING:
                    pass  # after the fact: `_sample`, once the result counts
        failed = [finding for finding in findings if not finding.passed]
        if failed:
            raise _ChecksFailed(
                f"step {step.id}: "
                + "; ".join(finding.describe() for finding in failed)
                + ". Nothing counts: the value reaches no step after it (ADR-0014)"
            )
        if approvals and not run.rehearsal:
            self._approved_or_asked(run, step, step_run, judged, digest, approvals)
        return dataclasses.replace(trace, inputs=tuple(inputs))

    async def _recomputed(
        self,
        run: Run,
        step_run: StepRun,
        work: Work,
        position: int,
        check: Check,
        value: Any,
        trace: Trace,
        span: Span,
    ) -> checking.Finding:
        """A recomputation (DEC-0173, provisional): a rule or a statistic is evaluated again over
        the same inputs. A call is never made twice; its value is held to what the call
        answered, as the step's provenance records the reading by digest."""
        digest = _digest(_canonical(value))
        if isinstance(work, ConnectorRule):
            if not isinstance(value, Mapping) or "output" not in value:
                return checking.Finding(
                    position, check, False, "the call's value carries no answer to compare"
                )
            answered = _digest(_canonical(value["output"]))
            read = [i.digest for i in trace.inputs if i.kind is InputKind.SOURCE and i.digest]
            recorded = read[-1] if read else answered  # a write records no reading
            return checking.recomputation(position, check, recorded, answered)
        if isinstance(work, LlmWork | WaitWork):
            return checking.Finding(
                position,
                check,
                False,
                "a recomputation evaluates a rule or a statistic again; this step's value comes "
                "from a model, which does not give the same value again",
            )
        again, _, _, _ = await self._evaluate(run, step_run, work, span)
        return checking.recomputation(position, check, digest, _digest(_canonical(again)))

    async def _check_read(
        self,
        run: Run,
        step_run: StepRun,
        check: Check,
        reads: Mapping[str, CheckRead],
        span: Span,
    ) -> tuple[Any, ProvenanceInput] | str:
        """What a reconciliation or an agreement reads through its source at the moment of the
        check, with the source as a provenance input; or why it could not be read."""
        source = str(check.source)
        read = reads.get(source)
        if read is None:
            return (
                f"the step's work names no read for {source} under `checking.reads`; a check "
                "that cannot read its source passes nothing"
            )
        resolved = await self._connector(run, step_run.step_id, read.capability)
        operation = resolved.declaration.operation(read.operation)
        if operation is None:
            return f"{read.operation} is not an operation the connector for {source} declares"
        if operation.outward:
            return f"{read.operation} acts outward; a check only reads"
        document, done, _, _ = await self._connector_call(
            run,
            step_run,
            ConnectorRule(
                rule="connector",
                operation=read.operation,
                input=read.input,
                credentials=read.credentials,
            ),
            span,
        )
        try:
            answered = select(document["output"], read.select)
        except KeyError:
            return f"{read.operation} answered without the part {read.select!r}"
        sources = [i for i in done.inputs if i.kind is InputKind.SOURCE]
        return answered, sources[-1]

    def _approved_or_asked(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        value: Any,
        digest: str,
        approvals: Sequence[tuple[int, Check]],
    ) -> None:
        """Nothing where no approval's threshold is exceeded, or a person of its role confirmed
        this value; `_ToApprove` with the requests to raise otherwise."""
        held = step_run.anchoring
        asking: list[tuple[int, Check]] = []
        for position, check in approvals:
            above = checking.above_threshold(check, value)
            if above is None:
                raise _ChecksFailed(
                    f"step {step.id}: check {position} ({checking.parameters(check)}) failed: "
                    f"the value {checking.text(value)[:120]} is not a number a threshold "
                    "judges. Nothing counts (ADR-0014)"
                )
            if not above:
                continue
            key = checking.approval_key(position, digest)
            if (
                held is not None
                and held.proceeds
                and anchoring.request_id(run.id, step.id, key, held.round) in held.requests
            ):
                continue
            asking.append((position, check))
        if not asking:
            return

        def drafts(round: int, due: date) -> list[Draft]:
            return [
                anchoring.approval(
                    run,
                    step,
                    check,
                    checking.text(value),
                    checking.approval_key(position, digest),
                    round=round,
                    due=due,
                )
                for position, check in asking
            ]

        raise _ToApprove(drafts)

    async def _sample(self, run: Run, step: Step, step_run: StepRun) -> Run:
        """After the result counts: each sampling check that chooses it puts it to a person of
        its role, and the ledger records the sample as `check.sampled` naming the request
        (UC-4.13, the row *sampling*). Nothing waits: the run goes on, and the verdict is read
        later."""
        if self._decisions is None:
            return run
        due = self._clock.now().date() + timedelta(days=self._options.decision_days)
        for position, check in enumerate(step.checks or (), start=1):
            if check.kind is not CheckKind.SAMPLING:
                continue
            if not checking.sampled(check, run.id, step.id):
                continue
            draft = anchoring.sample(run, step, check, checking.sample_key(position), due=due)
            try:
                await self._decisions.raise_request(run.tenant, draft)
            except NotRaised:
                continue  # the result counted; a sample not put is one sample less, not a failure
            run = await self._commit(
                run, SAMPLED, step=step_run, outcome=f"check_{position}", decision=draft.id
            )
        return run

    async def _evaluate(
        self, run: Run, step_run: StepRun, work: Work, span: Span
    ) -> tuple[Any, Trace, Consumption | None, str | None]:
        """The rule's value, what the rule read to produce it, what it consumed, and the
        adapter that served it where one did."""
        if isinstance(work, ConstantRule):
            return rules.constant(work), Trace(), None, None
        if isinstance(work, VerifyArtifactRule):
            producer = run.step_run(work.step)
            artifact = producer.artifact(work.artifact)
            content = None if artifact is None else await self._objects.get(artifact.digest)
            observed_at = self._clock.now()
            value = rules.verify_artifact(work, artifact, content)
            if artifact is None:  # unreachable: the rule refuses a missing artifact
                raise RuleFailed(f"step {work.step!r} produced no artifact {work.artifact!r}")
            verified = ProvenanceInput(
                kind=InputKind.ARTIFACT,
                run_id=run.id,
                step_id=producer.step_id,
                artifact_id=artifact.id,
                digest=artifact.digest,
                observed_at=observed_at,
            )
            return value, Trace(inputs=(verified,)), None, None
        if isinstance(work, CheckRule):
            values, read = await self._resolved(
                run, [condition.value for condition in work.conditions]
            )
            return rules.check(work, values), Trace(inputs=read), None, None
        if isinstance(work, ReadyRule):
            (issue, records, issues), read = await self._resolved(
                run, [work.issue, work.open_records, work.open_issues]
            )
            return rules.ready(work, issue, records, issues), Trace(inputs=read), None, None
        if isinstance(work, BacklogRule):
            (issues, records), read = await self._resolved(run, [work.issues, work.open_records])
            return rules.backlog(work, issues, records), Trace(inputs=read), None, None
        if isinstance(work, RoadmapRule):
            (text, issues), read = await self._resolved(run, [work.roadmap, work.issues])
            return rules.roadmap(work, text, issues), Trace(inputs=read), None, None
        if isinstance(work, SpamRule):
            (text,), read = await self._resolved(run, [work.text])
            return rules.spam(work, text), Trace(inputs=read), None, None
        if isinstance(work, ScreenRule):
            (text,), read = await self._resolved(run, [work.text])
            return rules.screen(work, text), Trace(inputs=read), None, None
        if isinstance(work, ClassificationRule):
            (answer, screened, versions), read = await self._resolved(
                run, [work.answer, work.screened, work.versions]
            )
            classified = rules.classification(work, answer, screened, versions)
            return classified, Trace(inputs=read), None, None
        if isinstance(work, TemplateRule):
            (values,), read = await self._resolved(run, [work.values])
            return rules.template(work, values), Trace(inputs=read), None, None
        if isinstance(work, ExtractRule):
            (values, excluding), read = await self._resolved(run, [work.values, work.excluding])
            return rules.extract(work, values, excluding), Trace(inputs=read), None, None
        if isinstance(work, CommitTitleRule):
            (title, number, labels, files, proposal), read = await self._resolved(
                run, [work.title, work.number, work.labels, work.files, work.proposal]
            )
            titled = rules.commit_title(work, title, number, labels, files, proposal)
            return titled, Trace(inputs=read), None, None
        if isinstance(work, InvoiceRule):
            (invoice, order), read = await self._resolved(run, [work.invoice, work.order])
            return invoices.invoice(invoice, order), Trace(inputs=read), None, None
        if isinstance(work, DeviationStatistic):
            (days,), read = await self._resolved(run, [work.days])
            return statistics.deviation(work, days), Trace(inputs=read), None, None
        if isinstance(work, ConnectorRule):
            return await self._connector_call(run, step_run, work, span)
        if isinstance(work, LlmWork):
            return await self._llm_step(run, step_run, work, span)
        raise UnsupportedWork(step_run.step_id, f"no evaluator for {type(work).__name__}")

    # --- estimate and admission -----------------------------------------------------------------

    def _line(self, run: Run) -> Limits:
        """The line the run is held to: its budget less its margin."""
        return budgeting.held(run.budget, run.margin)

    def _compute_table(self, run: Run) -> PriceTable | None:
        """The table the run's currency budget holds compute money at; None where it holds
        none — no currency budget, or one under which compute has no price (ADR-0005, fourth
        amendment)."""
        promised = budgeting.compute_money(run.budget, self._options.prices)
        held = promised is not None and promised.how == budgeting.HELD
        return self._options.prices if held else None

    def _spent(self, run: Run) -> ConsumptionQuantities:
        """What the run used and reserved, with the money of its compute seconds at the table
        where its currency budget holds it: money follows from the record, never stored."""
        consumed = run.consumed()
        table = self._compute_table(run)
        if table is None:
            return consumed
        return budgeting.with_money(consumed, run.compute_by_class(), table)[0]

    def _priced(self, run: Run, quantities: ConsumptionQuantities) -> ConsumptionQuantities:
        """A step's quantities with the money of its compute seconds, where it is held."""
        table = self._compute_table(run)
        if table is None or not quantities.compute_seconds or quantities.resource_class is None:
            return quantities
        seconds = {quantities.resource_class: quantities.compute_seconds}
        return budgeting.with_money(quantities, seconds, table)[0]

    def _per_second(self, run: Run, reservation: ConsumptionQuantities) -> tuple[str, float] | None:
        """The currency and the price of a second of the reservation's resource class, where
        the run's currency budget holds compute money: what the worker's ceiling is bought
        with."""
        table = self._compute_table(run)
        if table is None or table.compute is None or reservation.resource_class is None:
            return None
        price = table.compute.get(reservation.resource_class)
        return None if price is None else (table.currency, price)

    def _unpriced(self, run: Run, quantities: ConsumptionQuantities) -> str | None:
        """Why a step cannot be estimated in money under a currency budget, or None: its
        compute seconds have no price, or the compute the run already used has none, so what
        is left of the budget cannot be computed. Unpriced is never free (ADR-0010)."""
        if run.budget.currency is None:
            return None
        if not quantities.compute_seconds and not quantities.currency:
            return None
        promised = budgeting.compute_money(run.budget, self._options.prices)
        table = self._compute_table(run)
        if table is None:
            if not quantities.compute_seconds or promised is None:
                return None
            return f"the budget limits money and {promised.reason}"
        seconds = dict(run.compute_by_class())
        if quantities.compute_seconds:
            needed = quantities.resource_class or "an unnamed class"
            seconds[needed] = seconds.get(needed, 0.0) + quantities.compute_seconds
        missing = budgeting.with_money(quantities, seconds, table)[1]
        if not missing:
            return None
        return (
            f"the budget limits money and the price table {table.version} has no price for "
            + ", ".join(missing)
            + ": the step's cost, or what is left of the budget, cannot be computed"
        )

    async def _demand(self, run: Run, step: Step, work: Work) -> _Demand:
        """What a local step is estimated to use before it runs — or why it cannot be. A step
        whose adapter is not configured fails here, as it would when called, and its reason
        says which; a step whose adapter cannot estimate is refused by the caller."""
        if isinstance(work, WaitWork) and work.until is not None:
            resolved = await self._connector(run, step.id, work.until.capability)
            await self._not_stopped(run, resolved.adapter)
            operation = resolved.declaration.operation(work.until.operation)
            if operation is None:
                raise _StepFailed(
                    reason=str(NoConnector(step.id, work.until.operation)),
                    retryable=True,
                    consumption=None,
                    adapter=resolved.adapter,
                    outcome="no connector",
                    lack=(block.OPERATION_UNSUPPORTED, work.until.operation),
                )
            if operation.demand is None:
                return _Demand(None, _undeclared(operation.name), resolved.adapter)
            calls = int(work.until.timeout_seconds // work.until.poll_seconds) + 1
            return _Demand(_times(operation.demand.document(), calls), adapter=resolved.adapter)
        if isinstance(work, ConnectorRule):
            resolved = await self._connector(run, step.id, work.capability)
            await self._not_stopped(run, resolved.adapter)
            operation = resolved.declaration.operation(work.operation)
            if operation is None:
                raise _StepFailed(
                    reason=str(NoConnector(step.id, work.operation)),
                    retryable=True,
                    consumption=None,
                    adapter=resolved.adapter,
                    outcome="no connector",
                    lack=(block.OPERATION_UNSUPPORTED, work.operation),
                )
            if operation.demand is None:
                return _Demand(None, _undeclared(operation.name), resolved.adapter)
            return _Demand(_times(operation.demand.document(), 1), adapter=resolved.adapter)
        if isinstance(work, LlmWork):
            return await self._llm_demand(run, step, work)
        return _Demand(NOTHING)

    async def _llm_demand(self, run: Run, step: Step, work: LlmWork) -> _Demand:
        """Input counted before the call, output bounded by the limit the step sets; money at
        the price table, with every input token priced as the dearest input kind, because
        whether it will be read from a cache is not knowable before the call."""
        routed = await self._route(run, step, work)
        # Every member that fits cooling down: the step admits on the first, and waits at its
        # boundary without a call (ADR-0116 §6).
        resolved = routed.chosen or routed.fitting
        if resolved is None:
            raise _StepFailed(
                reason=_no_model(routed),
                retryable=True,
                consumption=None,
                adapter=None,
                outcome="no model",
            )
        # The model the route reached — the chain's first that fits, or the one a failure
        # moved the step to (ADR-0116 §6) — is asked nothing, not even a count, once stopped.
        await self._not_stopped(run, resolved.adapter)
        (values,), _ = await self._resolved(run, [work.values])
        rendered = rules.template(
            TemplateRule(rule="template", text=work.prompt, values=work.values), values
        )
        prompt = Prompt(system=work.system, user=rendered, max_output_tokens=work.max_output_tokens)
        declaration = resolved.model.calculability()
        counted = await resolved.model.count(prompt)
        if counted is None:
            return _Demand(
                None,
                f"{resolved.adapter} cannot count a prompt's input before the call "
                f"(input_count {declaration.input_count}), so the step has no estimate",
                resolved.adapter,
            )
        demand: dict[str, Any] = {"tokens_in": counted, "tokens_out": work.max_output_tokens}
        model = resolved.version or ""
        if re.fullmatch(MODEL_NAME_PATTERN, model):
            demand["tokens_by_model"] = {
                model: PriceKinds(input=counted, output=work.max_output_tokens)
            }
        table = self._options.prices
        if run.budget.currency is not None:
            if table is None or model not in table.prices:
                return _Demand(
                    None,
                    f"the budget limits money and the price table has no price for {model!r}: "
                    "the step's cost cannot be estimated",
                    resolved.adapter,
                )
            prices = table.prices[model]
            dearest = max(prices.get("input", 0.0), prices.get("cache_write", 0.0))
            bound = price(
                {model: PriceKinds(input=counted, output=work.max_output_tokens)},
                table.model_copy(update={"prices": {model: {**prices, "input": dearest}}}),
            )
            if not bound.complete:
                return _Demand(
                    None,
                    f"the price table prices {model!r} without "
                    + ", ".join(bound.unpriced)
                    + ": the step's cost cannot be estimated",
                    resolved.adapter,
                )
            demand["currency"] = {table.currency: bound.amount}
        return _Demand(ConsumptionQuantities.model_validate(demand), adapter=resolved.adapter)

    async def _admit(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        demand: _Demand,
        span: Span,
        **changes: Any,
    ) -> tuple[Run, StepRun, bool]:
        """Reserve the step's demand against what remains of the line the run is held to, or
        refuse it: for want of an estimate, or because the reservation does not fit. What is
        reserved is the estimate scaled by the measured error of its adapter; the ledger
        carries the estimate on `step.admitted` and, where the two differ, the reservation on
        `step.reserved`. A step admitted again after it failed is a retry, recorded as
        `step.retried` in the same transaction (ADR-0147 §4)."""
        retried = step_run.state is StepState.FAILED
        adapter = demand.adapter or step_run.adapter
        unpriced = None if demand.quantities is None else self._unpriced(run, demand.quantities)
        if unpriced is not None:
            demand = _Demand(None, unpriced, demand.adapter, demand.capabilities)
        if demand.quantities is None:
            span.record_failure("no estimate")
            step_run = step_run.to(
                StepState.REJECTED,
                adapter=adapter,
                estimate=None,
                reservation=None,
                reason="refused, not admitted: " + (demand.why_not or "no estimate"),
                **changes,
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.rejected", step=step_run, outcome="no_estimate"
            )
            return run, step_run, False
        scale, _ = (
            ({}, "")
            if adapter is None
            else budgeting.scale_for(
                adapter,
                step.method,
                demand.capabilities,
                self._observed.get(run.id, []),
                self._options.seeds,
                self._options.uncalibrated_margin,
                budgeting.models_of(demand.quantities),
                step=step_key(run.process_version, step.id),
            )
        )
        reservation = budgeting.reserve(demand.quantities, scale)
        line = self._line(run)
        spent = self._spent(_released(run, step_run.step_id))
        left = remaining(line, spent)
        verdict = admit(self._priced(run, reservation), left, line)
        capped = (
            not verdict.fits
            and step.method is Method.WORKER
            and admit(self._priced(run, demand.quantities), left, line).fits
        )
        if capped:
            # The worker's own estimate fits; only its calibrated error does not. It reserves
            # what is left and halts at its ceiling, never past the line (seventh amendment).
            reservation = budgeting.capped(reservation, left)
            verdict = admit(self._priced(run, reservation), left, line)
        refused = (
            await self._platform_refuses(self._options.unit_memory_bytes)
            if step.method is Method.WORKER and verdict.fits
            else None
        )
        if refused is not None:
            span.record_failure("rejected by the platform")
            run, step_run = await self._open_block(
                run, step_run, "limit.compute", block.REJECTED_BY_CAPACITY
            )
            step_run = step_run.to(
                StepState.REJECTED,
                adapter=adapter,
                estimate=demand.quantities,
                reservation=reservation,
                reason=refused,
                **changes,
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.rejected",
                step=step_run,
                outcome="rejected_by_capacity",
            )
            return run, step_run, False
        if not verdict.fits:
            span.record_failure("rejected by admission control")
            run, step_run = await self._open_block(
                run, step_run, block.limit_account(verdict.kinds), block.REJECTED_BY_ADMISSION
            )
            step_run = step_run.to(
                StepState.REJECTED,
                adapter=adapter,
                estimate=demand.quantities,
                reservation=reservation,
                reason="does not fit the remaining budget: " + "; ".join(verdict.findings),
                **changes,
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.rejected",
                step=step_run,
                outcome="rejected_by_admission",
            )
            return run, step_run, False
        if step_run.block is not None and step_run.block.cause in block.CLOSED_BY_ADMISSION:
            # What refused the step now lets it through: the block ends here.
            run, step_run = await self._close_block(run, step_run)
        step_run = step_run.to(
            StepState.ADMITTED,
            adapter=adapter,
            estimate=demand.quantities,
            reservation=reservation,
            reason=None,
            **changes,
        )
        run = await self._commit(
            run.with_step_run(step_run),
            "step.admitted",
            step=step_run,
            before=(
                ({"kind": RETRIED, "step": step_run, "outcome": "after_failure"},)
                if retried
                else ()
            ),
        )
        if reservation != demand.quantities:
            run = await self._commit(
                run, "step.reserved", step=step_run, outcome="capped" if capped else "calibrated"
            )
        return run, step_run, True

    async def _platform_refuses(self, memory_bytes: int | None) -> str | None:
        """Why the platform cannot hold what is about to start, or None: memory for the unit a
        worker step starts here, and storage above its refusal share for anything at all. What
        the platform could not observe refuses nothing (docs/architecture/platform.md)."""
        if self._platform is None:
            return None
        verdict = admit_capacity(
            await self._platform.observe(),
            CapacityDemand(memory_bytes=memory_bytes),
            self._options.capacity,
        )
        if verdict.fits:
            return None
        return "the platform cannot hold it: " + "; ".join(verdict.findings)

    async def _failed_before(
        self,
        run: Run,
        step_run: StepRun,
        span: Span,
        reason: str,
        adapter: str | None,
        retryable: bool | None,
        *,
        lack: tuple[str, str] | None = None,
    ) -> tuple[Run, StepRun]:
        """A step that failed while it was being estimated — its adapter is not configured,
        a reference in its prompt does not resolve — fails at its boundary like one that
        failed while running; nothing was admitted and nothing started. For want of an adapter
        it is blocked until it can start (ADR-0046)."""
        span.record_failure("failed before admission")
        run, step_run = await self._lacking(run, step_run, lack)
        step_run = step_run.to(
            StepState.FAILED,
            adapter=adapter,
            reason=reason,
            retryable=retryable,
            finished_at=self._clock.now(),
        )
        run = await self._commit(
            run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
        )
        return run, step_run

    async def _observations(self, tenant: Tenant) -> list[budgeting.Observation]:
        """The pairs of estimate and actual the calibration reads, oldest first: a step's
        `step.admitted` and the `step.finished` of the same step after it. The calibration
        is a statistic over these, and so reproducible from the ledger (ADR-0005 §4). They are
        a projection of the ledger, brought up to date from the last entry it read: a run start
        reads the entries since, not the tenant's history (ADR-0105)."""
        async with self._work.transaction(tenant):
            calibration = await self._ledger.project(tenant, CALIBRATION)
        return calibration.observations()

    # --- llm steps ------------------------------------------------------------------------------

    async def _llm_step(
        self, run: Run, step_run: StepRun, work: LlmWork, span: Span
    ) -> tuple[Any, Trace, Consumption | None, str]:
        """One completion from the model configured for the purpose. The text that leaves the
        step is the model's, once it passes the pattern; the tokens are counted; the model
        that answered goes into the provenance as the adapter's version, because a variable
        method is reproducible only at a pinned one."""
        routed = await self._route(run, run.step(step_run.step_id), work)
        resolved = routed.chosen
        if resolved is None and routed.fitting is not None:
            # Every member that fits is cooling down: nothing is called, and the step waits at
            # its boundary until the first cool-down ends (ADR-0116 §6).
            ends = min(
                self._cooling[s.adapter] for s in routed.skipped if s.reason == "cooling_down"
            )
            raise _AtLimit(
                adapter=routed.fitting.adapter,
                reason=f"every model of the purpose {work.purpose!r} that fits the step is "
                "cooling down after a rate limit or a failure",
                retry_after_seconds=max((ends - self._clock.now()).total_seconds(), 0.0),
            )
        if resolved is None:
            raise _StepFailed(
                reason=_no_model(routed),
                retryable=True,
                consumption=None,
                adapter=None,
                outcome="no model",
            )
        (values,), read = await self._resolved(run, [work.values])
        rendered = rules.template(
            TemplateRule(rule="template", text=work.prompt, values=work.values), values
        )
        prompt = Prompt(system=work.system, user=rendered, max_output_tokens=work.max_output_tokens)
        span.set_attribute("adapter", resolved.adapter)
        attributes: dict[str, str | int] = {
            "run.id": run.id,
            "step.id": step_run.step_id,
            "adapter": resolved.adapter,
            "model.purpose": work.purpose,
        }
        await self._not_stopped(run, resolved.adapter)
        try:
            async with self._telemetry.span("model.complete", attributes) as call:
                completion = await resolved.model.complete(prompt)
                call.set_attribute("model.name", completion.model)
                call.set_attribute("model.finish", completion.finish)
            await self._book_answer(run, step_run)
        except ModelAtLimit as error:
            delay = error.retry_after_seconds
            raise _AtLimit(
                adapter=resolved.adapter,
                reason=str(error),
                retry_after_seconds=delay,
                moves=await self._cool(run, step_run, work, resolved.adapter, delay),
            ) from error
        except ModelError as error:
            raise _StepFailed(
                reason=str(error),
                retryable=True,
                consumption=None,
                adapter=resolved.adapter,
                outcome="model unavailable",
                moves=await self._cool(run, step_run, work, resolved.adapter, None),
            ) from error
        consumption = Consumption(
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
            tokens_by_model=None
            if completion.by_kind is None or not re.fullmatch(MODEL_NAME_PATTERN, completion.model)
            else {completion.model: completion.by_kind},
        )
        if completion.finish == "length":
            raise _StepFailed(
                reason=f"the model stopped at the output limit of {work.max_output_tokens} "
                "tokens; the answer is cut off and does not leave the step",
                retryable=True,
                consumption=consumption,
                adapter=resolved.adapter,
                outcome="answer cut off",
            )
        if work.pattern is not None and re.search(work.pattern, completion.text) is None:
            raise _StepFailed(
                reason=f"the model's answer does not match {work.pattern!r}; nothing leaves the "
                "step (a variable method proposes, the check decides)",
                retryable=True,
                consumption=consumption,
                adapter=resolved.adapter,
                outcome="answer failed the check",
            )
        trace = Trace(inputs=read, adapter_version=completion.model, route=routed.record())
        return (
            {"text": completion.text, "model": completion.model},
            trace,
            consumption,
            resolved.adapter,
        )

    async def _route(self, run: Run, step: Step, work: LlmWork) -> routing.Route:
        """The step's route through its purpose's chain, at this moment (ADR-0116 §4)."""
        models = self._model_pool(run)
        chain = [] if models is None else await models.chain(work.purpose)
        permitted: Permitted = "anywhere"
        if self._residency is not None:
            permitted = await self._residency.permitted(run.tenant, work.data_class)
        needs = routing.Needs(
            purpose=work.purpose,
            exactness=step.exactness,
            permitted=permitted,
            data_class=work.data_class,
        )
        return routing.route(chain, needs, self._cooling, self._clock.now())

    async def _cool(
        self, run: Run, step_run: StepRun, work: LlmWork, adapter: str, delay: float | None
    ) -> bool:
        """The model failed, or answered at its rate limit: it cools down for the delay its
        provider named, or for the engine's cool-down where it named none. Whether another
        model of the chain fits the step now, so that the step moves there (ADR-0116 §5)."""
        seconds = self._options.model_cool_down_seconds if delay is None else delay
        self._cooling[adapter] = self._clock.now() + timedelta(seconds=seconds)
        routed = await self._route(run, run.step(step_run.step_id), work)
        return routed.chosen is not None

    # --- connector steps ------------------------------------------------------------------------

    async def _connector(self, run: Run, step_id: StepId, capability: str) -> ResolvedConnector:
        """The connector configured for the capability. None configured is a failed step, not
        an exception: the run escalates at the boundary with the reason, and a resume after
        the configuration changed retries it (the same as a model that is not configured)."""
        resolved = None
        pool = self._connector_pool(run)
        if pool is not None:
            resolved = await pool.resolve(capability)
        if resolved is None:
            raise _StepFailed(
                reason=str(NoConnector(step_id, capability)),
                retryable=True,
                consumption=None,
                adapter=None,
                outcome="no connector",
                lack=(block.NO_CONNECTOR, capability),
            )
        return resolved

    async def _connector_call(
        self, run: Run, step_run: StepRun, work: ConnectorRule, span: Span
    ) -> tuple[Any, Trace, Consumption | None, str]:
        """One operation, called once for this attempt of the step. What comes back is the
        result as the contract shapes it — output, effect, consumption — and, for an outward
        effect, the egress entry the commit writes beside `step.finished`."""
        resolved = await self._connector(run, step_run.step_id, work.capability)
        operation = resolved.declaration.operation(work.operation)
        if operation is None:
            raise _StepFailed(
                reason=str(NoConnector(step_run.step_id, work.operation)),
                retryable=True,
                consumption=None,
                adapter=resolved.adapter,
                outcome="no connector",
                lack=(block.OPERATION_UNSUPPORTED, work.operation),
            )
        (input,), read = await self._resolved(run, [work.input])
        if work.expect and operation.outward:
            raise UnsupportedWork(
                step_run.step_id, "only a reading carries an expectation; a write acts once"
            )
        span.set_attribute("adapter", resolved.adapter)
        # Before the call is booked: a stopped connector is neither called nor counted.
        await self._not_stopped(run, resolved.adapter)
        scope = await self._frame(run, step_run.step_id, resolved, operation)
        if run.rehearsal and operation.outward and not self._replaying(run):
            return await self._rehearsed(run, resolved, operation, read)
        sent: Digest | None = None
        if operation.outward and not run.rehearsal:
            input, sent = await self._labelled(run, step_run.step_id, work, operation, input)
            await self._book_call(run, step_run, operation.name, input)
        result = await self._call(
            run, step_run, resolved, operation, input, work.credentials, span, scope=scope
        )
        document = result.document()
        unmet = [why for e in work.expect if (why := rules.unmet(e, document["output"]))]
        if unmet:
            # The reading fails its own step, so that a resume reads again: the state outside
            # may be what was expected by then (issue #31).
            raise _StepFailed(
                reason=f"{operation.name} did not show what the step expects: "
                + "; ".join(unmet)
                + ". A resume reads it again",
                retryable=True,
                consumption=result.consumption,
                adapter=resolved.adapter,
                outcome="reading not as expected",
            )
        inputs = list(read)
        if not operation.outward:
            inputs.append(self._source(operation, input, document["output"]))
        # A replay sends an outward operation to its recording, which acts on nothing: the
        # step is rehearsed and no egress is written, as for any rehearsal (ADR-0108).
        rehearsed = run.rehearsal and operation.outward
        egress = result.effect if operation.outward and not rehearsed else None
        trace = Trace(
            inputs=tuple(inputs),
            adapter_version=resolved.version,
            egress=egress,
            rehearsed=rehearsed,
            message=sent if egress is not None else None,
        )
        return document, trace, result.consumption, resolved.adapter

    async def _labelled(
        self,
        run: Run,
        step_id: StepId,
        work: ConnectorRule,
        operation: Operation,
        input: Mapping[str, Any],
    ) -> tuple[dict[str, Any], Digest | None]:
        """A message step's input as it is sent — with the tenant's label added to its text
        where a model drafted it — and the digest of its record; a step that sends no message
        unchanged. The label is asked again at the call, so a label withdrawn while the message
        was held refuses it here, before the connector port is called (ADR-0142 §7)."""
        step = run.step(step_id)
        control = control_of(step, run.work.get(step_id), run.inputs)
        gate = await self._message_gate(run, step, work, control)
        if gate is not None and gate.refused is not None:
            token, why = gate.refused
            raise _StepFailed(
                reason=f"{operation.name} was not called: {why}",
                retryable=False,
                consumption=None,
                adapter=None,
                outcome="message held",
                held=token,
            )
        if gate is None or gate.message is None:
            return dict(input), None
        sent = dict(input)
        if gate.drafted:
            label = gate.rules.label
            labelled = None if label is None else messages.labelled(input, gate.message.text, label)
            if labelled is None:
                why = (
                    "the tenant configured no label"
                    if label is None
                    else f"its input has no text in {gate.message.text!r} to add the label to"
                )
                raise _StepFailed(
                    reason=f"{operation.name} was not called: a model drafted the message, and "
                    f"{why}. Nothing was sent (ADR-0142 §7)",
                    retryable=False,
                    consumption=None,
                    adapter=None,
                    outcome="message unlabelled",
                    held=messages.UNLABELLED,
                )
            sent = labelled
        record = {**gate.record, "label": gate.rules.label if gate.drafted else None}
        return sent, await self._objects.put(_canonical(record))

    # --- rehearsal (ADR-0030) ------------------------------------------------------------------

    async def _rehearsed(
        self,
        run: Run,
        resolved: ResolvedConnector,
        operation: Operation,
        read: tuple[ProvenanceInput, ...],
    ) -> tuple[Any, Trace, Consumption | None, str]:
        """An outward operation in a rehearsal: nothing is sent. The step answers with the
        recorded response of the most recent real call of the operation through the adapter,
        reads it as that run's result, and consumes nothing. Without a recording the step
        fails: the process cannot be rehearsed past it."""
        found = await self._recordings.response(run.tenant, resolved.adapter, operation.name)
        if found is None:
            raise _StepFailed(
                reason=f"rehearsal: no recorded response for {operation.name} through "
                f"{resolved.adapter} — it has never been called for real on this instance",
                retryable=False,
                consumption=None,
                adapter=resolved.adapter,
                outcome="no recording",
            )
        recording, document = found
        recorded = ProvenanceInput(
            kind=InputKind.RESULT,
            run_id=recording.run_id,
            step_id=recording.step_id,
            digest=recording.digest,
            observed_at=self._clock.now(),
        )
        replayed = {
            **document,
            "rehearsed_from": {"run_id": recording.run_id, "step_id": recording.step_id},
        }
        trace = Trace(inputs=(*read, recorded), adapter_version=resolved.version, rehearsed=True)
        return replayed, trace, None, resolved.adapter

    # --- end of rehearsal ----------------------------------------------------------------------

    async def _call(
        self,
        run: Run,
        step_run: StepRun,
        resolved: ResolvedConnector,
        operation: Operation,
        input: Mapping[str, Any],
        credentials: tuple[Any, ...],
        span: Span,
        *,
        scope: CaseScope | None = None,
    ) -> Result:
        await self._not_stopped(run, resolved.adapter)
        context = CallContext(
            tenant=run.tenant,
            identity=run.identity,
            run_id=run.id,
            step_id=step_run.step_id,
            attempt=step_run.attempt,
            idempotency_key=idempotency_key(run.id, step_run.step_id, step_run.attempt),
            credentials=credentials,
            autonomy_level=run.autonomy_level,
            scope=scope,
        )
        attributes: dict[str, str | int] = {
            "run.id": run.id,
            "step.id": step_run.step_id,
            "adapter": resolved.adapter,
            "connector.operation": operation.name,
            "connector.effect": str(operation.effect),
            "connector.attempt": step_run.attempt,
        }
        try:
            async with self._telemetry.span("connector.call", attributes) as call:
                result = await resolved.connector.call(operation.name, context, input)
                if result.effect.replayed is not None:
                    call.set_attribute("connector.replayed", result.effect.replayed)
        except CallFailed as failed:
            error = failed.error
            if error.cause is ConnectorCause.OUT_OF_SCOPE:
                # The connector refused data of another subject than the case's: the step
                # fails, and the refusal is recorded (ADR-0130). It is never repeated.
                raise _StepFailed(
                    reason=f"{operation.name} was refused as out of the case's scope: "
                    f"{error.detail}",
                    retryable=False,
                    consumption=error.consumption,
                    adapter=resolved.adapter,
                    outcome="out of scope",
                    frame=frame.OUT_OF_SCOPE,
                ) from failed
            reason = f"{operation.name} failed: {error.cause} — {error.detail}"
            if error.effect == "unknown" and not operation.repeatable:
                reason += (
                    "; the operation cannot recognise a repeat (idempotency: none), so the run "
                    "did not retry it. Check the target system whether the effect happened "
                    "before resuming: resuming repeats the call"
                )
            raise _StepFailed(
                reason=reason,
                retryable=error.retryable,
                consumption=error.consumption,
                adapter=resolved.adapter,
                outcome="connector failed",
                interface=interfaces.of_cause(error.cause),
                not_found=error.cause is ConnectorCause.NOT_FOUND,
            ) from failed
        except ConnectorError as broken:
            # The connector did not answer, or answered outside the contract: whether the
            # call acted is unknown unless the operation recognises a repeat.
            reason = f"{operation.name}: {broken}"
            if operation.outward and not operation.repeatable:
                reason += (
                    "; the operation cannot recognise a repeat (idempotency: none), so the run "
                    "did not retry it. Check the target system whether the effect happened "
                    "before resuming: resuming repeats the call"
                )
            broke = isinstance(broken, ContractBroken)
            raise _StepFailed(
                reason=reason,
                retryable=not operation.outward or operation.repeatable,
                consumption=None,
                adapter=resolved.adapter,
                outcome="connector broke the contract" if broke else "connector unreachable",
                interface=interfaces.CONTRACT if broke else interfaces.UNREACHABLE,
            ) from broken
        if result.effect.kind != operation.effect:
            raise _StepFailed(
                reason=f"{operation.name} reported effect {result.effect.kind}, declared "
                f"{operation.effect}: the connector broke its contract",
                retryable=False,
                consumption=result.consumption,
                adapter=resolved.adapter,
                outcome="connector broke the contract",
                interface=interfaces.CONTRACT,
            )
        return result

    def _source(
        self, operation: Operation, input: Mapping[str, Any], output: Any
    ) -> ProvenanceInput:
        """A read through a connector is an external source the step read, with the digest of
        what it answered: the moment and the content, so that "since when" stays answerable."""
        canonical = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        given = json.dumps(input, ensure_ascii=False, sort_keys=True)
        ref = f"{operation.name} {given}"
        return ProvenanceInput(
            kind=InputKind.SOURCE,
            capability=operation.capability,
            ref=ref if len(ref) <= SOURCE_REF_LENGTH else ref[: SOURCE_REF_LENGTH - 1] + "…",
            digest=_digest(canonical),
            observed_at=self._clock.now(),
        )

    async def _park(self, run: Run, step_run: StepRun, parked: _Parked) -> tuple[Run, StepRun]:
        """The wait goes on without this runner: the step goes back to its boundary with its
        block still open and the moment of its next check, and the run halts there with cause
        `parked` for its runner to defer the job to that moment (ADR-0103). The block ends only
        when the wait does, so its whole duration is booked to `wait.external`."""
        self._parked.add(run.id)
        now = self._clock.now()
        check_at = parked.check_at
        if step_run.block is not None:
            step_run = step_run.model_copy(
                update={"block": step_run.block.model_copy(update={"next_check_at": check_at})}
            )
        step_run = step_run.to(
            StepState.STOPPED,
            consumption=parked.consumption,
            reason=f"waiting, parked until {check_at.isoformat()}",
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(step_run),
            "step.waiting",
            step=step_run,
            outcome=step_run.block.cause if step_run.block is not None else "parked",
        )
        return run, step_run

    def _waited_so_far(self, step_run: StepRun, resumed: bool) -> float:
        """How long a wait step has waited: nothing when it starts now; since its block began
        when it resumes."""
        if not resumed or step_run.block is None:
            return 0.0
        return max(0.0, (self._clock.now() - step_run.block.since).total_seconds())

    async def _wait_for(self, step_run: StepRun, seconds: float, *, resumed: bool) -> None:
        """Wait on the clock for `seconds`, or, for a wait resumed, for what remains of them
        since it began. What remains beyond the engine's limit for waiting inline parks the run
        instead (ADR-0103)."""
        remaining = seconds - self._waited_so_far(step_run, resumed)
        if remaining <= 0:
            return
        limit = self._options.park_waits_after_seconds
        if limit is not None and remaining > limit:
            began = step_run.block.since if step_run.block is not None else self._clock.now()
            raise _Parked(began + timedelta(seconds=seconds), None)
        await self._clock.sleep(remaining)

    async def _wait_until(
        self,
        run: Run,
        step_run: StepRun,
        until: WaitUntil,
        span: Span,
        before: Consumption | None = None,
        *,
        resumed: bool = False,
    ) -> tuple[StepRun, Consumption | None]:
        """Poll a read operation until the selected part of its output is expected, within
        the timeout. A wait produces no result (ADR-0018); what it consumed is counted. The
        timeout counts from when the wait began, so a parked wait resumed, or one recovered
        after a restart, waits only what remains; a poll interval beyond the engine's limit for
        waiting inline parks the run until the next check (ADR-0103)."""
        resolved = await self._connector(run, step_run.step_id, until.capability)
        operation = resolved.declaration.operation(until.operation)
        if operation is None:
            raise _StepFailed(
                reason=str(NoConnector(step_run.step_id, until.operation)),
                retryable=True,
                consumption=None,
                adapter=resolved.adapter,
                outcome="no connector",
                lack=(block.OPERATION_UNSUPPORTED, until.operation),
            )
        if operation.outward:
            raise UnsupportedWork(step_run.step_id, "a wait reads an external state, never writes")
        (input,), _ = await self._resolved(run, [until.input])
        scope = await self._frame(run, step_run.step_id, resolved, operation)
        step_run = step_run.model_copy(update={"adapter": resolved.adapter})
        used: dict[str, Any] = {}
        if before is not None:
            _accumulate(used, before)
        waited = self._waited_so_far(step_run, resumed)
        limit = self._options.park_waits_after_seconds
        while True:
            try:
                result = await self._call(
                    run, step_run, resolved, operation, input, until.credentials, span, scope=scope
                )
            except _AdapterStopped as stopped:
                # Stopped between two checks: the wait stops at its boundary with what its
                # checks used (ADR-0138, amendment).
                raise _AdapterStopped(stopped.adapter, _consumption(used)) from None
            except _StepFailed as refused:
                # The record may not exist yet; any other refusal fails the step at once.
                if not refused.not_found:
                    raise
                if refused.consumption is not None:
                    _accumulate(used, refused.consumption)
                observed = _NOT_FOUND
            else:
                _accumulate(used, result.consumption)
                try:
                    observed = select(result.output, until.select)
                except KeyError:
                    observed = None
            if observed is not _NOT_FOUND and observed in until.expect:
                span.set_attribute("wait.observed", str(observed))
                return step_run, _consumption(used)
            if waited >= until.timeout_seconds:
                raise _StepFailed(
                    reason=f"waited {waited:.0f}s for {until.operation} {until.select} to be one "
                    f"of {list(until.expect)}; last observed "
                    f"{'not_found' if observed is _NOT_FOUND else repr(observed)}",
                    retryable=True,
                    consumption=_consumption(used),
                    adapter=resolved.adapter,
                    outcome="wait timed out",
                )
            if limit is not None and until.poll_seconds > limit:
                check_at = self._clock.now() + timedelta(seconds=until.poll_seconds)
                raise _Parked(check_at, _consumption(used))
            await self._clock.sleep(until.poll_seconds)
            waited += until.poll_seconds

    async def _resolved(
        self, run: Run, values: list[Any]
    ) -> tuple[list[Any], tuple[ProvenanceInput, ...]]:
        """The values with every `$from` reference replaced, and what was read to do so."""
        referenced: set[StepId] = set()
        artifacts: set[tuple[StepId, str]] = set()
        for value in values:
            referenced |= references(value)
            artifacts |= artifact_references(value)
        results, read = await self._results(run, referenced, artifacts)
        contents: dict[str, Any] = {}
        for step_id, artifact_id in artifacts:
            contents[f"{step_id}/{artifact_id}"] = await self._artifact_content(
                run, step_id, artifact_id
            )
        record = run.record()
        if self._statements is not None and any(_names_exactness(v) for v in values):
            # The statement as the process component renders it, unchanged (UC-6.9).
            rendered = await self._statements.rendered(run.tenant, run.process_version)
            if rendered is not None:
                record[EXACTNESS] = rendered
        try:
            return [resolve(value, results, contents, record) for value in values], read
        except KeyError as missing:
            raise RuleFailed(f"reference to {missing.args[0]!r} cannot be resolved") from missing

    async def _artifact_content(self, run: Run, step_id: StepId, artifact_id: str) -> Any:
        producer = run.step_run(step_id)
        if (
            producer.method is Method.ML
            and producer.confirmed_by is not None
            and producer.checkpoint is not None
            and producer.checkpoint.result_digest == _digest(NO_RESULT)
        ):
            raise RuleFailed(
                f"step {step_id!r} was performed by a person after its model was unsure; what "
                "the model produced leaves the step for nothing (ADR-0076)"
            )
        artifact = producer.artifact(artifact_id)
        if artifact is None:
            raise RuleFailed(f"step {step_id!r} produced no artifact {artifact_id!r}")
        content = await self._objects.get(artifact.digest)
        if content is None:
            raise RuleFailed(f"the content of artifact {artifact_id!r} is not available")
        text = content.decode("utf-8", errors="replace")
        if (artifact.media_type or "").startswith("application/json"):
            try:
                return json.loads(text)
            except ValueError as error:
                raise RuleFailed(f"artifact {artifact_id!r} is not the JSON it claims") from error
        return text

    # --- worker steps ----------------------------------------------------------------------------

    async def _worker_step(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        work: WorkerWork,
        span: Span,
        held: autonomy.Held,
    ) -> tuple[Run, StepRun]:
        permitted: Permitted = "anywhere"
        if self._residency is not None:
            permitted = await self._residency.permitted(run.tenant, work.data_class)
        outside: tuple[str, str] | None = None
        try:
            resolved = await self._worker_pool(run).resolve(step.required_capabilities, permitted)
            if resolved is None and permitted != "anywhere":
                # Whether a worker offers the capabilities and is outside the rule: the step
                # then fails naming the rule, and nothing is sent to it (ADR-0157 §2).
                beyond = await self._worker_pool(run).resolve(step.required_capabilities)
                if beyond is not None:
                    outside = (beyond.adapter, beyond.location)
        except UnaskedWorker as unasked:
            # A worker that cannot be asked what it offers is a worker that cannot answer: the
            # step fails with that cause, or waits for a platform without room for its unit,
            # as at the estimate below. Raised, the run stayed `running` and every claim of
            # its job recovered it again (#589).
            if isinstance(unasked.cause, WorkerAtCapacity):
                resuming = step_run.checkpoint if step_run.state is StepState.STOPPED else None
                return await self._full(
                    run, step_run, work, unasked.adapter, resuming, span, unasked.cause
                )
            return await self._unavailable(run, step_run, unasked.adapter, span, unasked)
        if resolved is None:
            # No configured worker offers the capabilities: a failed step, the run escalates
            # at the boundary, and a resume after the configuration changed retries it.
            span.record_failure("no worker")
            run, step_run = await self._lacking(
                run, step_run, (block.NO_WORKER, ",".join(step.required_capabilities) or "nothing")
            )
            step_run = step_run.to(
                StepState.FAILED,
                reason=str(
                    NoWorker(
                        step.id, step.required_capabilities, permitted=permitted, outside=outside
                    )
                ),
                retryable=True,
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        run, step_run = await self._lack_ends(run, step_run)
        adapter, worker = resolved.adapter, resolved.worker
        span.set_attribute("adapter", adapter)
        call = {"run.id": run.id, "step.id": step.id, "adapter": adapter}
        (inputs,), read = await self._resolved(run, [work.task.inputs])
        if isinstance(work, MlWork):
            try:
                inputs = MlWork.worker_inputs(inputs)
            except ValueError as unreadable:
                # The case does not give the numbers the model predicts from (ADR-0114 §3).
                return await self._failed_before(
                    run, step_run, span, f"the case cannot be predicted: {unreadable}", None, False
                )
            read = (*read, *self._predicted_from(step, inputs))
        trace = Trace(inputs=read, adapter_version=resolved.version)
        if step_run.assignment_open:
            # An assignment handed over earlier and never seen to end may still be running in
            # the worker: it is asked about before another is handed over (ADR-0038).
            reclaimed = await self._reclaim(
                run, step, step_run, work, resolved, trace, span, call, held
            )
            if reclaimed is not None:
                return reclaimed
        # An assignment adopted above was handed over when it was admitted; a new one is not
        # handed to an adapter below verified from level 3 (NTC-0051).
        unverified = await self._unverified(run, step, adapter, held)
        if unverified is not None:
            return await self._refuse_unverified(run, step_run, adapter, unverified, span)
        if adapter in await self._held_stops(run.tenant):
            # The adapter is stopped: nothing is handed to it, and the run halts at the step's
            # boundary (ADR-0138 §2).
            return await self._at_stopped_adapter(run, step_run, adapter, span)
        resuming = step_run.checkpoint if step_run.state is StepState.STOPPED else None
        left = remaining(self._line(run), self._spent(run))
        assignment = Assignment(
            # An open assignment the worker never received is posted again under its own id:
            # a runner that handed it over and was cut off then meets the worker's 409.
            assignment_id=step_run.assignment_id
            if step_run.assignment_open and step_run.assignment_id is not None
            else self._ids.new("asg"),
            task=Task(
                goal=work.task.goal,
                acceptance=work.task.acceptance,
                inputs=inputs,
                before=work.task.before,
                after=work.task.after,
            ),
            credentials=work.credentials or None,
            context=Context(
                workspace=work.workspace,
                checkpoint_ref=None if resuming is None else resuming.ref,
            ),
            frame=Frame(
                autonomy_level=run.autonomy_level,
                allowed_tools=step.required_capabilities,
                allowed_hosts=work.allowed_hosts,
                max_steps=work.max_steps,
            ),
            # The worker sees what is left, never the whole budget: its own check (W-10) then
            # guards the same line the core guards here.
            limits=left if left is not None else run.budget,
            callback=Callback(events="sse"),
        )

        # 1 + 2: estimate and admit, before anything starts. A worker that cannot answer — an
        # execution unit that does not start, an endpoint that does not answer — fails the
        # step with that cause; the run escalates and nothing is left half done. A worker at
        # capacity while it estimates — a platform without room for its unit — makes the step
        # wait, as at the hand-over (ADR-0037 §6).
        # A launched worker is estimated by the estimator it declares, and starts no unit for
        # it; one that declares none has no estimate, and its step is refused (ADR-0115).
        why_not: str | None = None
        try:
            async with self._telemetry.span("worker.estimate", call):
                estimate = await worker.estimate(assignment.estimate_request())
        except NoEstimator as error:
            estimate = None
            why_not = str(error)
        except WorkerAtCapacity as error:
            return await self._full(run, step_run, work, adapter, resuming, span, error)
        except WorkerError as error:
            return await self._unavailable(run, step_run, adapter, span, error)
        demand = ConsumptionQuantities.model_validate(
            {}
            if estimate is None
            else {**estimate.quantities(), "resource_class": estimate.resource_class}
        )
        if why_not is None and isinstance(work, MlWork) and work.fallback is not None:
            # A moved step may hand its case to the language model it was moved from: it is
            # admitted for both, the prediction and the completion (ADR-0114 §4).
            try:
                fallback = await self._llm_demand(run, step, work.fallback)
            except _StepFailed as failure:
                return await self._failed_before(
                    run, step_run, span, failure.reason, failure.adapter, failure.retryable
                )
            if fallback.quantities is None:
                why_not = f"the language model it falls back to: {fallback.why_not}"
            else:
                both: dict[str, Any] = {}
                _accumulate(both, fallback.quantities)
                _accumulate(both, demand)
                demand = ConsumptionQuantities.model_validate(both)
        run, step_run, admitted = await self._admit(
            run,
            step,
            step_run,
            _Demand(
                None if why_not is not None else demand,
                why_not,
                adapter=adapter,
                capabilities=tuple(step.required_capabilities),
            ),
            span,
            retryable=None,  # what a failure was classified as holds for that failure only
        )
        if not admitted:
            return run, step_run
        # The worker's ceiling is what was reserved for it with its share of the margin, never
        # more than what is left of the whole budget: it halts at its next boundary before its
        # running total would cross it (W-14).
        reservation = step_run.reservation or demand
        assignment = assignment.model_copy(
            update={
                "limits": budgeting.ceiling(
                    budgeting.grow(reservation, run.margin),
                    remaining(run.budget, self._spent(_released(run, step_run.step_id))),
                    run.budget,
                    self._per_second(run, reservation),
                )
            }
        )

        # 3: hand over. The assignment's id is committed first, with `step.assigned`: whatever
        # the worker accepts is named in the ledger even if this instance dies before it learns
        # of the acceptance, and whoever recovers the run knows what to ask the worker about.
        call["assignment.id"] = assignment.assignment_id
        step_run = step_run.model_copy(
            update={
                "assignment_id": assignment.assignment_id,
                "assignment_open": True,
                "assignment_seq": 0,
            }
        )
        run = await self._commit(run.with_step_run(step_run), "step.assigned", step=step_run)
        try:
            async with self._telemetry.span("worker.assign", call):
                state = await worker.assign(assignment)
        except WorkerAtCapacity as error:
            return await self._full(run, step_run, work, adapter, resuming, span, error)
        except AssignmentExists:
            # Another runner handed the same assignment over first: it is the worker's, and
            # this step continues it.
            try:
                state = await worker.state(assignment.assignment_id)
            except WorkerError as error:
                return await self._unavailable(run, step_run, adapter, span, error)
            return await self._handed_over(
                run, step, step_run, work, worker, state, trace, span, call, held, adopted=True
            )
        except WorkerError as error:
            return await self._unavailable(run, step_run, adapter, span, error)
        return await self._handed_over(
            run, step, step_run, work, worker, state, trace, span, call, held, adopted=False
        )

    async def _reclaim(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        work: WorkerWork,
        resolved: ResolvedWorker,
        trace: Trace,
        span: Span,
        call: dict[str, Any],
        held: autonomy.Held,
    ) -> tuple[Run, StepRun] | None:
        """The step's assignment was handed over and its end never read: an instance died
        between handing it over and reading its end, or the stream broke. The worker is asked.
        An assignment it holds is adopted — followed from the last event the step run holds,
        whatever its status. One it does not know never reached it, or is gone with a restart
        of the worker: None, and the caller posts it again under the same id. A worker that
        cannot be asked fails the step, and no other assignment is handed over (ADR-0038)."""
        assignment_id = step_run.assignment_id
        if assignment_id is None:  # unreachable: an open assignment carries its id
            return None
        call["assignment.id"] = assignment_id
        if step_run.adapter is not None and step_run.adapter != resolved.adapter:
            # The worker that holds it no longer serves the step. Nothing can ask it; a person
            # who resumes the run accepts that it may still run there.
            span.record_failure("assignment unreachable")
            step_run = step_run.to(
                StepState.FAILED,
                assignment_open=False,
                reason=f"assignment {assignment_id} was handed to the worker {step_run.adapter}, "
                f"which no longer serves this step ({resolved.adapter} does); it cannot be asked "
                "whether the assignment still runs there, and a resume hands over a new one",
                retryable=True,
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        try:
            async with self._telemetry.span("worker.state", call):
                state = await resolved.worker.state(assignment_id)
        except UnknownAssignment:
            return None
        except WorkerError as error:
            span.record_failure("worker unavailable")
            step_run = step_run.to(
                StepState.FAILED,
                reason=f"assignment {assignment_id}, handed over earlier, may still be running: "
                f"the worker could not be asked about it, so no other is handed over: {error}",
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        return await self._handed_over(
            run,
            step,
            step_run,
            work,
            resolved.worker,
            state,
            trace,
            span,
            call,
            held,
            adopted=True,
        )

    async def _handed_over(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        work: WorkerWork,
        worker: Worker,
        state: AssignmentState,
        trace: Trace,
        span: Span,
        call: dict[str, Any],
        held: autonomy.Held,
        *,
        adopted: bool,
    ) -> tuple[Run, StepRun]:
        """The worker holds the step's assignment: this runner handed it over and the worker
        took it (`step.started`), or it was found handed over earlier (`step.adopted`). Either
        way the step follows it, from the last event the step run holds."""
        assignment_id = state.assignment_id
        if step_run.waiting_since is not None or (
            step_run.block is not None and step_run.block.cause == block.AT_CAPACITY
        ):
            run, step_run = await self._waited(run, step_run, work, "assigned")
        if state.status == "finished" and state.outcome is Outcome.REJECTED:
            # A rejection is a state, not an error: the worker's own check refused it.
            span.record_failure("rejected by the worker")
            step_run = step_run.to(
                StepState.REJECTED,
                assignment_id=assignment_id,
                assignment_open=False,
                reason=f"rejected by the worker: {state.reason or 'no reason given'}",
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.rejected",
                step=step_run,
                outcome="rejected_by_worker",
            )
            return run, step_run
        now = self._clock.now()
        if adopted:
            step_run = step_run.to(
                StepState.RUNNING,
                assignment_id=assignment_id,
                started_at=step_run.started_at or now,
                reason=None,
                retryable=None,
                finished_at=None,
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.adopted", step=step_run, outcome=state.status
            )
        else:
            step_run = step_run.to(StepState.RUNNING, assignment_id=assignment_id, started_at=now)
            run = await self._commit(run.with_step_run(step_run), "step.started", step=step_run)
        self._inflight[run.id] = (worker, assignment_id)
        self._inflight_step[run.id] = step_run.step_id
        adapter = str(call["adapter"])
        self._inflight_adapter[run.id] = (run.tenant, adapter)
        if run.id in self._stop_requested or adapter in await self._held_stops(run.tenant):
            # A stop of the adapter requested since the check before the handover, or held
            # while an assignment handed over earlier was adopted, lands at its boundary.
            await self.request_stop(run.id)
        asked = self._taking_over.get(run.id)
        if asked is not None and asked.step_id == step_run.step_id:
            await self._stop_for_takeover(worker, assignment_id)
        try:
            async with self._telemetry.span("worker.follow", call) as following:
                run, step_run = await self._follow(
                    run, step_run, worker, assignment_id, trace, span, after=step_run.assignment_seq
                )
                following.set_attribute("step.state", step_run.state)
        finally:
            # On ClaimLost the assignment is left running: the runner that holds the claim now
            # adopts it (ADR-0038).
            self._inflight.pop(run.id, None)
            self._inflight_step.pop(run.id, None)
            self._inflight_adapter.pop(run.id, None)
        _measured(span, step_run)
        if (
            adopted
            and step_run.state is StepState.STOPPED
            and run.id not in self._limit_halts
            and run.id not in self._stop_requested
            and run.id not in self._taking_over
        ):
            # Stopped at a request this runner did not make: the runner that handed it over
            # asked before it gave the run up. The run is not stopped; the step continues from
            # the checkpoint with a new assignment.
            return await self._worker_step(run, step, step_run, work, span, held)
        return run, step_run

    async def _full(
        self,
        run: Run,
        step_run: StepRun,
        work: WorkerWork,
        adapter: str,
        resuming: Checkpoint | None,
        span: Span,
        error: WorkerAtCapacity,
    ) -> tuple[Run, StepRun]:
        """The worker holds as many assignments as it declares and did not take this one.
        Nothing started: the step goes back to the boundary it was admitted from and gives its
        reservation back, and the run halts there with cause `capacity` for its runner to try
        again later. Once the step's ceiling has passed, the step ends instead, failed with
        that cause, and the run escalates (ADR-0037)."""
        span.record_failure("worker at capacity")
        self._at_capacity.add(run.id)
        now = self._clock.now()
        since = step_run.waiting_since or now
        waits = step_run.waits + 1
        run, step_run = await self._open_block(
            run, step_run, waiting.ACCOUNT, block.AT_CAPACITY, since=since
        )
        # The worker did not take the assignment: none is open, and nothing is asked about it
        # when the run is resumed. Left open, a launched worker without a unit for it could
        # not be asked, and the resumed step failed (#486).
        step_run = step_run.model_copy(
            update={
                "adapter": adapter,
                "waiting_since": since,
                "waits": waits,
                "assignment_open": False,
            }
        )
        ceiling = self._ceiling(work)
        if waiting.over(since, now, ceiling):
            run, step_run = await self._waited(run, step_run, work, "ceiling")
            step_run = step_run.to(
                StepState.FAILED,
                reason=f"the worker {adapter} stayed at capacity for "
                f"{(now - since).total_seconds():.0f}s, {waits} times asked; the step's ceiling "
                f"is {ceiling}s: {error}",
                finished_at=now,
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.finished",
                step=step_run,
                outcome=waiting.AT_CAPACITY,
            )
            return run, step_run
        step_run = step_run.to(
            StepState.STOPPED,
            checkpoint=resuming,
            reason=f"waiting for a free place at the worker {adapter} since {since.isoformat()} "
            f"({waits} times asked; ceiling {ceiling}s): {error}",
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(step_run), "step.waiting", step=step_run, outcome=waiting.AT_CAPACITY
        )
        return run, step_run

    async def _waited(
        self,
        run: Run,
        step_run: StepRun,
        work: WorkerWork,
        ended: Literal["assigned", "ceiling"],
    ) -> tuple[Run, StepRun]:
        """The wait of a step ended — the worker took the assignment, or the ceiling passed:
        `step.waited` names the record with its account, cause and duration (ADR-0015)."""
        return await self._close_block(
            run,
            step_run,
            **waiting.details(
                adapter=step_run.adapter,
                waits=step_run.waits,
                ended=ended,
                ceiling_seconds=self._ceiling(work),
            ),
        )

    def _ceiling(self, work: WorkerWork) -> int:
        if work.capacity_ceiling_seconds is not None:
            return work.capacity_ceiling_seconds
        return self._options.capacity_ceiling_seconds

    async def _traced(self, run: Run, step_run: StepRun, event: Event) -> None:
        """The event kept as a line of the step's trace, in a transaction of its own, as it
        arrives (ADR-0135 §1). The trace is no part of the run's record: a line that cannot be
        kept is lost, and the step goes on."""
        if self._traces is None or self._masking is None:
            return
        line = line_of(
            event,
            run_id=run.id,
            step_id=step_run.step_id,
            recorded_at=self._clock.now(),
            mask=self._masking.mask,
        )
        try:
            async with self._work.transaction(run.tenant):
                await self._traces.append(run.tenant, line)
        except Exception:  # the trace never stops the work it watches
            return

    async def _unavailable(
        self, run: Run, step_run: StepRun, adapter: str, span: Span, error: WorkerError
    ) -> tuple[Run, StepRun]:
        span.record_failure("worker unavailable")
        step_run = step_run.to(
            StepState.FAILED, adapter=adapter, reason=str(error), finished_at=self._clock.now()
        )
        run = await self._commit(
            run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
        )
        return run, step_run

    async def _follow(
        self,
        run: Run,
        step_run: StepRun,
        worker: Worker,
        assignment_id: str,
        trace: Trace,
        span: Span,
        *,
        after: int = 0,
    ) -> tuple[Run, StepRun]:
        """Read the stream after `after` to its end, persisting what arrives as it arrives. The
        step run holds the effect of every event up to `after`; an adopted assignment is read
        from there, so that nothing is counted twice (ADR-0038)."""
        # What an earlier attempt of this step used was used all the same: a resumed or
        # retried step accumulates on top of it, and the budget sees the whole.
        used: dict[str, Any] = {}
        if step_run.consumption is not None:
            used = dict(step_run.consumption.quantities())
            if step_run.consumption.resource_class is not None:
                used["resource_class"] = step_run.consumption.resource_class
        artifacts = list(step_run.artifacts)  # inherited from before the checkpoint on resume
        checkpoint_ref: str | None = (
            None if step_run.checkpoint is None else step_run.checkpoint.ref
        )
        finished: AssignmentFinished | None = None
        last_seq = after
        watch = await self._watch(run, step_run)
        fired: repetition.Stop | None = None
        try:
            async for event in worker.events(assignment_id, after=after):
                if event.seq <= last_seq:
                    continue  # its effect is held already
                await self._traced(run, step_run, event)
                if watch is not None and isinstance(event, ToolCalled | ModelCalled):
                    stop = await self._reported(run, step_run, watch, event)
                    if stop is not None and fired is None:
                        fired = stop
                        await self._stop_reporting(run, step_run, worker, assignment_id, stop)
                if isinstance(event, ConsumptionReported):
                    _accumulate(used, event)
                elif isinstance(event, ArtifactProduced):
                    if any(a.id == event.artifact_id for a in artifacts):
                        continue  # produced before the checkpoint: never recorded twice
                    artifact = event.artifact()
                    content = await worker.artifact_bytes(assignment_id, artifact)
                    stored = await self._objects.put(content)
                    if stored != artifact.digest:
                        raise WorkerError(
                            f"artifact {artifact.id!r} hashes to {stored[:19]}…, not the "
                            f"announced {artifact.digest[:19]}…"
                        )
                    artifacts.append(artifact)
                elif isinstance(event, StepBoundary):
                    # The worker's own boundary: persisted now, so that an instance that dies
                    # after it resumes from here and not from the step's start.
                    checkpoint_ref = event.checkpoint_ref
                    step_run = step_run.model_copy(
                        update={
                            "artifacts": tuple(artifacts),
                            "consumption": _consumption(used),
                            "assignment_seq": event.seq,
                            "checkpoint": Checkpoint(
                                ref=checkpoint_ref,
                                step_id=step_run.step_id,
                                taken_at=self._clock.now(),
                                artifact_ids=tuple(a.id for a in artifacts),
                            ),
                        }
                    )
                    run = await self._commit(run.with_step_run(step_run))
                elif isinstance(event, MessageReceived):
                    received = await self._received(run, step_run, event)
                    if received is not step_run:
                        step_run = received
                        run = await self._commit(
                            run.with_step_run(step_run),
                            MESSAGE_RECEIVED,
                            step=step_run,
                            outcome="received",
                            digest=step_run.messages[-1].digest,
                        )
                elif isinstance(event, AssignmentFinished):
                    finished = event
                last_seq = event.seq
            if finished is None:
                raise WorkerError("the stream ended without assignment.finished")
        except WorkerError as error:
            span.record_failure("worker error")
            # The assignment may still be running, and no run follows it now: it is asked to
            # stop, and stays open, so that a resume asks the worker about it before it hands
            # over another (ADR-0038).
            with contextlib.suppress(Exception):
                await worker.stop(
                    assignment_id,
                    StopRequest(
                        reason="the step failed: " + str(error)[:200],
                        ceiling_seconds=self._options.step_ceiling_seconds,
                    ),
                )
            step_run = step_run.to(
                StepState.FAILED,
                artifacts=tuple(artifacts),
                consumption=_consumption(used),
                assignment_seq=last_seq,
                reason=str(error),
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run

        now = self._clock.now()
        consumption = _consumption(used)
        # Its end is read: the assignment is closed, and nothing is asked about it again.
        step_run = step_run.model_copy(
            update={"assignment_open": False, "assignment_seq": last_seq}
        )
        if step_run.messages:
            # Every message the worker received is an input of what the step produced.
            trace = dataclasses.replace(trace, inputs=(*trace.inputs, *_message_inputs(step_run)))
        if finished.outcome is Outcome.STOPPED:
            if fired is not None:
                # Stopped at its boundary by the rule on repetition: the run halts with cause
                # `repeated`, and a resume continues from the checkpoint (ADR-0144).
                self._repeating.add(run.id)
                finished = finished.model_copy(
                    update={"reason": fired.reason(step_run.step_id), "limit": None}
                )
            if finished.limit is not None:
                self._limit_halts.add(run.id)
            ref = finished.checkpoint_ref or checkpoint_ref
            checkpoint = (
                None
                if ref is None
                else Checkpoint(
                    ref=ref,
                    step_id=step_run.step_id,
                    taken_at=now,
                    artifact_ids=tuple(a.id for a in artifacts),
                )
            )
            if finished.limit is not None:
                # Halted at the run's own limit: blocked until a person changes it and the step
                # is admitted again (ADR-0043).
                run, step_run = await self._open_block(
                    run,
                    step_run,
                    block.limit_account([finished.limit]),
                    block.HALTED_AT_LIMIT,
                )
            step_run = step_run.to(
                StepState.STOPPED,
                artifacts=tuple(artifacts),
                consumption=consumption,
                checkpoint=checkpoint,
                reason=finished.reason
                or (
                    "stopped at the worker's step boundary"
                    if finished.limit is None
                    else f"the worker halted at its boundary before crossing its {finished.limit} "
                    "ceiling (W-14)"
                ),
                finished_at=now,
            )
            outcome = "stopped"
        elif finished.outcome is Outcome.SUCCEEDED and step_run.method is Method.ML:
            return await self._prediction(run, step_run, tuple(artifacts), consumption, trace)
        elif finished.outcome is Outcome.SUCCEEDED:
            checkpoint = Checkpoint(
                ref=checkpoint_ref or f"ckpt/{run.id}/{step_run.step_id}",
                step_id=step_run.step_id,
                taken_at=now,
                artifact_ids=tuple(a.id for a in artifacts),
            )
            step_run = step_run.to(
                StepState.SUCCEEDED,
                artifacts=tuple(artifacts),
                consumption=consumption,
                checkpoint=checkpoint,
                finished_at=now,
            )
            outcome = "succeeded"
        else:
            span.record_failure(f"assignment {finished.outcome}")
            step_run = step_run.to(
                StepState.FAILED,
                artifacts=tuple(artifacts),
                consumption=consumption,
                reason=finished.reason or f"the assignment ended {finished.outcome}",
                finished_at=now,
            )
            outcome = "failed"
        run = await self._commit(
            run.with_step_run(step_run),
            "step.finished",
            step=step_run,
            outcome=outcome,
            trace=trace,
        )
        return run, step_run

    def _predicted_from(self, step: Step, inputs: Mapping[str, Any]) -> list[ProvenanceInput]:
        """What an `ml` step reads beyond what earlier steps produced: its model, by the digest
        it is pinned at, and rows given in the work itself or behind a URI (ADR-0021, ADR-0076).
        Rows an earlier step produced are among the inputs `$from` already names."""
        now = self._clock.now()
        model = inputs.get("model") or {}
        read = [
            ProvenanceInput(
                kind=InputKind.SOURCE,
                capability=PREDICT,
                ref=f"model {step.model or 'unnamed'}"[:SOURCE_REF_LENGTH],
                digest=model.get("digest"),
                observed_at=now,
            )
        ]
        dataset = inputs.get("dataset") or {}
        if "uri" in dataset or "base64" in dataset:
            digest = dataset.get("digest")
            if digest is None and "base64" in dataset:
                digest = _digest(base64.b64decode(str(dataset["base64"])))
            read.append(
                ProvenanceInput(
                    kind=InputKind.SOURCE,
                    capability=PREDICT,
                    ref=f"rows {dataset.get('uri') or 'in the work'}"[:SOURCE_REF_LENGTH],
                    digest=digest,
                    observed_at=now,
                )
            )
        return read

    async def _prediction(
        self,
        run: Run,
        step_run: StepRun,
        artifacts: tuple[Artifact, ...],
        consumption: Consumption | None,
        trace: Trace,
    ) -> tuple[Run, StepRun]:
        """An `ml` step's assignment succeeded: its predictions are read, and the step's
        confidence decides where they go (ADR-0076). At or above its threshold the step
        finishes with a result that names the model, every row and the confidence. Below it,
        the step goes to its fallback: it waits for a person, the predictions stay recorded as
        its artifact and never become its result, and the steps that depend on it are held."""
        step = run.step(step_run.step_id)
        work = parse_work(step, run.work.get(step.id), run.inputs)
        if not isinstance(work, MlWork):  # unreachable: the method chose the work
            raise UnsupportedWork(step.id, "an ml step's work is a prediction")
        produced = next((a for a in artifacts if a.id == prediction.ARTIFACT), None)
        content = None if produced is None else await self._objects.get(produced.digest)
        now = self._clock.now()
        try:
            rows = prediction.rows(content)
        except prediction.Unreadable as unreadable:
            step_run = step_run.to(
                StepState.FAILED,
                artifacts=artifacts,
                consumption=consumption,
                reason=str(unreadable),
                finished_at=now,
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        confidence = prediction.lowest(rows)
        document: dict[str, Any] = {
            "model": step.model,
            "model_digest": work.model.digest,
            "confidence": confidence,
            "threshold": work.threshold.describe(),
        }
        if work.fallback is not None and produced is not None:  # rows() read it
            return await self._moved(
                run, step_run, work, artifacts, consumption, trace, rows, document
            )
        if work.threshold.unsure(confidence) and produced is not None:  # rows() read it
            fallback = {
                **document,
                "run_id": run.id,
                "step_id": step.id,
                "to": str(Method.HUMAN),
                "predictions": produced.digest,
            }
            digest = await self._objects.put(_canonical(fallback))
            run, step_run = await self._open_block(run, step_run, "wait.human", block.FELL_BACK)
            step_run = step_run.to(
                StepState.WAITING_HUMAN,
                artifacts=artifacts,
                consumption=consumption,
                reason=(
                    f"the model is unsure: confidence {confidence:g} meets the fallback "
                    f"{work.threshold.describe()}, so its answer does not leave the step; a "
                    "person performs the step and reports it performed"
                ),
            )
            run = await self._commit(
                self._hold_back(run.with_step_run(step_run), step.id),
                "step.awaiting",
                step=step_run,
                outcome=block.FELL_BACK,
                digest=digest,
            )
            return run, step_run
        document["rows"] = [row.document() for row in rows]
        content = _canonical(document)
        result_digest = await self._objects.put(content)
        result = Artifact(
            id="result",
            kind="result",
            digest=result_digest,
            media_type="application/json",
            size_bytes=len(content),
            created_at=now,
        )
        produced_now = (*artifacts, result)
        step_run = step_run.to(
            StepState.SUCCEEDED,
            artifacts=produced_now,
            consumption=consumption,
            checkpoint=Checkpoint(
                ref=f"ckpt/{run.id}/{step.id}",
                step_id=step.id,
                taken_at=now,
                artifact_ids=tuple(a.id for a in produced_now),
                result_digest=result_digest,
            ),
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(step_run),
            "step.finished",
            step=step_run,
            outcome="succeeded",
            trace=trace,
        )
        return run, step_run

    async def _moved(
        self,
        run: Run,
        step_run: StepRun,
        work: MlWork,
        artifacts: tuple[Artifact, ...],
        consumption: Consumption | None,
        trace: Trace,
        rows: Sequence[prediction.Row],
        document: Mapping[str, Any],
    ) -> tuple[Run, StepRun]:
        """A step moved from a language model to a trained model (ADR-0114 §4). When the model
        is sure — its confidence at or above the threshold — its class is the step's text.
        Otherwise the case goes to the language model the step was moved from, with the same
        prompt, and that answer is the step's text. Either way the result says which method
        answered and carries the model's rows, so that a dependant reads the text as it read
        the language model's, and a reader sees where each case went."""
        step = run.step(step_run.step_id)
        fallback = work.fallback
        if fallback is None:  # unreachable: the caller checked
            raise UnsupportedWork(step.id, "a moved step names the language model it falls to")
        confidence = float(document["confidence"])
        result: dict[str, Any] = {**document, "rows": [row.document() for row in rows]}
        used = consumption
        if not work.threshold.unsure(confidence) and len({row.label for row in rows}) == 1:
            result |= {"text": rows[0].label, "answered_by": str(Method.ML), "fell_back": False}
        else:
            attributes = {"run.id": run.id, "step.id": step.id}
            try:
                async with self._telemetry.span("model.fallback", attributes) as span:
                    value, read, spent, _ = await self._llm_step(run, step_run, fallback, span)
            except (_StepFailed, _AtLimit) as failure:
                spent_then = failure.consumption if isinstance(failure, _StepFailed) else None
                step_run = step_run.to(
                    StepState.FAILED,
                    artifacts=artifacts,
                    consumption=_added(consumption, spent_then),
                    reason=(
                        f"the model was unsure (confidence {confidence:g}, "
                        f"{work.threshold.describe()}), and the language model it falls back "
                        f"to did not answer: {failure.reason}"
                    ),
                    retryable=True,
                    finished_at=self._clock.now(),
                )
                run = await self._commit(
                    run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
                )
                return run, step_run
            result |= {
                "text": value["text"],
                "answered_by": str(Method.LLM),
                "fell_back": True,
                "fallback_model": value["model"],
            }
            used = _added(consumption, spent)
            trace = Trace(
                inputs=(*trace.inputs, *read.inputs), adapter_version=trace.adapter_version
            )
        now = self._clock.now()
        content = _canonical(result)
        result_digest = await self._objects.put(content)
        produced_now = (
            *artifacts,
            Artifact(
                id="result",
                kind="result",
                digest=result_digest,
                media_type="application/json",
                size_bytes=len(content),
                created_at=now,
            ),
        )
        step_run = step_run.to(
            StepState.SUCCEEDED,
            artifacts=produced_now,
            consumption=used,
            checkpoint=Checkpoint(
                ref=f"ckpt/{run.id}/{step.id}",
                step_id=step.id,
                taken_at=now,
                artifact_ids=tuple(a.id for a in produced_now),
                result_digest=result_digest,
            ),
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(step_run),
            "step.finished",
            step=step_run,
            outcome="succeeded",
            trace=trace,
        )
        return run, step_run

    async def _results(
        self, run: Run, referenced: set[StepId], artifacts: set[tuple[StepId, str]] | None = None
    ) -> tuple[dict[StepId, Any], tuple[ProvenanceInput, ...]]:
        """What the referenced steps produced, for `$from` — and the same as provenance
        inputs: a result by digest, or every artifact by identifier and digest, each with the
        moment it was read. A step referenced only through one of its artifacts is read too."""
        results: dict[StepId, Any] = {}
        read: list[ProvenanceInput] = []
        wanted = referenced | {step_id for step_id, _ in (artifacts or set())}
        for step_run in run.step_runs:
            if not step_run.done or step_run.step_id not in wanted:
                continue
            observed_at = self._clock.now()
            checkpoint = step_run.checkpoint
            if checkpoint is not None and checkpoint.result_digest is not None:
                content = await self._objects.get(checkpoint.result_digest)
                results[step_run.step_id] = None if content is None else json.loads(content)
                read.append(
                    ProvenanceInput(
                        kind=InputKind.RESULT,
                        run_id=run.id,
                        step_id=step_run.step_id,
                        digest=checkpoint.result_digest,
                        observed_at=observed_at,
                    )
                )
            else:
                results[step_run.step_id] = {
                    "artifacts": [a.document() for a in step_run.artifacts]
                }
                read.extend(
                    ProvenanceInput(
                        kind=InputKind.ARTIFACT,
                        run_id=run.id,
                        step_id=step_run.step_id,
                        artifact_id=artifact.id,
                        digest=artifact.digest,
                        observed_at=observed_at,
                    )
                    for artifact in step_run.artifacts
                )
        return results, tuple(read)

    # --- persistence and the ledger --------------------------------------------------------------

    async def _commit(
        self,
        run: Run,
        kind: str | None = None,
        *,
        step: StepRun | None = None,
        outcome: str | None = None,
        actor: str | None = None,
        trace: Trace | None = None,
        enqueue: Job | None = None,
        new: bool = False,
        trigger: Mapping[str, Any] | None = None,
        digest: Digest | None = None,
        decision: str | None = None,
        interface: str | None = None,
        ended: str | None = None,
        action: str | None = None,
        proposal: tuple[str, str | None, str] | None = None,
        before: Sequence[Mapping[str, Any]] = (),
        after: Sequence[Mapping[str, Any]] = (),
        inside: Callable[[], Awaitable[None]] | None = None,
    ) -> Run:
        """One transaction: the run as it now is, and — when `kind` is given — the ledger entry
        that says what changed. Either both land or neither does. A step that finished with a
        result gets its provenance record in the same transaction, bound to that entry; a job
        to `enqueue` lands in it too. `new` refuses a run that exists already (`RunExists`);
        `trigger` records the trigger that started the run as `run.triggered`; `interface`
        records a failed call that speaks about its interface as `interface.failed`, beside the
        step's entry (ADR-0047); `ended` records how the run ended, `ok`, `empty` or `error`, as
        `run.ended` with its duration from its creation (ADR-0107); `proposal` records the
        decision on a proposal — outcome, action class, document digest — as `proposal.decided`,
        naming no person (ADR-0110). `before` and `after` are further entries, each the
        arguments of `_record`, recorded before and after the entry of `kind`; `inside` is a
        write of the queue's that lands in the same transaction (ADR-0128)."""
        run = run.model_copy(update={"updated_at": self._clock.now()})
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            if new and await self._runs.get(run.tenant, run.id) is not None:
                raise RunExists(run.id)
            await self._runs.put(run.tenant, run)
            if enqueue is not None and self._queue is not None:
                await self._queue.enqueue(run.tenant, enqueue)
            if inside is not None:
                await inside()
            for extra in before:
                await self._record(run, **extra)
            if kind is not None:
                entry = await self._record(
                    run,
                    kind,
                    step=step,
                    outcome=outcome,
                    actor=actor,
                    digest=digest,
                    decision=decision,
                    action=action,
                )
                if proposal is not None and step is not None:
                    decided, held_by, document = proposal
                    await self._record(
                        run,
                        PROPOSAL_DECIDED,
                        step=step,
                        outcome=decided,
                        digest=document,
                        action=held_by,
                        bare=True,
                    )
                if interface is not None and step is not None:
                    await self._record(run, interfaces.RECORD_KIND, step=step, outcome=interface)
                if ended is not None:
                    took = (self._clock.now() - run.created_at).total_seconds()
                    await self._record(
                        run, RUN_ENDED, outcome=ended, duration=round(max(took, 0.0), 3)
                    )
                if trigger is not None:
                    # The ledger is content-free (ADR-0006): the entry names the trigger's kind
                    # and carries the digest of its document; the command keeps the document.
                    await self._record(
                        run,
                        "run.triggered",
                        outcome=str(trigger.get("kind", "trigger")),
                        actor=actor,
                        digest=_digest(_canonical(dict(trigger))),
                    )
                if step is not None and trace is not None and step.done:
                    await self._provenance.append(
                        run.tenant,
                        provenance.record(
                            run,
                            step,
                            id=self._ids.new("prov"),
                            inputs=trace.inputs,
                            entry=entry,
                            adapter_version=trace.adapter_version,
                            at=self._clock.now(),
                            route=trace.route,
                            scope=self._subject(run, step.step_id),
                        ),
                    )
                    if trace.egress is not None:
                        # The effect left the system: the egress entry names the step's
                        # result artifact and the digest of what went out (ADR-0022 §4).
                        await self._record(
                            run,
                            f"egress.{trace.egress.kind}",
                            step=step,
                            outcome="replayed" if trace.egress.replayed else "acted",
                            digest=trace.egress.content_digest,
                        )
                        if trace.message is not None:
                            # The message's record — case, checks, label — beside its egress
                            # entry, by digest (ADR-0142 §10).
                            await self._record(
                                run, messages.SENT, step=step, outcome="sent", digest=trace.message
                            )
                for extra in after:
                    await self._record(run, **extra)
        return run

    @staticmethod
    def _subject(run: Run, step_id: StepId) -> str | None:
        """The subject of the case the step served, for its provenance record; None for a step
        that serves no case (ADR-0130)."""
        scope = control_of(run.step(step_id), run.work.get(step_id), run.inputs).scope
        return None if scope is None else scope.subject

    async def _fence(self, run: Run) -> None:
        """Inside a transaction that writes the run: refuse it unless the claim the run is
        executed under is still this runner's. The queue keeps the claim from being taken
        until the transaction ends, so the writes land under the claim or not at all."""
        claim = self._claim.get()
        if claim is None or self._queue is None:
            return
        if not await self._queue.fence(run.tenant, claim):
            raise ClaimLost(
                f"run {run.id!r}: job {claim.job_id!r} was claimed again after "
                f"{claim.claimant!r} claimed it (attempt {claim.attempt}); the write is refused"
            )

    async def _record(
        self,
        run: Run,
        kind: str,
        *,
        step: StepRun | None = None,
        outcome: str | None = None,
        actor: str | None = None,
        digest: Digest | None = None,
        decision: str | None = None,
        duration: float | None = None,
        action: str | None = None,
        bare: bool = False,
    ) -> LedgerEntry:
        """`bare` records only what names the step — no assignment, no artifacts, no method,
        adapter or consumption — for an entry that counts a decision (ADR-0110)."""
        refs = LedgerRefs(
            tenant=run.tenant,
            plan_id=run.plan_id,
            process_version=run.process_version,
            run_id=run.id,
            step_id=None if step is None else step.step_id,
            assignment_id=None if step is None or bare else step.assignment_id,
            decision_request_id=decision,
            action=action,
            artifact_ids=None
            if step is None or bare or not step.artifacts
            else tuple(a.id for a in step.artifacts),
            actor=actor,
            # The trace this entry is recorded in: what joins the ledger and the telemetry.
            trace_id=self._telemetry.current_trace_id(),
        )
        entry = await self._entry(run, kind, step, outcome, refs, digest, duration, bare)
        if self._deadlines is not None:
            # In the same transaction: an entry that starts or meets a deadline does so with it.
            await self._deadlines.observe(
                run, kind, None if step is None else step.step_id, outcome
            )
        return entry

    async def _entry(
        self,
        run: Run,
        kind: str,
        step: StepRun | None,
        outcome: str | None,
        refs: LedgerRefs,
        digest: Digest | None,
        duration: float | None,
        bare: bool,
    ) -> LedgerEntry:
        consumption: Consumption | None = None
        if bare:
            return await self._ledger.record(
                run.tenant,
                Fact(
                    kind=kind,
                    refs=refs,
                    outcome=outcome,
                    content_digest=digest,
                    rehearsal=True if run.rehearsal else None,
                ),
            )
        if step is not None and kind not in (blocked.RECORD_KIND, interfaces.RECORD_KIND):
            if kind in ("step.admitted", "step.rejected") and step.estimate is not None:
                quantities = step.estimate.quantities()
                if quantities:
                    consumption = Consumption.model_validate(
                        {**quantities, "resource_class": step.estimate.resource_class}
                    )
            elif step.consumption is not None:
                consumption = step.consumption
        if digest is None and step is not None and step.checkpoint is not None:
            digest = step.checkpoint.result_digest
        return await self._ledger.record(
            run.tenant,
            Fact(
                kind=kind,
                refs=refs,
                method=None if step is None else step.method,
                adapter=None if step is None else step.adapter,
                consumption=consumption,
                outcome=outcome,
                duration_seconds=duration,
                content_digest=digest,
                rehearsal=True if run.rehearsal else None,  # ADR-0030
            ),
        )


EXACTNESS = "exactness"
"""The part of a `$run` reference that is the exactness statement of the run's version."""


def _names_exactness(value: Any) -> bool:
    """Whether a value carries `{"$run": "exactness"}` anywhere inside it."""
    if isinstance(value, Mapping):
        if value.get("$run") == EXACTNESS:
            return True
        return any(_names_exactness(v) for v in value.values())
    if isinstance(value, list | tuple):
        return any(_names_exactness(v) for v in value)
    return False


class _ChecksFailed(Exception):
    """A check the step declares disagreed with its value (ADR-0152)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _ToApprove(Exception):
    """The value is above an approval's threshold, and no person of its role has confirmed it
    yet (ADR-0152)."""

    def __init__(self, drafts: Callable[[int, date], Sequence[Draft]]) -> None:
        super().__init__("to approve")
        self.drafts = drafts


CHECK_FAILED = "check_failed"
"""The outcome of `step.finished` for a step whose value a check refused."""
SAMPLED = "check.sampled"
"""The ledger entry of a result a sampling check put to a person after the fact."""


class _Recount(Exception):
    """Another run of the process passed its caps while this one counted (ADR-0132 §2)."""

    def __init__(self, flying: frozenset[str]) -> None:
        super().__init__("recount")
        self.flying = flying


@dataclass(frozen=True)
class _AtLimit(Exception):
    """The model's provider answered at its rate limit: nothing was produced (ADR-0043)."""

    adapter: str
    reason: str
    retry_after_seconds: float | None = None
    """The delay the provider asked for in its `Retry-After`; None when it named none."""
    moves: bool = False
    """Another model of the purpose's chain fits the step: it moves there at its boundary
    instead of waiting (ADR-0116 §6)."""


@dataclass(frozen=True)
class _AdapterStopped(Exception):
    """The connector or the model a local step would call next is stopped: the call is not
    made, and the step stops at its boundary (ADR-0138, amendment)."""

    adapter: str
    consumption: Consumption | None = None
    """What the step used before, for a wait stopped between two checks."""


@dataclass(frozen=True)
class _Parked(Exception):
    """A wait step waits longer than the engine waits inline: the run parks (ADR-0103)."""

    check_at: datetime
    """When the wait is checked next: for a wait on the clock, when it ends."""
    consumption: Consumption | None
    """What the wait's checks used so far, its earlier parks included."""


@dataclass(frozen=True)
class _Gate:
    """What the frame of an outward message holds a connector step to (ADR-0142)."""

    rules: MessageRules
    message: Message | None = None
    """The step's message frame; None for an outward step held to the recipient limit alone."""
    drafted: bool = False
    """A model drafted what the step sends."""
    case: str | None = None
    refused: tuple[str, str] | None = None
    """Why nothing is sent, as the token `message.held` records and a reason."""
    anchors: tuple[Anchor, ...] = ()
    record: dict[str, Any] = field(default_factory=dict)
    """What `message.sent` names by digest."""

    def refusing(self, token: str, reason: str) -> _Gate:
        return dataclasses.replace(self, refused=(token, reason))

    def anchored(self, anchors: tuple[Anchor, ...]) -> _Gate:
        return dataclasses.replace(self, anchors=anchors)


def _holding(step_run: StepRun) -> bool:
    """Whether the step is an approved message held at its boundary (ADR-0142 §8)."""
    return step_run.block is not None and step_run.block.cause == block.HOLDING_MESSAGE


def _parked_wait(step_run: StepRun) -> bool:
    """Whether the step run is a wait step parked at its boundary (ADR-0103)."""
    return step_run.block is not None and step_run.block.next_check_at is not None


_NOT_FOUND: Any = object()
"""What a wait observed when the read answered `not_found`."""


@dataclass(frozen=True)
class _StepFailed(Exception):
    """A local step that did not complete for a reason that is not a rule's: the connector
    refused, vanished or broke its contract, a wait ran out. Carries what the step run records."""

    reason: str
    retryable: bool | None
    consumption: Consumption | None
    adapter: str | None
    outcome: str
    lack: tuple[str, str] | None = None
    """For a step that failed for want of an adapter: the cause token of the lack and what was
    lacking. The step then carries a block until it can start (ADR-0046)."""
    interface: str | None = None
    """For a call through a connector that failed in a way that speaks about its interface: the
    token `interface.failed` records (ADR-0047)."""
    not_found: bool = False
    """The connector answered `not_found`: a wait on an outside state reads that as a state
    not reached yet (ADR-0103 §6)."""
    moves: bool = False
    """The call failed on one model of the purpose's chain, and another fits the step: it moves
    there at its boundary instead of escalating (ADR-0116 §6)."""
    frame: str | None = None
    """The call was refused by the step's frame, or by its connector as out of the case's
    scope: the token `frame.refused` records (ADR-0130)."""
    held: str | None = None
    """The message was not sent at the call: the token `message.held` records (ADR-0142)."""


def _no_model(routed: routing.Route) -> str:
    """Why no model serves the step, naming the settings that configure one."""
    return f"{routed.why_none()} (TAKTUS_MODELS, TAKTUS_MODEL_ENDPOINT, TAKTUS_MODEL_NAME)"


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _canonical(document: Any) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _undeclared(operation: str) -> str:
    return (
        f"the operation {operation} declares no demand, so a call to it has no estimate; its "
        "connector must declare what one call consumes (contracts/connector/v1, Demand)"
    )


def _times(demand: Mapping[str, Any], calls: int) -> ConsumptionQuantities:
    """A declared demand for `calls` calls."""
    quantities: dict[str, Any] = {}
    for name, value in demand.items():
        if name == "currency":
            quantities[name] = {code: amount * calls for code, amount in value.items()}
        else:
            quantities[name] = value * calls
    if "compute_seconds" in quantities:
        quantities["resource_class"] = "connector"
    return ConsumptionQuantities.model_validate(quantities)


def _released(run: Run, step_id: StepId) -> Run:
    """The run with the given step's reservation released, its own earlier use kept: the step
    is being admitted again, and its old reservation is replaced."""
    for step_run in run.step_runs:
        if step_run.step_id == step_id and step_run.reservation is not None:
            return run.with_step_run(step_run.model_copy(update={"reservation": None}))
    return run


def _measured(span: Span, step_run: StepRun) -> None:
    """What the step used, as span attributes: quantities and their class, never content."""
    span.set_attribute("step.state", step_run.state)
    consumption = step_run.consumption
    if consumption is None:
        return
    for name, value in consumption.quantities().items():
        if name == "tokens_by_model":
            continue  # model names are configuration, and the totals are already attributes
        if name == "currency" and isinstance(value, dict):
            for code, amount in value.items():
                span.set_attribute(f"consumption.currency.{code}", float(amount))
        elif isinstance(value, int | float):
            span.set_attribute(f"consumption.{name}", value)
    if consumption.resource_class is not None:
        span.set_attribute("consumption.resource_class", consumption.resource_class)


def _accumulate(used: dict[str, Any], event: ConsumptionQuantities) -> None:
    for name, value in event.quantities().items():
        if name == "tokens_by_model":
            used[name] = add_tokens_by_model(used.get(name), value)
        elif name == "currency" and isinstance(value, dict):
            totals: dict[str, float] = used.setdefault("currency", {})
            for code, amount in value.items():
                totals[code] = totals.get(code, 0.0) + amount
        elif isinstance(value, int | float):
            used[name] = used.get(name, 0) + value
    if event.resource_class is not None:
        used["resource_class"] = event.resource_class
    # Beside the quantities: where the tokens went (#449), summed over the step's events.
    if event.turns is not None:
        used["turns"] = used.get("turns", 0) + event.turns
    if event.compression is not None:
        held = used.get("compression")
        used["compression"] = event.compression if held is None else held.plus(event.compression)


def _added(*parts: Consumption | None) -> Consumption | None:
    """What several parts of one step used, together: a moved step's prediction and the
    completion it fell back to (ADR-0114 §4)."""
    used: dict[str, Any] = {}
    for part in parts:
        if part is not None:
            _accumulate(used, part)
    return _consumption(used)


def _consumption(used: dict[str, Any]) -> Consumption | None:
    if not any(name in used for name in QUANTITIES):
        return None
    return Consumption.model_validate(used)


def _credential_names(work: Work) -> list[str]:
    """The credentials a step's work names, resolved: a connector call's, a wait's on one, a
    worker's assignment's."""
    if isinstance(work, ConnectorRule | WorkerWork):
        return [c.name for c in work.credentials]
    if isinstance(work, WaitWork) and work.until is not None:
        return [c.name for c in work.until.credentials]
    return []


def _message_inputs(step_run: StepRun) -> tuple[ProvenanceInput, ...]:
    """The persons' messages the step's worker received, as inputs of its provenance: each by
    its identifier and its text's digest, read when it was received (ADR-0156 §9)."""
    return tuple(
        ProvenanceInput(
            kind=InputKind.MESSAGE,
            ref=message.message_id,
            digest=message.digest,
            observed_at=message.received_at,
        )
        for message in step_run.messages
    )
