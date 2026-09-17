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

from .test_first_slice import TENANT, bundle, entries_of, start, verifies


def wiring(engine_socket: str, image: str) -> LocalWiring:
    return LocalWiring(
        EnvironmentConfiguration(
            {
                "TAKTUS_EXECUTION": "container",
                "TAKTUS_EXECUTION_UNIT": image,
                "TAKTUS_EXECUTION_ENGINE_SOCKET": engine_socket,
                "TAKTUS_EXECUTION_MEMORY_MB": "128",
                "TAKTUS_EXECUTION_WALL_SECONDS": "120",
            }
        )
    )


async def test_a_run_with_a_worker_step_executes_in_a_container_stops_and_resumes(
    engine_socket: str, reference_worker_image: str, tmp_path: Path
) -> None:
    document = bundle(with_overreach=False)
    document["autonomy"] = 4  # the level at which nothing but an isolated unit is allowed
    compute = next(s for s in document["steps"] if s["id"] == "compute")
    compute["work"]["task"]["inputs"] = {
        "commands": ["expr 6 '*' 7", "sleep 0.5; echo two", "sleep 0.5; echo three", "echo four"]
    }
    local = wiring(engine_socket, reference_worker_image)
    async with local.services(state_dir=tmp_path / "state", worker_endpoint="") as services:
        running = asyncio.create_task(start(services, document))
        while True:
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
        assert run.state is RunState.FINISHED
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
