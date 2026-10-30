"""Aggregates with every field filled, for round trips. Built from the shipped example where
one exists, so that the shape the tests store is the shape the product stores."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import yaml

from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    Configuration,
    ConformanceResult,
    ProcessFinding,
    RemovalResult,
    RunSummary,
    StepFinding,
    Verdict,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.decision.domain.model import RegisterEntry, Request
from taktus.components.governance.domain.model import (
    AnchorConfiguration,
    CaseAnswer,
    CorrectionLimits,
    Happening,
    Incident,
    IncidentKind,
    MessageRules,
    ResidencyRule,
    RunSeen,
    SourceDeclaration,
    Stage,
    StagePlan,
    WatchConfiguration,
    case_key,
)
from taktus.components.identity.domain.model import (
    BrowserSession,
    ChannelLink,
    Identity,
    LinkCode,
    LinkOrigin,
    Right,
    RoleRights,
    code_id,
    digest,
    link_id,
    session_id,
)
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import (
    CorrectedCase,
    Evaluation,
    EvaluationCase,
    Expect,
    Process,
    ProcessVersion,
    Slo,
    Trigger,
    TriggerState,
)
from taktus.components.reporting.domain.model import Corridor, OwnerChannel, Report, Subject
from taktus.components.run.domain.model import (
    ActionKind,
    AdapterStop,
    Anchoring,
    Checkpoint,
    Deadline,
    DeadlineAction,
    DeadlineRule,
    OpenBlock,
    ReceivedMessage,
    Run,
    RunState,
    Start,
    StepState,
    StopState,
    WorkingTime,
    deadline_id,
)
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Artifact,
    Command,
    Commissioned,
    Consumption,
    ConsumptionQuantities,
    Intent,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    ReplyTo,
)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "processes" / "six-times-seven.yaml"
AT = datetime(2026, 9, 16, 12, 0, 0, 123456, tzinfo=UTC)
DIGEST = "sha256:" + "ab" * 32


def bundle() -> dict[str, Any]:
    with EXAMPLE.open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    return document


def process_version(version: str = "1", tenant: str = "t") -> ProcessVersion:
    document = bundle()
    document["version"] = version
    document["triggers"] = [
        {"schedule": "0 6 * * 1-5"},
        {"event": "issue.labelled", "filter": {"label": ["ready", "now"]}},
    ]
    document["slo"] = {"freshness": "24h", "latency": "90s"}
    document["expect"] = {"schedule": "0 7 * * 1-5", "bound": "2h"}
    document["open_work"] = {
        "pull_requests": {
            "cap": 2,
            "reading": {"operation": "repository.pullrequests.list", "select": "pull_requests"},
            "check_every": "30m",
        }
    }
    document["deadlines"] = {
        "answer": {
            "from": "run",
            "limit": "1d",
            "lead": "4h",
            "counts": "working",
            "until": {"step": "settle"},
            "at_lead": {"remind": "operations"},
            "at_limit": {"escalate": "operations-lead"},
        },
        "follow_up": {
            "from": {"after": "compute"},
            "limit": "2h",
            "until": {"step": "verify-answer"},
            "at_limit": {"start": {"process": "six-times-seven", "inputs": {"a": 1}}},
        },
    }
    document["evaluation"] = {
        "cases": [
            {
                "id": "forty-two",
                "targets": {"prepare-commands": {"commands": ["expr 6 '*' 7"]}, "compute": "42"},
            }
        ],
        "scorers": [
            {
                "step": "prepare-commands",
                "method": "rule",
                "reason": "the commands are fixed",
                "exactness": "exact",
                "rule": {"kind": "equals"},
            },
            {
                "step": "compute",
                "method": "llm",
                "reason": "the worker's answer may be phrased in many ways",
                "rejected": [{"method": "rule", "why": "a number may be written in words"}],
                "exactness": "tolerant",
                "fallback": {"when": "the judge gives no score", "to": "rule"},
                "rule": {"kind": "contains"},
                "purpose": "judging",
                "criterion": "Does the answer give the same number?",
            },
        ],
        "schedule": "weekly",
    }
    parsed = parse_bundle(document)
    assert parsed.evaluation is not None and len(parsed.evaluation.scorers) == 2
    assert parsed.open_work["pull_requests"].check_every == timedelta(minutes=30)
    assert parsed.deadlines["answer"].working and parsed.deadlines["answer"].lead == timedelta(
        hours=4
    )
    assert parsed.triggers == (
        Trigger(schedule="0 6 * * 1-5"),
        Trigger(event="issue.labelled", filter={"label": ("ready", "now")}),
    )
    assert parsed.slo == Slo(freshness=timedelta(hours=24), latency=timedelta(seconds=90))
    assert parsed.expect == Expect(schedule="0 7 * * 1-5", bound=timedelta(hours=2))
    return parsed


def process(tenant: str = "t") -> Process:
    return Process(
        id="six-times-seven",
        name="Six times seven",
        active_version="1",
        activated_by="idn_ada",
        activated_at=datetime(2026, 10, 10, 9, 0, tzinfo=UTC),
    )


def command(id: str = "cmd_1", tenant: str = "t") -> Command:
    return Command(
        id=id,
        channel="channel.cli",
        identity="idn_1",
        org_path=(tenant, "dev"),
        intent=Intent(raw="run it", recognised="process.run"),
        context={"issue": 7, "thread": "abc"},
        reply_to=ReplyTo(channel="channel.cli", address="stdout", thread="abc"),
        received_at=AT,
    )


def adapter_maturity(id: str = "worker.endpoint", tenant: str = "t") -> AdapterMaturity:
    return AdapterMaturity(
        id=id,
        tenant=tenant,
        family="worker",
        conformance=ConformanceResult(
            integration=id,
            family="worker",
            contract="worker/v1",
            taktus_version="0.0.0",
            configuration=Configuration(adapter=id, serves=("shell.script",), version="0.1.0"),
            outcome="failed",
            failed=("W-05",),
            inconclusive=("W-14",),
            digest="sha256:" + "1" * 64,
            tested_at=AT,
            actor="idn_ada",
            run_id="run_s01",
        ),
        removal=RemovalResult(
            integration=id,
            family="worker",
            verdict=Verdict.CHANGED,
            tested_at=AT,
            run_id="run_removal_1",
            processes=(
                ProcessFinding(
                    process="six-times-seven@1",
                    exercised="run",
                    verdict=Verdict.CHANGED,
                    steps=(
                        StepFinding(
                            step="compute",
                            served="shell.script",
                            alternative=None,
                            fallback=Method.HUMAN,
                            verdict=Verdict.CHANGED,
                            reason="no other adapter serves shell.script; a person takes over",
                        ),
                    ),
                    baseline=RunSummary(
                        run_id="run_a", state="halted", cause="limit", at_step="overreach"
                    ),
                    withheld=RunSummary(
                        run_id="run_b", state="escalated", cause="failure", at_step="compute"
                    ),
                    note="stops at compute, where a person takes over",
                ),
            ),
        ),
        updated_at=AT + timedelta(seconds=5),
    )


def intake_event(id: str = "placeholder-delivery-1", tenant: str = "t") -> IntakeEvent:
    return IntakeEvent(
        id=id,
        tenant=tenant,
        channel="channel.repo",
        event="issue_comment.created",
        sender_account="100000001",
        sender_kind="person",
        intent="@taktus turn this into a pull request",
        context={"repository": "placeholder-owner/placeholder-repo", "issue": "412"},
        reply_channel="channel.repo",
        reply_address="placeholder-owner/placeholder-repo#412",
        reply_thread="3000000001",
        occurred_at=AT,
        received_at=AT + timedelta(seconds=2),
    )


def plan(id: str = "pln_1", tenant: str = "t") -> Plan:
    return Plan(
        id=id,
        command_id="cmd_1",
        goal="run process six-times-seven",
        autonomy_level=2,
        due=AT + timedelta(days=1),
        steps=process_version().ordered(),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_1", at=AT),
    )


def run(id: str = "run_1", tenant: str = "t") -> Run:
    """A run two steps in: the first succeeded with a result, the second is running with the
    worker's first boundary persisted, the rest are planned."""
    version = process_version()
    fresh = Run(
        id=id,
        plan_id="pln_1",
        process_version=version.ref,
        tenant=tenant,
        identity="idn_t",
        autonomy_level=2,
        budget=Limits(compute=ComputeLimit(seconds=2, resource_class="cpu.small")),
        steps=version.ordered(),
        work=version.work,
        deadlines=(deadline_rule(),),
        bindings={"drafting": "model.candidate"},
        state=RunState.RUNNING,
        created_at=AT,
        updated_at=AT + timedelta(seconds=5),
    )
    first = (
        fresh.step_run("prepare-commands")
        .to(StepState.ADMITTED)
        .to(StepState.RUNNING, started_at=AT + timedelta(seconds=1))
    )
    first = first.to(
        StepState.SUCCEEDED,
        artifacts=(
            Artifact(
                id="result",
                kind="result",
                digest=DIGEST,
                media_type="application/json",
                size_bytes=12,
                created_at=AT + timedelta(seconds=2),
            ),
        ),
        checkpoint=Checkpoint(
            ref=f"ckpt/{id}/prepare-commands",
            step_id="prepare-commands",
            taken_at=AT + timedelta(seconds=2),
            artifact_ids=("result",),
            result_digest=DIGEST,
        ),
        finished_at=AT + timedelta(seconds=2),
    )
    second = fresh.step_run("compute").to(
        StepState.ADMITTED,
        adapter="worker.http",
        estimate=ConsumptionQuantities(compute_seconds=1.0, resource_class="cpu.small"),
    )
    second = second.to(
        StepState.RUNNING, assignment_id="asg_0001", started_at=AT + timedelta(seconds=3)
    )
    second = second.model_copy(
        update={
            "artifacts": (
                Artifact(
                    id="output-1",
                    kind="log",
                    digest=DIGEST,
                    media_type="text/plain",
                    size_bytes=3,
                    uri="worker://asg_0001/output-1",
                    title="expr 6 '*' 7",
                    created_at=AT + timedelta(seconds=4),
                ),
            ),
            "consumption": Consumption(compute_seconds=0.5, resource_class="cpu.small"),
            "confirmed_by": "idn_ada",
            "anchoring": Anchoring(
                requests=("dr_0123456789abcdef01234567",),
                round=1,
                verdict="proceed",
                decided_by="idn_ada",
            ),
            "messages": (
                ReceivedMessage(
                    message_id="msg_0001", digest=DIGEST, received_at=AT + timedelta(seconds=4)
                ),
            ),
            "checkpoint": Checkpoint(
                ref="ckpt/asg_0001/0",
                step_id="compute",
                taken_at=AT + timedelta(seconds=4),
                artifact_ids=("output-1",),
            ),
        }
    )
    # The third step is held back behind the second, in a block that has not ended (ADR-0043).
    third = fresh.step_runs[2].model_copy(
        update={
            "block": OpenBlock(
                account="wait.dependency",
                cause="held_back",
                since=AT + timedelta(seconds=3),
                on="compute",
            )
        }
    )
    return fresh.with_step_run(first).with_step_run(second).with_step_run(third)


