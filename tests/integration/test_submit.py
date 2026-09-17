"""`taktusctl submit` queues a run for the daemon: in a database it lands `planned` with a job;
in memory there is no daemon to claim, and the command says so."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import yaml

from taktus.adapters.driven.postgres import PostgresQueue
from taktus.components.run.domain.model import RunState

from .test_daemon_scaling import rule_only_bundle
from .test_first_slice import PLAIN, taktusctl
from .test_restart import TENANT, Database


def test_submit_queues_the_run_in_a_database(postgres_url: str, tmp_path: Path) -> None:
    process_file = tmp_path / "bundle.yaml"
    process_file.write_text(yaml.safe_dump(rule_only_bundle(99)), encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "submit", "--process", str(process_file)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN, "TAKTUS_DATABASE_URL": postgres_url},
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    run_id = completed.stdout.strip()
    assert run_id.startswith("run_")
    assert "state  database" in completed.stderr

    async def check() -> None:
        database = Database(postgres_url)
        try:
            run = await database.run(run_id)
            assert run is not None and run.state is RunState.PLANNED
            assert [e.kind for e in await database.entries(run_id)] == ["run.created"]
            async with database.persistence.transaction(TENANT):
                queue = PostgresQueue(database.persistence)
                claimed = await queue.claim(TENANT, "probe", 50)
                assert [j.id for j in claimed if j.payload["run_id"] == run_id], "one job"
                for job in claimed:  # the probe gives every job back
                    await queue.release(TENANT, job.id, "probe")
        finally:
            await database.close()

    asyncio.run(check())


def test_submit_refuses_without_a_database(tmp_path: Path) -> None:
    process_file = tmp_path / "bundle.yaml"
    process_file.write_text(yaml.safe_dump(rule_only_bundle(98)), encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "submit", "--process", str(process_file)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN, "TAKTUS_STATE_DIR": str(tmp_path / "state")},
        check=False,
    )
    assert completed.returncode == 2
    assert "submit needs a database" in completed.stderr
