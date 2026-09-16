"""The whole slice against the reference worker: a command becomes a plan, the plan runs, the
run delegates to the worker, every step lands in the ledger, and the ledger verifies.

Four cases from the definition of done: a run completes; a run stops at a boundary and resumes;
a run is rejected by admission control; and the shipped example does all of it through
`taktusctl run`, including a resume from a later invocation.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.adapters.driving.cli.wiring import Services
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import RegisterProcessVersion
from taktus.components.run.application.service import ResumeRun, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.composition.local import LocalWiring
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "processes" / "six-times-seven.yaml"


def bundle(*, budget_seconds: float = 2, with_overreach: bool = True) -> dict[str, Any]:
    with EXAMPLE.open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    document["limits"] = {"compute": {"seconds": budget_seconds, "resource_class": "cpu.small"}}
    if not with_overreach:
        document["steps"] = [s for s in document["steps"] if s["id"] != "overreach"]
    return document


async def start(
    services: Services, document: dict[str, Any], *, stop_after: int | None = None
) -> Run:
    version = await services.register_version.execute(RegisterProcessVersion(document))
    command = Command(
        id=services.ids.new("cmd"),
        channel="channel.cli",
        identity="idn_test",
        org_path=("test",),
        intent=Intent(raw="run"),
        reply_to=ReplyTo(channel="channel.cli", address="test"),
        received_at=services.clock.now(),
    )
    plan = await services.commission.execute(
        CommissionPlan(
            command=command,
            goal="g",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    return await services.engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(dict(version.limits or {})),
            process_version=version.ref,
            actor="idn_test",
            stop_after=stop_after,
        )
    )


async def test_a_run_completes_and_the_ledger_verifies(
    worker_endpoint: str, tmp_path: Path
) -> None:
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await start(services, bundle(with_overreach=False))
        assert run.state is RunState.FINISHED
        assert [s.state for s in run.step_runs] == [StepState.SUCCEEDED] * 4
        compute = run.step_run("compute")
        assert [a.id for a in compute.artifacts] == ["output-1"]
        assert compute.consumption is not None and compute.consumption.compute_seconds > 0
        assert compute.consumption.resource_class == "cpu.small"
        verify = run.step_run("verify-answer")
        assert verify.checkpoint is not None and verify.checkpoint.result_digest is not None
        entries = await services.ledger.entries(run.id)
        assert [e.kind for e in entries][:2] == ["run.created", "run.started"]
        assert [e.kind for e in entries][-1] == "run.finished"
        assert sum(1 for e in entries if e.kind == "step.finished") == 4
        started = next(
            e for e in entries if e.kind == "step.started" and e.refs.step_id == "compute"
        )
        assert started.adapter == "worker.http" and started.refs.assignment_id is not None
        assert (await services.ledger.verify()).intact


async def test_a_run_stops_at_a_boundary_and_resumes(worker_endpoint: str, tmp_path: Path) -> None:
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await start(services, bundle(with_overreach=False), stop_after=2)
        assert run.state is RunState.HALTED and run.cause is Cause.STOP
        assert [s.state for s in run.step_runs] == [
            StepState.SUCCEEDED,
            StepState.SUCCEEDED,
            StepState.PLANNED,
            StepState.PLANNED,
        ]
        assert (await services.ledger.verify()).intact
    # A later invocation: the state comes back from the snapshot.
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await services.engine.resume(ResumeRun(run_id=run.id, actor="idn_test"))
        assert run.state is RunState.FINISHED
        assert [s.state for s in run.step_runs] == [StepState.SUCCEEDED] * 4
        kinds = [e.kind for e in await services.ledger.entries(run.id)]
        assert kinds.count("step.started") == 4, "no step ran twice"
        assert "run.resumed" in kinds
        assert (await services.ledger.verify()).intact


async def test_a_worker_step_stopped_mid_way_resumes_from_its_checkpoint_without_duplicates(
    worker_endpoint: str, tmp_path: Path
) -> None:
    document = bundle(with_overreach=False)
    compute = next(s for s in document["steps"] if s["id"] == "compute")
    compute["work"]["task"]["inputs"] = {
        "commands": ["expr 6 '*' 7", "echo two", "echo three", "echo four"]
    }
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        running = asyncio.create_task(start(services, document))
        # Wait until the worker step has an assignment in flight, then ask for a stop.
        while True:
            runs = await services.runs.list()
            if runs and runs[0].step_run("compute").state is StepState.RUNNING:
                break
            await asyncio.sleep(0.02)
        await services.engine.request_stop(runs[0].id)
        run = await running
        assert run.state is RunState.HALTED and run.cause is Cause.STOP
        stopped = run.step_run("compute")
        assert stopped.state is StepState.STOPPED
        assert stopped.checkpoint is not None and stopped.checkpoint.ref.startswith("ckpt/asg_")
        assert 0 < len(stopped.artifacts) < 4, "the running command finished; nothing after it ran"
        run = await services.engine.resume(ResumeRun(run_id=run.id, actor="idn_test"))
        assert run.state is RunState.FINISHED
        resumed = run.step_run("compute")
        ids = [a.id for a in resumed.artifacts]
        assert ids == ["output-1", "output-2", "output-3", "output-4"]
        assert len(set(ids)) == 4
        assert (await services.ledger.verify()).intact


async def test_a_step_is_rejected_by_admission_control_before_it_starts(
    worker_endpoint: str, tmp_path: Path
) -> None:
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await start(services, bundle())
        assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
        overreach = run.step_run("overreach")
        assert overreach.state is StepState.REJECTED
        assert overreach.assignment_id is None, "nothing was posted to the worker"
        assert overreach.estimate is not None and overreach.estimate.compute_seconds is not None
        assert overreach.estimate.compute_seconds > 2
        kinds = [(e.kind, e.refs.step_id, e.outcome) for e in await services.ledger.entries(run.id)]
        assert ("step.rejected", "overreach", "rejected_by_admission") in kinds
        assert ("step.started", "overreach", None) not in kinds
        assert kinds[-1] == ("run.halted", None, "limit")
        assert (await services.ledger.verify()).intact
        # With a larger budget the same run continues and finishes.
        run = await services.engine.resume(
            ResumeRun(
                run_id=run.id,
                actor="idn_test",
                budget=Limits.model_validate(
                    {"compute": {"seconds": 120, "resource_class": "cpu.small"}}
                ),
            )
        )
        assert run.state is RunState.FINISHED
        assert run.step_run("overreach").state is StepState.SUCCEEDED
        assert (await services.ledger.verify()).intact


def taktusctl() -> str:
    path = shutil.which("taktusctl")
    assert path is not None, "taktusctl is not on the path; run under `uv run`"
    return path


def test_taktusctl_run_executes_the_example_and_resumes_in_a_later_invocation(
    worker_endpoint: str, tmp_path: Path
) -> None:
    env = {
        **os.environ,
        "TAKTUS_WORKER": worker_endpoint,
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
    }
    first = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "run", "--process", str(EXAMPLE), "--stop-after", "2"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert first.returncode == 3, first.stdout + first.stderr
    assert "state halted (stop)" in first.stdout
    assert "verifies" in first.stdout and "DOES NOT VERIFY" not in first.stdout
    run_id = next(line.split()[-1] for line in first.stdout.splitlines() if "--resume" in line)
    second = subprocess.run(  # noqa: S603
        [taktusctl(), "run", "--process", str(EXAMPLE), "--resume", run_id],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert second.returncode == 3, second.stdout + second.stderr
    assert "state halted (limit)" in second.stdout
    assert "rejected_by_admission" in second.stdout
    assert "verify-answer        rule       exact     succeeded" in second.stdout
    assert "settle               wait       -         succeeded" in second.stdout
    ledger = json.loads((tmp_path / "state" / "ledger.json").read_text())
    assert [e["kind"] for e in ledger][-1] == "run.halted"
    assert all("reason" not in e for e in ledger), "the ledger stores no text"


def test_taktusctl_run_refuses_an_invalid_bundle(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    document = bundle()
    document["steps"][0]["method"] = "llm"  # exact on llm
    bad.write_text(yaml.safe_dump(document), encoding="utf-8")
    completed = subprocess.run(  # noqa: S603
        [taktusctl(), "run", "--process", str(bad), "--state-dir", str(tmp_path / "state")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "is not a valid process" in completed.stderr
    assert "exact" in completed.stderr


@pytest.mark.parametrize("missing", ["--process"])
def test_taktusctl_run_needs_a_process(missing: str) -> None:
    completed = subprocess.run([taktusctl(), "run"], capture_output=True, text=True, check=False)  # noqa: S603
    assert completed.returncode == 2
    assert missing in completed.stderr