def rehearsal_run(id: str = "run_2", tenant: str = "t") -> Run:
    """The same run as a rehearsal (ADR-0030): the flag survives the round trip."""
    return run(id, tenant).model_copy(update={"rehearsal": True})


def trigger_state(tenant: str = "t") -> TriggerState:
    return TriggerState(
        id="six-times-seven:trg_0123456789abcdef0123",
        process_id="six-times-seven",
        schedule="0 6 * * 1-5",
        armed_at=AT,
        fired_slot=datetime(2026, 9, 17, 6, 0, tzinfo=UTC),
        fired_at=AT + timedelta(days=1),
        runs=("run_a", "run_b"),
    )


def identity(tenant: str = "t") -> Identity:
    return Identity(
        id="idn_ada",
        tenant=tenant,
        org_path=(tenant, "finance", "payables"),
        roles=("finance.lead", "owner"),
        key_digest="ab" * 32,
        agent_key_digest="cd" * 32,
        created_at=AT,
    )


def anchor_configuration(tenant: str = "t") -> AnchorConfiguration:
    examples = ROOT / "contracts/shared/v1/examples/anchor/valid"
    anchors = []
    for name in ("payment-release", "correction-after-delivery", "release"):
        anchor = json.loads((examples / f"{name}.json").read_text())
        anchor.pop("scope", None)
        anchors.append(anchor)
    return AnchorConfiguration.model_validate(
        {
            "id": tenant,
            "tenant": tenant,
            "anchors": anchors,
            "risk_classes": {
                "financial.high": ["payment.release:large"],
                "egress.any": ["correction.execute:*"],
            },
            "configured_at": AT,
            "configured_by": "idn_admin",
        }
    )


