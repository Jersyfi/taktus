"""The whole slice against the reference worker: a command becomes a plan, the plan runs, the
run delegates to the worker, every step lands in the ledger, and the ledger verifies.

Four cases from the definition of done: a run completes; a run stops at a boundary and resumes;
a run is rejected by admission control; and the shipped example does all of it through
`taktusctl run`, including a resume from a later invocation.

The example runs at autonomy level 2, so no step starts before a person confirmed it (ADR-0039):
the cases confirm each step as it waits, the way its operator does.
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
from fakes.identity import added_by_command_line

from taktus.adapters.driving.cli.wiring import Services
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import RegisterProcessVersion
from taktus.components.run.application.service import ConfirmSteps, ResumeRun, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.composition.local import LocalWiring
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "processes" / "six-times-seven.yaml"
TENANT = "test"


def bundle(*, budget_seconds: float = 2, with_overreach: bool = True) -> dict[str, Any]:
    with EXAMPLE.open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    document["limits"] = {"compute": {"seconds": budget_seconds, "resource_class": "cpu.small"}}
    if not with_overreach:
        document["steps"] = [s for s in document["steps"] if s["id"] != "overreach"]
    return document


def verified(state_dir: Path, *adapters: str) -> None:
    """Record both halves of *verified* for the adapters in a state directory's snapshot, as a
    conformance run and a removal test that said `changed` would. A step at level 3 or above
    runs only on such an adapter (ADR-0039)."""
    at = "2026-10-09T12:00:00Z"
    records = [
        {
            "id": adapter,
            "tenant": tenant,
            "family": adapter.split(".", 1)[0],
            "conformance_passed_at": at,
            "removal": {
                "integration": adapter,
                "family": adapter.split(".", 1)[0],
                "verdict": "changed",
                "tested_at": at,
                "run_id": "run_removal",
            },
            "updated_at": at,
        }
        for adapter in adapters
        for tenant in ("default", TENANT)
    ]
    by_tenant: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_tenant.setdefault(str(record["tenant"]), []).append(record)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "adaptermaturity.json").write_text(json.dumps(by_tenant), encoding="utf-8")


async def confirm(services: Services, run: Run, *steps: str, stop_after: int | None = None) -> Run:
    """A person confirms the steps, and the run continues."""
    return await services.engine.confirm(
        ConfirmSteps(
            run_id=run.id, steps=steps, actor="idn_test", tenant=TENANT, stop_after=stop_after
        )
    )


async def through(services: Services, run: Run) -> Run:
    """Confirm whatever waits for a person, as the operator would, until nothing waits."""
    while run.state is RunState.WAITING_HUMAN:
        run = await confirm(services, run, *(s.step_id for s in run.waiting()))
    return run


async def start(services: Services, document: dict[str, Any], *, confirmed: bool = True) -> Run:
    version = await services.register_version.execute(
        RegisterProcessVersion(document, tenant=TENANT)
    )
    command = Command(
        id=services.ids.new("cmd"),
        channel="channel.cli",
        identity="idn_test",
        org_path=(TENANT,),
        intent=Intent(raw="run"),
        reply_to=ReplyTo(channel="channel.cli", address="test"),
        received_at=services.clock.now(),
    )
    plan = await services.commission.execute(
        CommissionPlan(
            command=command,
            tenant=TENANT,
            goal="g",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    run = await services.engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(dict(version.limits or {})),
            process_version=version.ref,
            actor="idn_test",
            tenant=TENANT,
            actions=version.autonomy.action_levels,
        )
    )
    return await through(services, run) if confirmed else run


async def entries_of(services: Services, run_id: str) -> list[Any]:
    async with services.work.transaction(TENANT):
        return list(await services.ledger.entries(TENANT, run_id))


async def verifies(services: Services) -> bool:
    async with services.work.transaction(TENANT):
        return (await services.ledger.verify(TENANT)).intact


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
        entries = await entries_of(services, run.id)
        assert [e.kind for e in entries][:3] == ["run.created", "budget.set", "run.started"]
        assert [e.kind for e in entries][-1] == "run.finished"
        assert sum(1 for e in entries if e.kind == "step.finished") == 4
        started = next(
            e for e in entries if e.kind == "step.started" and e.refs.step_id == "compute"
        )
        assert started.adapter == "worker.endpoint" and started.refs.assignment_id is not None
        assert await verifies(services)


async def test_a_run_stops_at_a_boundary_and_resumes(worker_endpoint: str, tmp_path: Path) -> None:
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await start(services, bundle(with_overreach=False), confirmed=False)
        run = await confirm(services, run, "prepare-commands")
        run = await confirm(services, run, "compute", stop_after=1)
        assert run.state is RunState.HALTED and run.cause is Cause.STOP
        assert [s.state for s in run.step_runs] == [
            StepState.SUCCEEDED,
            StepState.SUCCEEDED,
            StepState.PLANNED,
            StepState.PLANNED,
        ]
        assert await verifies(services)
    # A later invocation: the state comes back from the snapshot.
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await services.engine.resume(
            ResumeRun(run_id=run.id, actor="idn_test", tenant=TENANT)
        )
        run = await through(services, run)
        assert run.state is RunState.FINISHED
        assert [s.state for s in run.step_runs] == [StepState.SUCCEEDED] * 4
        kinds = [e.kind for e in await entries_of(services, run.id)]
        assert kinds.count("step.started") == 4, "no step ran twice"
        assert "run.resumed" in kinds
        assert await verifies(services)


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
        run = await start(services, document, confirmed=False)
        run = await confirm(services, run, "prepare-commands")
        running = asyncio.create_task(confirm(services, run, "compute"))
        # Wait until the worker step has an assignment in flight, then ask for a stop.
        while True:
            async with services.work.transaction(TENANT):
                runs = await services.runs.list(TENANT)
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
        run = await services.engine.resume(
            ResumeRun(run_id=run.id, actor="idn_test", tenant=TENANT)
        )
        run = await through(services, run)
        assert run.state is RunState.FINISHED, (run.cause, run.reason)
        resumed = run.step_run("compute")
        ids = [a.id for a in resumed.artifacts]
        assert ids == ["output-1", "output-2", "output-3", "output-4"]
        assert len(set(ids)) == 4
        assert await verifies(services)


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
        kinds = [(e.kind, e.refs.step_id, e.outcome) for e in await entries_of(services, run.id)]
        assert ("step.rejected", "overreach", "rejected_by_admission") in kinds
        assert ("step.started", "overreach", None) not in kinds
        assert kinds[-1] == ("run.halted", None, "limit")
        assert await verifies(services)
        # With a larger budget the same run continues and finishes.
        run = await services.engine.resume(
            ResumeRun(
                run_id=run.id,
                actor="idn_test",
                tenant=TENANT,
                budget=Limits.model_validate(
                    {"compute": {"seconds": 120, "resource_class": "cpu.small"}}
                ),
            )
        )
        run = await through(services, run)
        assert run.state is RunState.FINISHED, (run.cause, run.reason)
        assert run.step_run("overreach").state is StepState.SUCCEEDED
        assert await verifies(services)


def taktusctl() -> str:
    path = shutil.which("taktusctl")
    assert path is not None, "taktusctl is not on the path; run under `uv run`"
    return path


# The command line colours its usage errors where the terminal allows it; CI's does, and the
# escape codes would split the words the assertions look for.
PLAIN = {"NO_COLOR": "1", "TERM": "dumb"}


def test_taktusctl_run_executes_the_example_and_resumes_in_a_later_invocation(
    worker_endpoint: str, tmp_path: Path
) -> None:
    env = {
        **os.environ,
        "TAKTUS_WORKER": worker_endpoint,
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
    }
    added_by_command_line(taktusctl(), "idn_test", env)
    first = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "run", "--process", str(EXAMPLE)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert first.returncode == 3, first.stdout + first.stderr
    assert "state  memory with a snapshot under" in first.stdout, "the storage is never silent"
    assert "state waiting_human (person)" in first.stdout, "level 2: the first step waits"
    assert "verifies" in first.stdout and "DOES NOT VERIFY" not in first.stdout
    hint = next(line for line in first.stdout.splitlines() if "waits for a person:" in line)
    assert hint.endswith("--approve prepare-commands"), hint
    run_id = hint.split("--resume ", 1)[1].split()[0]
    # Each later invocation confirms the step that waits, and the run goes on to the next.
    second = first
    for _ in range(6):
        waiting = [line for line in second.stdout.splitlines() if "waits for a person:" in line]
        if not waiting:
            break
        step = waiting[0].split()[-1]
        second = subprocess.run(  # noqa: S603
            [taktusctl(), "run", "--process", str(EXAMPLE), "--resume", run_id, "--approve", step],
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
    ledger = json.loads((tmp_path / "state" / "ledger.json").read_text())["default"]
    assert [e["kind"] for e in ledger][-1] == "run.halted"
    assert all("reason" not in e for e in ledger), "the ledger stores no text"


def test_taktusctl_run_refuses_an_invalid_bundle(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    document = bundle()
    document["steps"][0]["method"] = "llm"  # exact on llm
    bad.write_text(yaml.safe_dump(document), encoding="utf-8")
    added_by_command_line(taktusctl(), "idn_test", None, "--state-dir", str(tmp_path / "state"))
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
    completed = subprocess.run(  # noqa: S603
        [taktusctl(), "run"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **PLAIN},
    )
    assert completed.returncode == 2
    assert missing in completed.stderr


def test_nothing_executes_without_an_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `--identity`, or one the identity component does not know: the command refuses
    before it registers anything, and names the way out (control-plane.md §2, ADR-0040)."""
    monkeypatch.delenv("TAKTUS_IDENTITY")
    state = str(tmp_path / "state")
    completed = subprocess.run(  # noqa: S603
        [taktusctl(), "run", "--process", str(EXAMPLE), "--state-dir", state],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **PLAIN},
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "nothing executes without an identity" in completed.stderr
    assert "--identity" in completed.stderr
    assert not (tmp_path / "state" / "ledger.json").exists()

    unknown = subprocess.run(  # noqa: S603
        [taktusctl(), "run", "--process", str(EXAMPLE), "--state-dir", state, "--identity", "x"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **PLAIN},
    )
    assert unknown.returncode == 2, unknown.stdout + unknown.stderr
    assert "has no identity 'x'" in unknown.stderr
    assert "taktusctl identity add x" in unknown.stderr
    assert not (tmp_path / "state" / "ledger.json").exists(), "nothing registered either"


async def test_what_a_run_cost_is_read_back_from_the_ledger(
    worker_endpoint: str, tmp_path: Path
) -> None:
    from taktus.adapters.driving.cli.cost_command import render
    from taktus.components.accounting.application.service import CostOfRun

    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await start(services, bundle())
        assert services.cost is not None
        cost = await services.cost.execute(CostOfRun(run.id, TENANT))
    assert cost.meter.steps["worker"] == 1 and cost.meter.compute_seconds["cpu.small"] > 0
    assert cost.priced is None and cost.unpriced == (), (
        "no tokens: nothing to price, nothing hidden"
    )
    shown = render(cost)
    assert shown.startswith(f"run      {run.id}") and "compute  " in shown
