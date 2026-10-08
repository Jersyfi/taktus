"""Runners on several instances, and a runner that dies mid-step (ADR-0013 A, issue #73).

Two `taktusd` processes with the role `runner` share one PostgreSQL database, as two
containers would. Twenty runs are submitted, each with a worker step that takes about two
seconds. While they execute, the test reads the job table every few milliseconds and keeps,
for every job, who held its claim and since when.

Once some runs are done and runner A holds a run whose worker step has persisted an inner
boundary, A is killed: SIGKILL, no shutdown, no chance to halt or release anything. Then:

- every run finishes;
- the load was spread: both runners held claims, and neither ever held more jobs than its
  concurrency (NTC-0027);
- a claim moved from one runner to the other only for a job A held when it died, only to B,
  and only after A's last renewal of the lease had expired;
- every run A held when it died was taken over by B at its last boundary: recovered
  (`run.recovered`), started if A had not started it, or left as it was if it had ended before
  A could complete its job (NTC-0026); the run whose worker step was interrupted continued
  from the worker's checkpoint, and every output of that step exists once;
- no step that had finished was started again; a step A had started was started again, and a
  step A had only admitted was started once, by B (NTC-0046); in a run nobody interrupted every
  step started exactly once;
- the ledger chain verifies, and the provenance chain of every run verifies against its run
  and its ledger entries.

The test runs in a tenant of its own, which both runners serve and nothing else uses. The
scheduler's election with two instances is proven in `test_daemon_scaling.py`, and is not
repeated here.
"""

from __future__ import annotations

import asyncio
import os
import signal
from asyncio.subprocess import Process
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.postgres import _schema as s
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service import provenance
from taktus.composition.daemon import wire

from .conftest import free_port
from .test_daemon_scaling import settings, submit
from .test_daemon_shutdown import daemon, wait_ready
from .test_restart import COMMANDS, Database
from .test_restart import bundle as restart_bundle

TENANT = f"failover_{os.urandom(4).hex()}"
"""A tenant of its own: a job another test left in a shared tenant is not this test's to run."""
RUNS = 20
CONCURRENCY = 2
LEASE_SECONDS = 5
"""The shortest lease the daemon accepts; a runner renews it every third of that."""


def bundle(n: int) -> dict[str, Any]:
    document = restart_bundle()
    document["id"] = f"failover-{os.getpid()}-{n}"
    return document


@dataclass
class Claim:
    """One holder of one job's claim, as the job table showed it."""

    claimant: str
    first_seen: datetime
    """The `claimed_at` of the first row that showed this holder: when it claimed the job."""
    last_renewed: datetime
    """The latest `claimed_at` seen while this holder had the claim."""


@dataclass
class Claims:
    """Every holder of every job of this test, in the order they held it."""

    by_job: dict[str, list[Claim]] = field(default_factory=dict)
    run_of: dict[str, str] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    """How often each job was claimed, as the table counted it."""
    most: dict[str, int] = field(default_factory=dict)
    """The most jobs each runner held at once, in any one reading of the table."""

    def observe(self, rows: Iterable[Any], runs: set[str]) -> None:
        rows = list(rows)
        held: dict[str, int] = {}
        for row in rows:
            if str(row.payload.get("run_id", "")) in runs and row.claimed_by is not None:
                held[row.claimed_by] = held.get(row.claimed_by, 0) + 1
        for claimant, count in held.items():
            self.most[claimant] = max(self.most.get(claimant, 0), count)
        for row in rows:
            run_id = str(row.payload.get("run_id", ""))
            if run_id not in runs or row.claimed_by is None or row.claimed_at is None:
                continue
            self.run_of[row.id] = run_id
            self.attempts[row.id] = row.attempts
            history = self.by_job.setdefault(row.id, [])
            if history and history[-1].claimant == row.claimed_by:
                if row.claimed_at > history[-1].last_renewed:
                    history[-1].last_renewed = row.claimed_at
                continue
            if history and row.claimed_at <= history[-1].last_renewed:
                raise AssertionError(
                    f"job {row.id} changed holder from {history[-1].claimant} to "
                    f"{row.claimed_by} without a claim later than the last renewal"
                )
            history.append(Claim(row.claimed_by, row.claimed_at, row.claimed_at))

    def holders(self) -> set[str]:
        return {c.claimant for history in self.by_job.values() for c in history}

    def completed(self, rows: Iterable[Any]) -> set[str]:
        """The jobs that were claimed and are gone from the table: completed."""
        present = {row.id for row in rows}
        return {job for job in self.by_job if job not in present}