def decision_request(tenant: str = "t") -> Request:
    shaped = json.loads(
        (ROOT / "contracts/shared/v1/examples/decision-request/valid/applied.json").read_text()
    )
    return Request.model_validate(
        {
            "id": shaped["id"],
            "tenant": tenant,
            "decider": "product.owner",
            "anchor": "anc-release",
            "raised_at": AT,
            "request": shaped,
            "answered_by": "idn_ada",
            "answered_at": AT + timedelta(hours=2),
            "reflection": "I read your answer as option A. Confirm to apply this.",
            "decided_by": "idn_ada",
            "decided_at": AT + timedelta(hours=2, minutes=1),
        }
    )


def register_entry(tenant: str = "t") -> RegisterEntry:
    return RegisterEntry.model_validate(
        {
            "id": "dce_2026-014",
            "tenant": tenant,
            "request_id": "DR-2026-014",
            "run_id": "run_17342",
            "step_id": "roadmap-consistency",
            "class": "strategic",
            "anchor": "anc-release",
            "decider": "product.owner",
            "option": "A",
            "proposal": "Ship 0.2.0 without the chat connector.",
            "modifications": "release notes name the missing connector",
            "answer_raw": "yes, ship it, but mention the gap in the release notes",
            "decided_by": "idn_ada",
            "raised_at": AT,
            "answered_at": AT + timedelta(hours=2),
            "decided_at": AT + timedelta(hours=2, minutes=1),
        }
    )


