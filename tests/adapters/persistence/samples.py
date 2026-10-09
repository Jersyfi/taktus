"""Aggregates with every field filled, for round trips. Built from the shipped example where
one exists, so that the shape the tests store is the shape the product stores."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    ProcessFinding,
    RemovalResult,
    RunSummary,
    StepFinding,
    Verdict,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.decision.domain.model import RegisterEntry, Request
from taktus.components.governance.domain.model import AnchorConfiguration
from taktus.components.identity.domain.model import (
    ChannelLink,
    Identity,
    LinkCode,
    LinkOrigin,
    code_id,
    link_id,
)
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import (
    Process,
    ProcessVersion,
    Slo,
    Trigger,
    TriggerState,
)
from taktus.components.reporting.domain.model import OwnerChannel, Report
from taktus.components.run.domain.model import (
    Anchoring,
    Checkpoint,
    OpenBlock,
    Run,
    RunState,
    StepState,
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
    document["triggers"] = [{"schedule": "0 6 * * 1-5"}, {"event": "repo.push", "filter": "x"}]
    document["slo"] = {"freshness": "24h", "latency": "90s"}
    parsed = parse_bundle(document)
    assert parsed.triggers == (
        Trigger(schedule="0 6 * * 1-5"),
        Trigger(event="repo.push", filter="x"),
    )
    assert parsed.slo == Slo(freshness=timedelta(hours=24), latency=timedelta(seconds=90))
    return parsed


def process(tenant: str = "t") -> Process:
    return Process(
        id="six-times-seven", name="Six times seven", active_version="1", activated_by="idn_ada"
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
        conformance_passed_at=None,
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