def held_by(rows: Iterable[Any], claimant: str, runs: set[str]) -> dict[str, Any]:
    """The rows of the jobs of `runs` that `claimant` holds now, by run."""
    held = {}
    for row in rows:
        run_id = str(row.payload.get("run_id", ""))
        if run_id in runs and row.claimed_by == claimant:
            held[run_id] = row
    return held


async def create_tenant(database: Database) -> None:
    async with database.persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": database.tenant}
        )
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"),
            {"t": database.tenant},
        )


async def job_rows(database: Database) -> list[Any]:
    async with database.persistence.transaction(TENANT):
        connection = database.persistence.connection(TENANT)
        result = await connection.execute(
            select(
                s.job.c.id,
                s.job.c.payload,
                s.job.c.claimed_by,
                s.job.c.claimed_at,
                s.job.c.attempts,
            ).where(s.job.c.tenant == TENANT)
        )
        return list(result)


async def describe(database: Database, run_ids: list[str], claims: Claims) -> str:
    """What every run and every claim looked like, for a failure message."""
    lines = []
    for run_id in run_ids:
        run = await database.run(run_id)
        if run is None:
            lines.append(f"{run_id}: missing")
            continue
        steps = ", ".join(
            f"{s.step_id}={s.state}" + (f"({s.reason})" if s.reason else "") for s in run.step_runs
        )
        kinds = [e.kind for e in await database.entries(run_id)]
        lines.append(f"{run_id}: {run.state} {run.cause or ''} {run.reason or ''} [{steps}]")
        lines.append(f"    {kinds}")
    for job, history in claims.by_job.items():
        holders = [c.claimant for c in history]
        lines.append(f"{job} ({claims.run_of[job]}): {holders}, {claims.attempts[job]} claims")
    return "\n".join(lines)


async def all_finished(database: Database, run_ids: list[str]) -> bool:
    async with database.persistence.transaction(TENANT):
        stored = [await database.runs.get(TENANT, run_id) for run_id in run_ids]
    return all(r is not None and r.state is RunState.FINISHED for r in stored)