def channel_link(tenant: str = "t") -> ChannelLink:
    return ChannelLink(
        id=link_id("channel.repo", "100200"),
        tenant=tenant,
        channel="channel.repo",
        account="100200",
        identity="idn_ada",
        origin=LinkOrigin.CONFIRMED,
        linked_at=AT,
        revoked_at=AT + timedelta(days=1),
        revoked_by="idn_admin",
    )


def link_code(tenant: str = "t") -> LinkCode:
    return LinkCode(
        id=code_id("tkl-" + "0" * 24),
        tenant=tenant,
        identity="idn_ada",
        channel="channel.repo",
        created_at=AT,
        expires_at=AT + timedelta(minutes=30),
        used_at=AT + timedelta(minutes=1),
    )


def browser_session(tenant: str = "t") -> BrowserSession:
    return BrowserSession(
        id=session_id("tks_" + "0" * 64),
        tenant=tenant,
        identity="idn_ada",
        key_digest=digest("tka_" + "0" * 64),
        created_at=AT,
        expires_at=AT + timedelta(hours=12),
        ended_at=AT + timedelta(hours=1),
    )


def role_rights(tenant: str = "t") -> RoleRights:
    return RoleRights(id="finance.lead", tenant=tenant, rights=(Right.ANSWER, Right.START))


PHRASEBOOK = json.loads(
    (ROOT / "src/taktus/composition/phrasebooks/de.json").read_text(encoding="utf-8")
)


