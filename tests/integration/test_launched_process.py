"""The whole slice with an execution unit the control plane starts itself: `TAKTUS_EXECUTION=
process`. Every worker step starts the reference worker as a fresh unit — a probe for the
estimate, a unit for the assignment — and a stop mid-step resumes in a new unit from the
checkpoint the previous one left in the unit's state."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.components.run.application.service import ResumeRun
from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.composition.execution import execution_of, worker_unit
from taktus.composition.local import LocalWiring
from taktus.composition.settings import load_workers
from taktus.ports.execution import JobRequest
from taktus.ports.worker import CredentialReference

from .test_first_slice import TENANT, bundle, entries_of, start, through, verified, verifies

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"
LINUX = sys.platform.startswith("linux")


def wiring(**more: str) -> LocalWiring:
    return LocalWiring(
        EnvironmentConfiguration(
            {
                "TAKTUS_EXECUTION": "process",
                "TAKTUS_EXECUTION_UNIT": f"{sys.executable} {WORKER} --step-seconds 0.1",
                "TAKTUS_EXECUTION_WALL_SECONDS": "60",
                # Only Linux enforces the unit's memory limit; elsewhere the adapter refuses
                # the job unless the operator accepts the limit unenforced, as here.
                "TAKTUS_EXECUTION_MEMORY_UNENFORCED": "false" if LINUX else "true",
                **more,
            }
        )
    )


async def test_a_run_completes_through_units_started_per_job(tmp_path: Path) -> None:
    async with wiring().services(state_dir=tmp_path / "state", worker_endpoint="") as services:
        run = await start(services, bundle(with_overreach=False))
        assert run.state is RunState.FINISHED
        assert [s.state for s in run.step_runs] == [StepState.SUCCEEDED] * 4
        compute = run.step_run("compute")
        assert [a.id for a in compute.artifacts] == ["output-1"]
        entries = await entries_of(services, run.id)
        started = next(
            e for e in entries if e.kind == "step.started" and e.refs.step_id == "compute"
        )
        assert started.adapter == "worker.process"
        assert await verifies(services)
    units = tmp_path / "state" / "units" / "unit"
    logs = sorted(p.name for p in units.glob("job-*.log"))
    assert len(logs) == 3, logs
    assert logs[0].startswith("job-asg_"), "one unit served the assignment"
    assert logs[1].startswith("job-probe-asg_"), "one probe answered its estimate"
    assert logs[2] == "job-probe-capabilities.log", "one probe answered the capabilities"
    assert list(units.glob("ckpt_*.json")), "the unit's checkpoints outlive the job"


async def test_a_worker_step_stopped_mid_way_resumes_in_a_new_unit(tmp_path: Path) -> None:
    document = bundle(with_overreach=False)
    compute = next(s for s in document["steps"] if s["id"] == "compute")
    compute["work"]["task"]["inputs"] = {
        "commands": ["expr 6 '*' 7", "echo two", "echo three", "echo four", "echo five"]
    }
    async with wiring().services(state_dir=tmp_path / "state", worker_endpoint="") as services:
        running = asyncio.create_task(start(services, document))
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
        assert 0 < len(stopped.artifacts) < 5
        run = await services.engine.resume(
            ResumeRun(run_id=run.id, actor="idn_test", tenant=TENANT)
        )
        run = await through(services, run)
        assert run.state is RunState.FINISHED
        ids = [a.id for a in run.step_run("compute").artifacts]
        assert ids == [f"output-{n}" for n in range(1, 6)]
        assert await verifies(services)
    units = tmp_path / "state" / "units" / "unit"
    assert len(list(units.glob("job-asg_*.log"))) == 2, "two units served the step"


async def test_the_process_adapter_is_refused_at_level_3_and_the_run_escalates(
    tmp_path: Path,
) -> None:
    document = bundle(with_overreach=False)
    document["autonomy"] = {"level": 3, "reason": "the test needs the level", "toward_next": "-"}
    # Verified, so that what refuses the step is the execution rule and not its maturity.
    await verified(tmp_path / "state", "worker.process")
    async with wiring().services(state_dir=tmp_path / "state", worker_endpoint="") as services:
        run = await start(services, document)
        assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
        compute = run.step_run("compute")
        assert compute.state is StepState.FAILED
        assert compute.reason is not None and "ADR-0002" in compute.reason
        assert compute.assignment_id is None, "no unit was started for the assignment"
    assert not list((tmp_path / "state" / "units").glob("*/job-asg_*.log"))


async def test_a_unit_that_exceeds_its_wall_clock_is_killed_and_the_step_fails_with_the_cause(
    tmp_path: Path,
) -> None:
    """A limit the execution adapter enforces ends the unit; the run sees a failed step that
    names the kill, not a stream that hangs. The memory limit of the container adapter is
    reported through the same path (tests/adapters/execution/test_container.py)."""
    document = bundle(with_overreach=False)
    compute = next(s for s in document["steps"] if s["id"] == "compute")
    compute["work"]["task"]["inputs"] = {"commands": [f"sleep 0.4; echo {n}" for n in range(30)]}
    compute["work"]["max_steps"] = 40
    document["limits"] = {"compute": {"seconds": 120, "resource_class": "cpu.small"}}
    local = wiring(TAKTUS_EXECUTION_WALL_SECONDS="3")
    async with local.services(state_dir=tmp_path / "state", worker_endpoint="") as services:
        run = await start(services, document)
        assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
        failed = run.step_run("compute")
        assert failed.state is StepState.FAILED
        assert failed.reason is not None and "wall-clock limit of 3s" in failed.reason
        assert failed.reason.startswith("the execution unit was killed")
        assert 0 < len(failed.artifacts) < 30, "what was done before the kill is kept"


async def test_each_configured_worker_launches_with_its_own_credential(tmp_path: Path) -> None:
    """Issue #209: two launched workers that reference the same credential name each receive
    the value configured for that worker; neither unit sees the other's value, nor the
    instance's. Each keeps its state and logs under its own name (ADR-0078)."""
    values = {"first": "first-3f9a1c", "second": "second-77b0e2", "instance": "instance-0d1e"}
    for name, value in values.items():
        (tmp_path / name).write_text(value + "\n", encoding="utf-8")
    dump = (
        "import os, json; print(json.dumps({k: v for k, v in os.environ.items() "
        "if k == 'AGENT_KEY'}), flush=True)"
    )
    serve = f"import runpy; runpy.run_path('{WORKER}', run_name='__main__')"
    configuration = EnvironmentConfiguration(
        {
            "TAKTUS_WORKERS": "first,second",
            "TAKTUS_EXECUTION": "process",
            "TAKTUS_EXECUTION_UNIT": f'{sys.executable} -c "{dump}; {serve}"',
            "TAKTUS_EXECUTION_MEMORY_UNENFORCED": "false" if LINUX else "true",
            "TAKTUS_WORKER_FIRST_CREDENTIAL_AGENT_KEY_FILE": str(tmp_path / "first"),
            "TAKTUS_WORKER_SECOND_CREDENTIAL_AGENT_KEY_FILE": str(tmp_path / "second"),
            "TAKTUS_CREDENTIAL_AGENT_KEY_FILE": str(tmp_path / "instance"),
        }
    )
    state = tmp_path / "state"
    for worker in load_workers(configuration):
        execution = execution_of(
            worker.execution, worker.configuration(configuration), state_dir=state
        )
        request = JobRequest(
            job_id=f"job-{worker.name}",
            unit=worker_unit(worker),
            autonomy_level=1,
            credentials=(CredentialReference(name="AGENT_KEY", injected_as="env"),),
        )
        async with execution.launch(request):
            pass
    for name in ("first", "second"):
        log = state / "units" / name / f"job-job-{name}.log"
        dumped = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert dumped == {"AGENT_KEY": values[name]}, name
