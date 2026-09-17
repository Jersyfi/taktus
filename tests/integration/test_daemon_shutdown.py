"""A real SIGTERM mid-run lands on a step boundary (ADR-0005, ADR-0013 A), and the whole
surface works under a non-root path prefix.

`taktusd` runs as a process of its own — runner role, against PostgreSQL and the reference
worker — and executes a submitted run whose worker step takes a couple of seconds. Once that
step has persisted an inner boundary, the process receives SIGTERM. Then: it exits 0 within the
ceiling; the run is halted at a boundary with its checkpoint and nothing after it started; the
job is claimable again; the ledger verifies. A second daemon claims the job, resumes the run
from that boundary — the worker produces nothing it produced before — and finishes it, and its
SIGTERM lands cleanly on an idle process. Health answered throughout; readiness said yes. The
second daemon is served under `/taktus/two`: nothing answers at the root, everything under the
prefix.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from asyncio.subprocess import PIPE, STDOUT, Process
from pathlib import Path
from typing import Any

import httpx

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.postgres import PostgresQueue
from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.composition.daemon import wire

from .conftest import free_port
from .test_daemon_scaling import settings, submit
from .test_restart import COMMANDS, Database
from .test_restart import bundle as restart_bundle

TENANT = "default"


def bundle(n: int) -> dict[str, Any]:
    document = restart_bundle()
    document["id"] = f"shutdown-{os.getpid()}-{n}"
    return document


async def daemon(environment: dict[str, str], log: Path) -> Process:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "taktus.composition.daemon",
        stdout=PIPE,
        stderr=STDOUT,
        env={**os.environ, **environment},
    )

    async def pump() -> None:
        assert process.stdout is not None
        with log.open("ab") as handle:
            async for line in process.stdout:
                handle.write(line)

    asyncio.get_running_loop().create_task(pump())
    return process


async def wait_ready(port: int, process: Process, prefix: str = "") -> None:
    async with asyncio.timeout(30), httpx.AsyncClient() as client:
        while True:
            assert process.returncode is None, "the daemon exited early"
            try:
                url = f"http://127.0.0.1:{port}{prefix}/ready"
                if (await client.get(url)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)


async def test_sigterm_mid_run_lands_on_a_boundary_and_the_next_daemon_resumes(
    worker_endpoint: str, postgres_url: str, tmp_path: Path
) -> None:
    configured = settings(postgres_url, tmp_path, TAKTUS_WORKER=worker_endpoint)
    async with wire(configured, EnvironmentConfiguration({})) as wired:
        run = await submit(wired, bundle(1))
    database = Database(postgres_url)
    environment = {
        "TAKTUS_DATABASE_URL": postgres_url,
        "TAKTUS_ROLES": "runner",
        "TAKTUS_WORKER": worker_endpoint,
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
        "TAKTUS_POLL_SECONDS": "0.05",
        "TAKTUS_LEASE_SECONDS": "5",
        "TAKTUS_SHUTDOWN_CEILING_SECONDS": "20",
        "TAKTUS_LOG_LEVEL": "debug",
    }
    port = free_port()
    log = tmp_path / "taktusd-1.log"
    first = await daemon(
        {**environment, "TAKTUS_HTTP_PORT": str(port), "TAKTUS_INSTANCE": "first"}, log
    )
    try:
        await wait_ready(port, first)
        async with httpx.AsyncClient() as client:
            health = await client.get(f"http://127.0.0.1:{port}/health")
            assert health.status_code == 200 and health.json() == {"status": "alive"}
            ready = (await client.get(f"http://127.0.0.1:{port}/ready")).json()
            assert ready == {"status": "ready", "roles": ["runner"], "leading": False}
        # Until the worker step has persisted an inner boundary, so that the signal lands
        # inside a step with something to resume from.
        async with asyncio.timeout(30):
            while True:
                assert first.returncode is None, f"the daemon exited early; see {log}"
                stored = await database.run(run.id)
                assert stored is not None
                compute = stored.step_run("compute")
                if compute.state is StepState.RUNNING and compute.checkpoint is not None:
                    break
                await asyncio.sleep(0.05)
        first.send_signal(signal.SIGTERM)
        assert await asyncio.wait_for(first.wait(), timeout=25) == 0, log.read_text()
    finally:
        if first.returncode is None:
            first.kill()

    halted = await database.run(run.id)
    assert halted is not None and halted.state is RunState.HALTED and halted.cause is Cause.STOP
    compute = halted.step_run("compute")
    assert compute.state is StepState.STOPPED and compute.checkpoint is not None
    assert compute.checkpoint.ref.startswith("ckpt/asg_"), "the worker's boundary"
    produced_before = [a.id for a in compute.artifacts]
    assert 0 < len(produced_before) < COMMANDS, "stopped inside the step, at a boundary"
    assert halted.step_run("verify-answer").state is StepState.PLANNED, "nothing after it ran"
    before = await database.entries(run.id)
    assert [e.kind for e in before][-1] == "run.halted"
    assert await database.verifies()
    async with database.persistence.transaction(TENANT):
        jobs = await PostgresQueue(database.persistence, lease_seconds=5).claim(TENANT, "probe", 10)
        assert [j.payload["run_id"] for j in jobs] == [run.id], "the job was released"
        await PostgresQueue(database.persistence).release(TENANT, jobs[0].id, "probe")
    text = log.read_text()
    assert "signal received" in text and "runner stopped" in text and "taktusd stopped" in text

    port = free_port()
    log = tmp_path / "taktusd-2.log"
    prefix = "/taktus/two"
    second = await daemon(
        {
            **environment,
            "TAKTUS_HTTP_PORT": str(port),
            "TAKTUS_INSTANCE": "second",
            "TAKTUS_PATH_PREFIX": prefix,
            "TAKTUS_ROLES": "runner,api",
        },
        log,
    )
    try:
        await wait_ready(port, second, prefix)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            assert (await client.get("/ready")).status_code == 404, "nothing at the root"
            assert (await client.get("/health")).status_code == 404
            assert (await client.get(f"/runs/{run.id}")).status_code == 404
            assert (await client.get(f"{prefix}/health")).json() == {"status": "alive"}
            seen = await client.get(f"{prefix}/runs/{run.id}")
            assert seen.status_code == 200 and seen.json()["id"] == run.id
            listed = await client.get(f"{prefix}/runs")
            assert run.id in [r["id"] for r in listed.json()["runs"]]
            problem = await client.get(f"{prefix}/runs/run_nope")
            assert problem.status_code == 404
            assert problem.headers["content-type"] == "application/problem+json"
        async with asyncio.timeout(60):
            while True:
                assert second.returncode is None, f"the daemon exited early; see {log}"
                stored = await database.run(run.id)
                if stored is not None and stored.state is RunState.FINISHED:
                    break
                await asyncio.sleep(0.1)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            ledger = (await client.get(f"{prefix}/runs/{run.id}/ledger")).json()
            assert ledger["chain"]["intact"] and ledger["entries"][-1]["kind"] == "run.finished"
        second.send_signal(signal.SIGTERM)
        assert await asyncio.wait_for(second.wait(), timeout=25) == 0, log.read_text()
    finally:
        if second.returncode is None:
            second.kill()

    resumed = await database.run(run.id)
    assert resumed is not None
    assert [s.state for s in resumed.step_runs] == [StepState.SUCCEEDED] * 4
    compute = resumed.step_run("compute")
    ids = [a.id for a in compute.artifacts]
    assert ids == [f"output-{n}" for n in range(1, COMMANDS + 1)], "every command's output, once"
    assert ids[: len(produced_before)] == produced_before, "what was produced before stayed"
    after = await database.entries(run.id)
    assert after[: len(before)] == before, "nothing before the signal changed"
    kinds = [e.kind for e in after]
    assert kinds[len(before)] == "run.resumed"
    assert kinds[-1] == "run.finished"
    assert sum(1 for e in after if e.kind == "step.started" and e.refs.step_id == "compute") == 2
    assert await database.verifies()
    await database.close()