def owner_channel(tenant: str = "t") -> OwnerChannel:
    return OwnerChannel.model_validate(
        {
            "id": tenant,
            "tenant": tenant,
            "owner": "idn_owner",
            "named": ["idn_deputy"],
            "roles": ["owner", "product.owner"],
            "channel": "channel.chat",
            "address": "D0000000001",
            "phrasebook": PHRASEBOOK,
            "task": {"capability": "repository.issues", "operation": "repository.issues.create"},
            "view_base": "https://taktus.example/instance",
            "configured_at": AT,
            "configured_by": "operator",
        }
    )


def report(tenant: str = "t") -> Report:
    return Report.model_validate(
        {
            "id": "dr_run17342_release_1",
            "tenant": tenant,
            "kind": "decision",
            "title": "Run run_17342 has reached step release, whose act is anchored.",
            "needed": ["Does Taktus release the payment?"],
            "steps": ["A: Release it. (Proposed here.)", "B: Do not release it."],
            "standing_still": ["run_17342", "run_17342/release"],
            "due": (AT + timedelta(days=3)).date().isoformat(),
            "offered": [
                {"id": "A", "label": "Release it.", "recommended": True},
                {"id": "B", "label": "Do not release it."},
            ],
            "links": [{"label": "Run", "url": "https://taktus.example/runs/run_17342"}],
            "raised_at": AT,
            "state": "filed",
            "filed": {
                "answer": "A",
                "by": "idn_owner",
                "at": AT + timedelta(hours=2),
                "record": "dce_run17342_release_1",
                "where": "channel.chat D0000000001 1700000000.000100",
            },
            "deliveries": [
                {
                    "channel": "task",
                    "state": "delivered",
                    "at": AT,
                    "record": "issue:412",
                    "url": "https://repository.example/issues/412",
                },
                {
                    "channel": "message",
                    "state": "failed",
                    "at": AT,
                    "reason": "unreachable",
                    "address": "D0000000001",
                },
                {
                    "channel": "message",
                    "state": "delivered",
                    "at": AT + timedelta(minutes=5),
                    "address": "D0000000001",
                    "thread": "1700000000.000100",
                    "record": "chat.message:D0000000001/1700000000.000100",
                },
            ],
            "history": [
                {"at": AT, "event": "raised"},
                {"at": AT + timedelta(hours=1), "event": "reflected", "by": "idn_owner"},
                {"at": AT + timedelta(hours=2), "event": "filed", "by": "idn_owner"},
            ],
        }
    )


def incident(tenant: str = "t") -> Incident:
    last = RunSeen(at=AT - timedelta(days=1), run_id="run_0", kind="run.started")
    return Incident(
        id="inc_0123456789abcdef0123",
        tenant=tenant,
        kind=IncidentKind.MISSING,
        process_id="six-times-seven",
        process_version="six-times-seven@1",
        expected_at=AT,
        last_run=last,
        rule="expected.slot",
        facts={"schedule": "0 7 * * 1-5", "grace_seconds": 900.0},
        raised_at=AT + timedelta(minutes=15),
        timeline=(
            Happening(
                at=AT + timedelta(minutes=15),
                what="missed",
                expected_at=AT,
                deadline=AT + timedelta(minutes=15),
            ),
            Happening(
                at=AT + timedelta(hours=1),
                what="happened",
                run=RunSeen(at=AT + timedelta(minutes=50), run_id="run_1", kind="run.started"),
            ),
        ),
    )


def watch_configuration(tenant: str = "t") -> WatchConfiguration:
    return WatchConfiguration(
        id=tenant,
        tenant=tenant,
        grace=timedelta(minutes=5),
        empty_share=0.75,
        empty_window=timedelta(days=7),
        empty_minimum=4,
        configured_at=AT,
    )


