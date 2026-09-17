"""Aggregates with every field filled, for round trips. Built from the shipped example where
one exists, so that the shape the tests store is the shape the product stores."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from taktus.components.command.domain.model import IntakeEvent
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import Process, ProcessVersion, Slo, Trigger
from taktus.components.run.domain.model import Checkpoint, Run, RunState, StepState
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Artifact,
    Command,
    Commissioned,
    Consumption,
    ConsumptionQuantities,
    Intent,
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
    return Process(id="six-times-seven", name="Six times seven", active_version="1")


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
            "checkpoint": Checkpoint(
                ref="ckpt/asg_0001/0",
                step_id="compute",
                taken_at=AT + timedelta(seconds=4),
                artifact_ids=("output-1",),
            ),
        }
    )
    return fresh.with_step_run(first).with_step_run(second)
