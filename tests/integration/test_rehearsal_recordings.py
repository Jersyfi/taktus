"""The local recordings of the replay on `main`, made again (ADR-0108).

Not a test of anything: the way `tests/rehearsal/recordings/` was made, kept so that it can be
made again while the recordings there are local ones. It runs only with
`TAKTUS_RECORD_LOCAL=1`, and then writes the directories itself:

    TAKTUS_RECORD_LOCAL=1 uv run pytest tests/integration/test_rehearsal_recordings.py \
        --basetemp=/tmp/taktus-record

It runs P-01, P-02, P-03 and S-07 for real, against the repository's fakes — the repository
service, the model endpoint, the coding agent — exactly as `test_dev_orchestration.py` does,
with the state in a PostgreSQL database, and then writes each run's recording with
`tools/record_rehearsal.py`, the tool the instance's recordings are taken with. A recording
from the instance replaces each of these; then this file is removed.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml
from fakes.identity import added_by_command_line
from fakes.maturity import configurations, verified

from taktus.adapters.driven.postgres import PostgresPersistence, PostgresRepository
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.run.domain.model import Run

from .conftest import ROOT
from .test_dev_orchestration import (
    BLUEPRINT,
    RECORDS,
    ROADMAP,
    Outside,
    backlog,
    hand,
    outside,  # noqa: F401 — the fixture, used by name
    p03_inputs,
)
from .test_first_slice import taktusctl

pytestmark = pytest.mark.skipif(
    not os.environ.get("TAKTUS_RECORD_LOCAL"),
    reason="writes the local recordings of tests/rehearsal; TAKTUS_RECORD_LOCAL=1 runs it",
)

RECORDINGS = ROOT / "tests" / "rehearsal" / "recordings"
TOOL = ROOT / "tools" / "record_rehearsal.py"
S07 = ROOT / "blueprints" / "self-operation" / "processes" / "S-07-change-in-dialogue.yaml"
TENANT = "default"


def environment(fakes: Outside, state_dir: Path, database: str) -> dict[str, str]:
    return {**fakes.environment(state_dir), "TAKTUS_DATABASE_URL": database}


def run(bundle: Path, env: dict[str, str], *inputs: str) -> None:
    command = [taktusctl(), "run", "--process", str(bundle)]
    for given in inputs:
        command += ["--input", given]
    completed = subprocess.run(  # noqa: S603 — our own entry point
        command, capture_output=True, text=True, env=env, check=False, timeout=300
    )
    assert "state finished" in completed.stdout, completed.stdout + completed.stderr


async def verify_adapters(fakes: Outside, database: str) -> None:
    """The fakes recorded as verified, as `test_dev_orchestration.verified` does in a snapshot."""
    declared = await configurations(
        workers={"worker.endpoint": fakes.worker_url},
        connectors={"connector.channel.repo": fakes.connector_url},
        models={"model.endpoint": ("fake-model", ("*",))},
    )
    postgres = PostgresPersistence(database)
    try:
        async with postgres.transaction(TENANT):
            store = PostgresRepository(postgres, AdapterMaturity)
            for configuration in declared:
                await store.put(TENANT, verified(configuration, TENANT))
    finally:
        await postgres.close()


async def last_run_of(database: str, process: str) -> str:
    postgres = PostgresPersistence(database)
    try:
        async with postgres.transaction(TENANT):
            runs = await PostgresRepository(postgres, Run).list(TENANT)
    finally:
        await postgres.close()
    found = [r for r in runs if r.process_version.startswith(process + "@")]
    return max(found, key=lambda r: r.created_at).id


def record(env: dict[str, str], state_dir: Path, process: str, run_id: str) -> None:
    target = RECORDINGS / process
    if target.exists():
        shutil.rmtree(target)  # the earlier local recording; the repository's history holds it
    completed = subprocess.run(  # noqa: S603 — our own tool, fixed arguments
        [
            sys.executable, str(TOOL), "--tenant", TENANT, "--run", run_id, "--out", str(target),
            "--objects", str(state_dir / "objects"), "--taken", "local",
        ],
        capture_output=True, text=True, env=env, check=False, timeout=120,
    )  # fmt: skip
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_record_the_local_recordings(
    outside: Outside,  # noqa: F811 — the fixture
    postgres_url: str,
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    env = environment(outside, state_dir, postgres_url)
    added_by_command_line(taktusctl(), "idn_test", env)
    asyncio.run(verify_adapters(outside, postgres_url))

    # The backlog P-02 and P-03 work on, and a roadmap P-01 holds it against.
    tasks = backlog(outside)
    report = outside.issue("Reports of P-01", "", ["report"], None)
    outside.commit_on_main(
        {
            "docs/roadmap.md": ROADMAP.format(
                first=f"A greeting (#{tasks.ready})", second="An item without an issue"
            )
        }
    )
    run(
        BLUEPRINT / "P-01-roadmap-control.yaml", env,
        "roadmap_path=docs/roadmap.md", f"records_path={RECORDS}", f"report_issue={report}",
    )  # fmt: skip
    run(BLUEPRINT / "P-02-refinement.yaml", env, f"issue={tasks.missing_section}")
    hand(outside, tasks.ready)
    outside.main_ran("success")
    run(BLUEPRINT / "P-03-implementation.yaml", env, *p03_inputs(outside, tasks.ready))

    # S-07 asks the model for a changed P-02: the fake answers with the bundle under another
    # version, as a model that understood the request would.
    changed = yaml.safe_load((BLUEPRINT / "P-02-refinement.yaml").read_text(encoding="utf-8"))
    changed["version"] = "local-change"
    httpx.post(
        f"{outside.model_url}/_fake/answer", json={"answer": json.dumps(changed)}, timeout=5
    ).raise_for_status()
    run(S07, env, "process=p02-refinement", "request=also post the sections as a comment")

    for process in ("p01-roadmap-control", "p02-refinement", "p03-implementation"):
        record(env, state_dir, process, asyncio.run(last_run_of(postgres_url, process)))
    record(
        env, state_dir, "s07-change-in-dialogue",
        asyncio.run(last_run_of(postgres_url, "s07-change-in-dialogue")),
    )  # fmt: skip