def corridor(tenant: str = "t") -> Corridor:
    return Corridor(
        id="cost.cloud_daily@2",
        tenant=tenant,
        signal="cost.cloud_daily",
        version=2,
        process="read-cloud-cost",
        step="read-cost",
        select="totals.eur",
        about=Subject(kind="department", name="engineering"),
        bounds="median",
        yellow=1.5,
        red=2.0,
        window=timedelta(days=7),
        minimum=5,
        fresh=timedelta(hours=26),
        role="owner",
        case="https://tickets.example/board/cost",
        interventions=("throttle-cloud",),
        changed_at=AT,
    )


def lowering_incident(tenant: str = "t") -> Incident:
    """An incident about a level that fell by rule: no expected time (ADR-0110)."""
    return Incident(
        id="inc_level",
        tenant=tenant,
        kind=IncidentKind.BREACH,
        process_id="p",
        process_version="p@1",
        run_id="run_1",
        rule="anchor.breach",
        facts={"anchors": "anc-write", "level_before": "3", "level_after": "2"},
        raised_at=AT,
    )


def residency_rule(tenant: str = "t") -> ResidencyRule:
    return ResidencyRule(
        id=tenant, tenant=tenant, location="eu", classes={"personal": "own"}, configured_at=AT
    )


def source_declaration(tenant: str = "t") -> SourceDeclaration:
    return SourceDeclaration(
        id=tenant,
        tenant=tenant,
        free=("analytics.cohorts",),
        personal=("customers.accounts",),
        configured_at=AT,
    )


def message_rules(tenant: str = "t") -> MessageRules:
    return MessageRules(
        id=tenant,
        tenant=tenant,
        label="Written by an AI system; a person reads every answer.",
        delay_seconds=900,
        quiet_begins=time(22, 0),
        quiet_ends=time(7, 0),
        zone="Europe/Berlin",
        recipient_limit=5,
        configured_at=AT,
    )


def case_answer(tenant: str = "t") -> CaseAnswer:
    return CaseAnswer(
        id=case_key("support-reply", "ticket-17"),
        tenant=tenant,
        process="support-reply",
        case="ticket-17",
        answered_at=AT,
    )


def correction_limits(tenant: str = "t") -> CorrectionLimits:
    return CorrectionLimits(
        id=tenant,
        tenant=tenant,
        raise_decisions=10,
        raise_weeks=2,
        raise_rate=0.1,
        lower_rate=0.3,
        lower_window=timedelta(days=14),
        lower_minimum=3,
        configured_at=AT,
    )


def deadline_rule() -> DeadlineRule:
    return DeadlineRule(
        name="answer",
        start=Start.RUN,
        limit=timedelta(days=1),
        lead=timedelta(hours=4),
        working=True,
        until="settle",
        at_lead=DeadlineAction(kind=ActionKind.REMIND, role="operations"),
        at_limit=DeadlineAction(kind=ActionKind.ESCALATE, role="operations-lead"),
    )


def deadline(tenant: str = "t") -> Deadline:
    """A deadline whose lead action was taken and whose limit has not come (ADR-0133)."""
    return Deadline(
        id=deadline_id("run_1", "answer"),
        tenant=tenant,
        run_id="run_1",
        process_version="six-times-seven@1",
        rule=deadline_rule(),
        started_at=AT,
        due_at=AT + timedelta(days=1),
        lead_at=AT + timedelta(hours=20),
        created_at=AT,
        lead_taken_at=AT + timedelta(hours=20, seconds=3),
    )


def stage_plan(tenant: str = "t") -> StagePlan:
    """Two stages, the second bounded on every figure (ADR-0137)."""
    return StagePlan.model_validate(
        {
            "id": tenant,
            "tenant": tenant,
            "responsible": "operations",
            "blueprint": "software-operations",
            "stages": [
                Stage.model_validate(
                    {"id": "control-loop", "name": "The control loop", "processes": {"b-9-01": 2}}
                ),
                Stage.model_validate(
                    {
                        "id": "operation-without-handwork",
                        "name": "Operation without handwork",
                        "processes": {"b-1-01": 3, "b-2-01": 2},
                        "condition": {
                            "weeks": 4,
                            "runs": 20,
                            "missed": 0,
                            "incidents": 1,
                            "correction_rate": 0.1,
                            "undecided": 0,
                        },
                    }
                ),
            ],
            "configured_at": AT,
        }
    )


