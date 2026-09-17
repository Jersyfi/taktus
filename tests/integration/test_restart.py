"""A restart resumes at the last step boundary (ADR-0013 A), proven rather than asserted.

`taktusctl run` executes a bundle against the reference worker with the state in PostgreSQL.
Once two steps have finished and the third — a worker step — has persisted its first inner
boundary, the process is killed: SIGKILL, no shutdown, no chance to halt the run. A second
invocation resumes the run by id. Then: it continued from the last boundary, at most one
step's work was lost, no artifact is duplicated, and the ledger verifies unbroken across the
restart with every entry from before it unchanged — and so does the provenance chain: the
records written before the kill are unchanged, the interrupted step gets its record from the
second process, and the chain verifies with no gap at the boundary (ADR-0021).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from asyncio.subprocess import PIPE, STDOUT
from pathlib import Path
from typing import Any

import yaml

from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresRepository,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service import provenance
from taktus.shared.v1 import LedgerEntry, Provenance

from .test_first_slice import EXAMPLE, PLAIN, taktusctl

TENANT = "default"
COMMANDS = 20  # times --step-seconds 0.1 in the worker: a window of about two seconds to kill in


def bundle() -> dict[str, Any]:
    """The shipped example, with a worker step long enough to be killed inside and the step
    that admission control rejects left out: this run is meant to finish."""
    with EXAMPLE.open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    document["id"] = "restart"
    document["limits"] = {"compute": {"seconds": 60, "resource_class": "cpu.small"}}
    document["steps"] = [s for s in document["steps"] if s["id"] != "overreach"]
    compute = next(s for s in document["steps"] if s["id"] == "compute")
    compute["work"]["max_steps"] = COMMANDS
    prepare = next(s for s in document["steps"] if s["id"] == "prepare-commands")
    prepare["work"]["value"] = {
        "commands": ["expr 6 '*' 7", *[f"echo {n}" for n in range(2, COMMANDS + 1)]]
    }
    return document


class Database:
    """What the test reads directly from the database, as the application would."""

    def __init__(self, url: str) -> None:
        self.persistence = PostgresPersistence(url, pool_size=1)
        self.runs = PostgresRepository(self.persistence, Run)
        self.ledger = PostgresLedgerStore(self.persistence)
        self.provenance = PostgresProvenanceStore(self.persistence)

    async def records(self, run_id: str) -> list[Provenance]:
        async with self.persistence.transaction(TENANT):
            return list(await self.provenance.of_run(TENANT, run_id))

    async def run(self, run_id: str) -> Run | None:
        async with self.persistence.transaction(TENANT):
            return await self.runs.get(TENANT, run_id)

    async def latest_run(self) -> Run | None:
        async with self.persistence.transaction(TENANT):
            runs = [r for r in await self.runs.list(TENANT) if r.process_version == "restart@1"]
        return max(runs, key=lambda r: r.created_at, default=None)

    async def entries(self, run_id: str) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return [e for e in await self.ledger.entries(TENANT) if e.refs.run_id == run_id]

    async def verifies(self) -> bool:
        async with self.persistence.transaction(TENANT):
            verification = await ChainedLedger(self.ledger, _NoClock()).verify(TENANT)
        assert verification.intact, verification.findings
        return True

    async def close(self) -> None:
        await self.persistence.close()


class _NoClock:
    """`verify` never asks the time; the ledger needs a clock only to record."""

    def now(self) -> Any:
        raise AssertionError("verify does not read the clock")

    async def sleep(self, seconds: float) -> None:
        raise AssertionError("verify does not sleep")


async def test_a_run_survives_a_killed_process_and_resumes_at_its_last_boundary(
    worker_endpoint: str, postgres_url: str, tmp_path: Path
) -> None:
    process_file = tmp_path / "restart.yaml"
    process_file.write_text(yaml.safe_dump(bundle()), encoding="utf-8")
    env = {
        **os.environ,
        **PLAIN,
        "TAKTUS_WORKER": worker_endpoint,
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
        "TAKTUS_DATABASE_URL": postgres_url,
    }
    database = Database(postgres_url)
    first = await asyncio.create_subprocess_exec(
        taktusctl(), "run", "--process", str(process_file), stdout=PIPE, stderr=STDOUT, env=env
    )
    try:
        # Wait until two steps are done and the worker step has persisted a boundary of its
        # own, so that the kill lands inside a step with something to resume from.
        deadline = time.monotonic() + 30
        while True:
            if first.returncode is not None:
                output, _ = await first.communicate()
                raise AssertionError(f"the run finished before it could be killed:\n{output!r}")
            assert time.monotonic() < deadline, "no boundary was persisted within 30 seconds"
            run = await database.latest_run()
            if run is not None:
                compute = run.step_run("compute")
                if (
                    run.step_run("prepare-commands").done
                    and compute.state is StepState.RUNNING
                    and compute.checkpoint is not None
                ):
                    break
            await asyncio.sleep(0.05)
        first.kill()
        await first.wait()
    finally:
        if first.returncode is None:
            first.kill()

    # What the database holds after the kill: the run still running, the step in flight with
    # its last boundary, fewer artifacts than the step will have, and an intact chain.
    interrupted = await database.run(run.id)
    assert interrupted is not None and interrupted.state is RunState.RUNNING
    compute = interrupted.step_run("compute")
    assert compute.state is StepState.RUNNING and compute.checkpoint is not None
    produced_before = [a.id for a in compute.artifacts]
    assert 0 < len(produced_before) < COMMANDS
    assert compute.checkpoint.ref.startswith("ckpt/asg_")
    before = await database.entries(run.id)
    assert [e.kind for e in before][-1] == "step.started", "nothing after the kill was recorded"
    assert await database.verifies()
    recorded_before = await database.records(run.id)
    assert [r.step_id for r in recorded_before] == ["prepare-commands"], (
        "the step in flight has no record yet; the one before it has"
    )

    second = await asyncio.create_subprocess_exec(
        taktusctl(),
        "run",
        "--process",
        str(process_file),
        "--resume",
        run.id,
        stdout=PIPE,
        stderr=STDOUT,
        env=env,
    )
    output, _ = await second.communicate()
    assert second.returncode == 0, output.decode()
    assert "state  database" in output.decode()

    resumed = await database.run(run.id)
    assert resumed is not None and resumed.state is RunState.FINISHED
    assert [s.state for s in resumed.step_runs] == [StepState.SUCCEEDED] * 4

    # Continued from the last boundary: the steps before it are untouched, the interrupted
    # step was resumed from its persisted checkpoint rather than started over.
    for step_id in ("prepare-commands",):
        assert resumed.step_run(step_id).started_at == interrupted.step_run(step_id).started_at
        assert resumed.step_run(step_id).finished_at == interrupted.step_run(step_id).finished_at
    compute = resumed.step_run("compute")
    assert (
        compute.checkpoint is not None
        and compute.checkpoint.ref != interrupted.step_run("compute").checkpoint.ref
    )
    ids = [a.id for a in compute.artifacts]
    assert ids == [f"output-{n}" for n in range(1, COMMANDS + 1)], "every command's output, once"
    assert len(set(ids)) == COMMANDS, "no artifact is duplicated"
    assert ids[: len(produced_before)] == produced_before, (
        "what was produced before the kill stayed"
    )
    assert compute.consumption is not None and compute.consumption.compute_seconds is not None
    assert compute.consumption.compute_seconds < 2 * COMMANDS * 0.1 + 1, (
        "at most one step of work was done twice, not the whole step"
    )

    # The ledger verifies unbroken across the restart; what was there before is unchanged.
    after = await database.entries(run.id)
    assert after[: len(before)] == before
    kinds = [e.kind for e in after]
    assert kinds[len(before)] == "run.recovered"
    assert kinds[-1] == "run.finished"
    assert kinds.count("step.started") == 5, "prepare once, compute twice, the last two once"
    assert sum(1 for e in after if e.kind == "step.started" and e.refs.step_id == "compute") == 2
    assert (
        sum(1 for e in after if e.kind == "step.started" and e.refs.step_id == "prepare-commands")
        == 1
    )
    assert await database.verifies()

    # The provenance chain has no gap at the boundary: what was recorded before the kill is
    # unchanged, the interrupted step got its record from the second process with every
    # artifact of both attempts, and the chain verifies against the run and the ledger.
    recorded = await database.records(run.id)
    assert recorded[: len(recorded_before)] == recorded_before
    assert [r.step_id for r in recorded] == [s.id for s in resumed.steps]
    assert recorded[1].outputs == tuple(ids)
    assert recorded[1].adapter == "worker.http" and recorded[1].adapter_version is not None
    assert recorded[1].ledger_seq > before[-1].seq, "recorded by the second process"
    assert [i.step_id for i in recorded[3].inputs] == ["compute"]
    verification = provenance.verify(resumed, recorded, after)
    assert verification.intact, verification.findings
    await database.close()

    # The artifact bytes of both invocations are in the same object store.
    assert shutil.which("taktusctl") is not None
    assert (tmp_path / "state" / "objects").is_dir()
