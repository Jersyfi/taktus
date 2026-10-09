"""The whole slice with `TAKTUS_EXECUTION=container`: every worker step runs in an isolated
container the control plane starts, a stop mid-step lands on the worker's boundary, and the
resume runs in a new container that finds the checkpoint in the unit's state volume. Needs
Docker; skips without it (fails in CI, where Docker is required)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.components.run.application.service import ResumeRun
from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.composition.local import LocalWiring

from .test_first_slice import TENANT, bundle, entries_of, start, through, verified, verifies


def wiring(engine_socket: str, image: str) -> LocalWiring:
    return LocalWiring(
        EnvironmentConfiguration(
            {
                "TAKTUS_EXECUTION": "container",
                "TAKTUS_EXECUTION_UNIT": image,
                "TAKTUS_EXECUTION_ENGINE_SOCKET": engine_socket,
                "TAKTUS_EXECUTION_MEMORY_MB": "128",
                "TAKTUS_EXECUTION_WALL_SECONDS": "120",
                # The reference worker plans 0.3 s a step whatever the command, and a command
                # in a container takes longer: an underestimating worker. Four fifths of the
                # budget held back lets the worker use five times its reservation before it
                # must halt (W-14), so that this test proves the stop and the resume and nothing
                # about the budget; the budget below is raised to leave the line above the step.
                "TAKTUS_BUDGET_MARGIN": "0.8",
            }
        )
    )


async def test_a_run_with_a_worker_step_executes_in_a_container_stops_and_resumes(
    engine_socket: str, reference_worker_image: str, tmp_path: Path
) -> None:
    document = bundle(with_overreach=False)
    # The level at which nothing but an isolated unit is allowed.
    document["autonomy"] = {"level": 4, "reason": "the test needs the level"}
    document["limits"] = {"compute": {"seconds": 20, "resource_class": "cpu.small"}}
    compute = next(s for s in document["steps"] if s["id"] == "compute")
    compute["work"]["task"]["inputs"] = {
        "commands": ["expr 6 '*' 7", "sleep 0.5; echo two", "sleep 0.5; echo three", "echo four"]
    }
    local = wiring(engine_socket, reference_worker_image)
    await verified(
        tmp_path / "state", "worker.container"
    )  # level 4 runs only on a verified adapter
    async with local.services(state_dir=tmp_path / "state", worker_endpoint="") as services:
        running = asyncio.create_task(start(services, document))
        async with asyncio.timeout(120):
            while True:
                if running.done():
                    ended = running.result()
                    raise AssertionError(f"the run ended before its step ran: {ended.reason}")
                async with services.work.transaction(TENANT):
                    runs = await services.runs.list(TENANT)
                if runs and runs[0].step_run("compute").state is StepState.RUNNING:
                    break
                await asyncio.sleep(0.05)
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
        assert [s.state for s in run.step_runs] == [StepState.SUCCEEDED] * 4
        assert [a.id for a in run.step_run("compute").artifacts] == [
            "output-1",
            "output-2",
            "output-3",
            "output-4",
        ]
        entries = await entries_of(services, run.id)
        started = [e for e in entries if e.kind == "step.started" and e.refs.step_id == "compute"]
        assert len(started) == 2 and all(e.adapter == "worker.container" for e in started)
        assert await verifies(services)
    logs = sorted(p.name for p in (tmp_path / "state" / "units" / "unit").glob("job-asg_*.log"))
    assert len(logs) == 2, "two containers served the step: one before the stop, one after"