def working_time(tenant: str = "t") -> WorkingTime:
    return WorkingTime(
        id=tenant,
        tenant=tenant,
        zone="Europe/Berlin",
        days=(0, 1, 2, 3),
        begins=time(8, 30),
        ends=time(16, 0),
        holidays=(date(2026, 12, 25),),
        configured_at=AT,
    )


def evaluation(tenant: str = "t") -> Evaluation:
    """An evaluation of a proposal beside the active version, scored and overridden (ADR-0134)."""
    version = process_version(tenant=tenant)
    assert version.evaluation is not None
    return Evaluation.model_validate(
        {
            "id": "evl_1",
            "tenant": tenant,
            "process_id": version.process_id,
            "purpose": "change",
            "version": version.ref,
            "proposal": "prp_1",
            "candidate": f"{version.process_id}@proposal-prp_1",
            "acting_for": "idn_ada",
            "cases": [c.document() for c in version.evaluation.cases],
            "scorers": [s.document() for s in version.evaluation.scorers],
            "runs": [
                {"case": "forty-two", "side": "active", "run_id": "run_a"},
                {
                    "case": "forty-two",
                    "side": "proposed",
                    "run_id": "run_b",
                    "judges": {"compute.1": "run_c"},
                },
                {"case": "personal", "side": "active", "left_out": "it keeps a subject"},
            ],
            "state": "scored",
            "results": [
                {
                    "case": "forty-two",
                    "side": "proposed",
                    "run_id": "run_b",
                    "run_state": "finished",
                    "score": 0.5,
                    "scores": [
                        {
                            "scorer": "prepare-commands.0",
                            "step": "prepare-commands",
                            "method": "rule",
                            "exactness": "exact",
                            "score": 1.0,
                            "how": "rule",
                        },
                        {
                            "scorer": "compute.1",
                            "step": "compute",
                            "method": "llm",
                            "exactness": "tolerant",
                            "score": 0.0,
                            "how": "judge",
                        },
                    ],
                    "models": {"compute": "a-model-20261001"},
                    "seconds": 3.5,
                    "tokens_in": 120,
                    "tokens_out": 8,
                },
                {"case": "personal", "side": "active", "left_out": "it keeps a subject"},
            ],
            "sides": [
                {"side": "active", "version": version.ref, "score": 1.0, "cases": 1, "unscored": 0},
                {
                    "side": "proposed",
                    "version": f"{version.process_id}@proposal-prp_1",
                    "score": 0.5,
                    "cases": 1,
                    "unscored": 0,
                },
            ],
            "verdict": "regressed",
            "tolerance": 0.05,
            "started_at": AT.isoformat(),
            "scored_at": (AT + timedelta(minutes=3)).isoformat(),
            "override": {
                "reason": "the old answer was wrong",
                "at": AT.isoformat(),
            },
        }
    )


def corrected_case(tenant: str = "t") -> CorrectedCase:
    return CorrectedCase(
        id="cor-1",
        tenant=tenant,
        process_id="six-times-seven",
        case=EvaluationCase(id="cor-1", inputs={"message": "late"}, targets={"compute": "42"}),
        state="confirmed",  # type: ignore[arg-type]
        source_run="run_1",
        source_step="compute",
        left_out=("mailbox",),
        proposed_at=AT,
        decided_at=AT + timedelta(hours=1),
    )


def adapter_stop(tenant: str = "t") -> AdapterStop:
    """A stop of an adapter that held and was confirmed, naming the run it halted (ADR-0138)."""
    return AdapterStop(
        id="stp_1",
        tenant=tenant,
        adapter="worker.coding",
        requested_by="idn_operator",
        requested_at=AT,
        created_at=AT,
        state=StopState.CONFIRMED,
        confirmed_at=AT + timedelta(seconds=40),
        stopped=("run_1",),
    )