async def test_two_runners_share_the_runs_and_the_survivor_resumes_a_killed_runners_run(
    worker_endpoint: str, postgres_url: str, tmp_path: Path
) -> None:
    database = Database(postgres_url, TENANT)
    await create_tenant(database)
    tenancy = {"TAKTUS_TENANTS": TENANT, "TAKTUS_PROVISIONAL_IDENTITY": f"{TENANT}=idn_test"}
    configured = settings(postgres_url, tmp_path, TAKTUS_WORKER=worker_endpoint, **tenancy)
    environment = {
        **tenancy,
        "TAKTUS_DATABASE_URL": postgres_url,
        "TAKTUS_ROLES": "runner",
        "TAKTUS_WORKER": worker_endpoint,
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
        "TAKTUS_POLL_SECONDS": "0.05",
        "TAKTUS_LEASE_SECONDS": str(LEASE_SECONDS),
        # Two runs per runner. The reference worker accepts four assignments at once and
        # answers 503 beyond, which fails the step. After the kill, the killed runner's
        # assignments keep running in the worker beside the survivor's two: four again.
        "TAKTUS_RUNNER_CONCURRENCY": str(CONCURRENCY),
        "TAKTUS_SHUTDOWN_CEILING_SECONDS": "20",
        "TAKTUS_LOG_LEVEL": "debug",
    }
    claims = Claims()
    processes: dict[str, Process] = {}
    logs = {name: tmp_path / f"taktusd-{name}.log" for name in ("a", "b")}
    try:
        for name in ("a", "b"):
            port = free_port()
            processes[name] = await daemon(
                {**environment, "TAKTUS_HTTP_PORT": str(port), "TAKTUS_INSTANCE": name},
                logs[name],
            )
            await wait_ready(port, processes[name])
        # Submitted once both serve, so that neither has a head start.
        async with wire(configured, EnvironmentConfiguration({})) as wired:
            runs = [await submit(wired, bundle(n), TENANT) for n in range(RUNS)]
        run_ids = [r.id for r in runs]
        ours = set(run_ids)

        # Until some runs are done, and A holds a run whose worker step has persisted an inner
        # boundary: the kill then lands inside a step with something to resume from.
        victim: Run | None = None
        searching = asyncio.timeout(60)
        try:
            async with searching:
                while victim is None:
                    for name, process in processes.items():
                        assert process.returncode is None, f"runner {name} exited; see {logs[name]}"
                    rows = await job_rows(database)
                    claims.observe(rows, ours)
                    ready = len(claims.completed(rows)) >= 4
                    for run_id in held_by(rows, "a", ours) if ready else ():
                        stored = await database.run(run_id)
                        if stored is None or stored.state is not RunState.RUNNING:
                            continue
                        compute = stored.step_run("compute")
                        if compute.state is StepState.RUNNING and compute.checkpoint is not None:
                            victim = stored
                            break
                    else:
                        await asyncio.sleep(0.02)
        except TimeoutError:
            raise AssertionError(
                "runner a never held a run inside its worker step after four were done:\n"
                + await describe(database, run_ids, claims)
            ) from None
        processes["a"].kill()
        assert await processes["a"].wait() == -signal.SIGKILL

        # What A left behind: its claims, frozen at its last renewal, and the victim's step in
        # flight with its boundary.
        rows = await job_rows(database)
        claims.observe(rows, ours)
        left = held_by(rows, "a", ours)
        orphaned = set(left)
        assert victim.id in orphaned
        died = {row.id: row.claimed_at for row in left.values()}
        interrupted: dict[str, Run] = {}
        for run_id in orphaned:
            stored = await database.run(run_id)
            assert stored is not None
            interrupted[run_id] = stored
        compute = interrupted[victim.id].step_run("compute")
        assert compute.state is StepState.RUNNING and compute.checkpoint is not None
        produced_before = [a.id for a in compute.artifacts]
        assert 0 < len(produced_before) < COMMANDS, "killed inside the step, at a boundary"
        before = {run_id: await database.entries(run_id) for run_id in orphaned}
        assert await database.verifies(), "nothing A wrote broke the chain"

        deadline = asyncio.get_running_loop().time() + 120
        while not await all_finished(database, run_ids):
            assert processes["b"].returncode is None, f"runner b exited; see {logs['b']}"
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(
                    "not every run finished within 120 seconds of the kill:\n"
                    + await describe(database, run_ids, claims)
                )
            claims.observe(await job_rows(database), ours)
            await asyncio.sleep(0.02)
        processes["b"].send_signal(signal.SIGTERM)
        stopped = await asyncio.wait_for(processes["b"].wait(), timeout=25)
        assert stopped == 0, logs["b"].read_text()
    finally:
        for process in processes.values():
            if process.returncode is None:
                process.kill()

    # The runs were shared, and each claim had one holder at a time: a job changed holder
    # only when A had died holding it, only to B, and only after A's lease had run out.
    assert claims.holders() == {"a", "b"}, "both runners held claims"
    assert all(n <= CONCURRENCY for n in claims.most.values()), (
        f"a runner held more jobs than its concurrency: {claims.most} (NTC-0027)"
    )
    for job, history in claims.by_job.items():
        holders = [c.claimant for c in history]
        if job in died:
            assert holders == ["a", "b"], f"job {job}: {holders}"
            taken = history[1].first_seen
            assert taken >= died[job] + timedelta(seconds=LEASE_SECONDS), (
                f"job {job} was claimed by b {taken - died[job]} after a's last renewal"
            )
        else:
            assert len(holders) == 1, f"job {job} changed holder while its runner lived"
    remaining = [r for r in await job_rows(database) if r.payload.get("run_id") in ours]
    assert remaining == [], "every job of a finished run is completed and gone"

    async with database.persistence.transaction(TENANT):
        ledger = [e for e in await database.ledger.entries(TENANT) if e.refs.run_id in ours]
    for run_id in run_ids:
        try:
            finished = await database.run(run_id)
            assert finished is not None and finished.state is RunState.FINISHED
            assert [s.state for s in finished.step_runs] == [StepState.SUCCEEDED] * 4
            entries = [e for e in ledger if e.refs.run_id == run_id]
            kinds = [e.kind for e in entries]
            assert kinds[-1] == "run.finished" and kinds.count("run.finished") == 1
            started = [e.refs.step_id for e in entries if e.kind == "step.started"]
            ids = [a.id for a in finished.step_run("compute").artifacts]
            assert ids == [f"output-{n}" for n in range(1, COMMANDS + 1)], "every output, once"
            if run_id in orphaned:
                # Recovered by B at the boundary A left: nothing A wrote changed, the entry after
                # it is the recovery, and only a step A had started was started again. A step A
                # had admitted and not yet started is in flight too, and goes back to its start:
                # it is started once, by B (NTC-0046).
                earlier = before[run_id]
                assert entries[: len(earlier)] == earlier
                was = interrupted[run_id]
                if was.state is RunState.FINISHED:
                    # A died after the run ended and before it completed the job (NTC-0026).
                    assert entries == earlier, f"run {run_id} ended before A died; nothing follows"
                else:
                    expected = (
                        "run.started"
                        if was.state is RunState.PLANNED and was.in_flight() is None
                        else "run.recovered"
                    )
                    assert kinds[len(earlier)] == expected, (run_id, kinds[len(earlier) :])
                    assert kinds.count("run.recovered") == (expected == "run.recovered")
                in_flight = was.in_flight()
                started_by_a = {e.refs.step_id for e in earlier if e.kind == "step.started"}
                restarted = in_flight is not None and in_flight.step_id in started_by_a
                assert restarted == (
                    in_flight is not None and in_flight.state is StepState.RUNNING
                ), f"run {run_id}: a step is running exactly when A wrote its start"
                again = [step for step in set(started) if started.count(step) > 1]
                assert again == ([in_flight.step_id] if restarted else []), (
                    f"run {run_id}: started more than once {again}; in flight at the kill "
                    f"{None if in_flight is None else (in_flight.step_id, in_flight.state)}"
                )
                if in_flight is not None and not restarted:
                    by_b = [
                        e.refs.step_id for e in entries[len(earlier) :] if e.kind == "step.started"
                    ]
                    assert in_flight.step_id in by_b, f"run {run_id}: B started the admitted step"
                finished_before = {
                    s.step_id
                    for s in interrupted[run_id].step_runs
                    if s.state is StepState.SUCCEEDED
                }
                assert finished_before.isdisjoint(again), "no finished step ran twice"
            else:
                assert "run.recovered" not in kinds
                assert sorted(started) == sorted(set(started)), f"run {run_id}: {started}"
                assert len(started) == 4, "every step started once"
            records = await database.records(run_id)
            verification = provenance.verify(finished, records, entries)
            assert verification.intact, (run_id, verification.findings)
        except AssertionError as failure:
            # What every run and claim looked like, so that a failure in CI explains itself.
            raise AssertionError(
                f"{failure}\n" + await describe(database, run_ids, claims)
            ) from failure

    # The victim's worker step continued from the checkpoint A left, not from its start.
    resumed = await database.run(victim.id)
    assert resumed is not None
    ids = [a.id for a in resumed.step_run("compute").artifacts]
    assert ids[: len(produced_before)] == produced_before, "what A produced stayed"
    assert resumed.step_run("compute").checkpoint is not None
    assert resumed.step_run("compute").checkpoint.ref != compute.checkpoint.ref
    assert await database.verifies()
    text = logs["b"].read_text()
    assert "runner stopped" in text and "taktusd stopped" in text
    await database.close()
