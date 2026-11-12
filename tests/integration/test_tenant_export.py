"""A tenant exported and imported into a fresh instance, proven by its chains (ADR-0221).

The roadmap's condition for `1.0.0`: an export of a tenant — processes, runs, ledger,
provenance, artifacts — is imported into a fresh instance, and the ledger chain and every
provenance chain verify there.

Two instances, each a database and a state directory of its own. On the first, `taktusctl run`
runs a process of rules to its end, and a second process at level 2 waits for a person before
its first step. `taktusctl tenant export` writes the tenant to one file. On the second, fresh,
`taktusctl tenant import` reads it and checks it. Then: every ledger entry, every run and every
provenance record is the same as on the first, every object the runs name is held by the
second instance, the waiting run continues there to its end, and the ledger still verifies.
A second import into the same tenant is refused, and so is an export whose bytes changed.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fakes.identity import added_by_command_line

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresRepository,
)
from taktus.components.run.domain.model import Run, RunState

from .conftest import administration, database
from .test_daemon_scaling import rule_only_bundle
from .test_first_slice import PLAIN, taktusctl

TENANT = "default"


@pytest.fixture
def fresh(postgres_server: str, template: str) -> Iterator[str]:
    """A second instance's database, migrated and empty: the instance the export goes to."""
    name = f"integration_{os.urandom(6).hex()}"
    with administration(postgres_server) as connection:
        connection.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    try:
        yield database(postgres_server, name)
    finally:
        with administration(postgres_server) as connection:
            connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def ctl(url: str, state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), *arguments],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN, "TAKTUS_DATABASE_URL": url, "TAKTUS_STATE_DIR": str(state)},
        check=False,
    )


def waiting_bundle() -> dict[str, Any]:
    document = rule_only_bundle(2)
    document["id"] = f"export-waits-{os.getpid()}"
    document["autonomy"] = {"level": 2, "reason": "a person confirms", "toward_next": "-"}
    return document


async def everything(url: str) -> dict[str, Any]:
    persistence = PostgresPersistence(url, pool_size=1)
    try:
        async with persistence.transaction(TENANT):
            entries = await PostgresLedgerStore(persistence).entries(TENANT)
            runs = await PostgresRepository(persistence, Run).list(TENANT)
            records = [
                r.document()
                for run in runs
                for r in await PostgresProvenanceStore(persistence).of_run(TENANT, run.id)
            ]
        return {
            "ledger": [e.document() for e in entries],
            "runs": {r.id: r for r in runs},
            "provenance": records,
        }
    finally:
        await persistence.close()


def digests_of(runs: dict[str, Run]) -> set[str]:
    found: set[str] = set()
    for run in runs.values():
        for step_run in run.step_runs:
            if step_run.checkpoint is not None and step_run.checkpoint.result_digest:
                found.add(step_run.checkpoint.result_digest)
    return found


async def test_an_export_imported_into_a_fresh_instance_verifies_there_and_runs_on(
    postgres_url: str, fresh: str, tmp_path: Path
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    finished, waits = tmp_path / "finished.yaml", tmp_path / "waits.yaml"
    finished.write_text(yaml.safe_dump(rule_only_bundle(1)), encoding="utf-8")
    waits.write_text(yaml.safe_dump(waiting_bundle()), encoding="utf-8")
    added_by_command_line(
        taktusctl(),
        "idn_test",
        {**os.environ, "TAKTUS_DATABASE_URL": postgres_url, "TAKTUS_STATE_DIR": str(first)},
    )
    done = ctl(postgres_url, first, "run", "--process", str(finished))
    assert done.returncode == 0, done.stdout + done.stderr
    waiting = ctl(postgres_url, first, "run", "--process", str(waits))
    assert waiting.returncode == 3, waiting.stdout + waiting.stderr
    hint = next(line for line in waiting.stdout.splitlines() if "waits for a person:" in line)
    run_id = hint.split("--resume ", 1)[1].split()[0]
    before = await everything(postgres_url)
    assert {r.state for r in before["runs"].values()} == {RunState.FINISHED, RunState.WAITING_HUMAN}

    export = tmp_path / "tenant.json"
    written = ctl(postgres_url, first, "tenant", "export", TENANT, "--out", str(export))
    assert written.returncode == 0, written.stdout + written.stderr
    document = json.loads(export.read_text(encoding="utf-8"))
    assert document["ledger"]["verified"] is True
    assert set(document["objects"]) >= digests_of(before["runs"])

    read = ctl(fresh, second, "tenant", "import", str(export))
    assert read.returncode == 0, read.stdout + read.stderr
    assert "ledger      verifies" in read.stdout
    assert "chains      as exported" in read.stdout
    assert "provenance  verifies" in read.stdout

    after = await everything(fresh)
    # Everything the first instance held, entry for entry, and the import recorded after it.
    assert document["ledger"]["entries"] == len(before["ledger"])
    assert after["ledger"][: len(before["ledger"])] == before["ledger"]
    assert [e["kind"] for e in after["ledger"]][-1] == "tenant.imported"
    assert after["runs"] == before["runs"] and after["provenance"] == before["provenance"]
    objects = MemoryObjectStore(second / "objects")
    for digest in digests_of(before["runs"]):
        assert await objects.get(digest) is not None, digest

    # The waiting run continues on the second instance, from where it waited.
    for _ in range(3):
        resumed = ctl(fresh, second, "run", "--process", str(waits), "--resume", run_id)
        line = next((ln for ln in resumed.stdout.splitlines() if "waits for a person:" in ln), None)
        if line is None:
            break
        step = line.split()[-1]
        resumed = ctl(
            fresh, second, "run", "--process", str(waits), "--resume", run_id, "--approve", step
        )
        if resumed.returncode == 0:
            break
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert "DOES NOT VERIFY" not in resumed.stdout
    assert (await everything(fresh))["runs"][run_id].state is RunState.FINISHED

    again = ctl(fresh, second, "tenant", "import", str(export))
    assert again.returncode == 2 and "already holds" in again.stderr, again.stdout + again.stderr


def test_an_export_whose_bytes_changed_is_refused(postgres_url: str, tmp_path: Path) -> None:
    state = tmp_path / "state"
    export = tmp_path / "tenant.json"
    written = ctl(postgres_url, state, "tenant", "export", TENANT, "--out", str(export))
    assert written.returncode == 0, written.stdout + written.stderr
    document = json.loads(export.read_text(encoding="utf-8"))
    document["tenant"]["name"] = "someone else"
    export.write_text(json.dumps(document), encoding="utf-8")
    refused = ctl(postgres_url, state, "tenant", "import", str(export))
    assert refused.returncode == 2 and "digest does not match" in refused.stderr, refused.stderr


def test_an_export_needs_the_database(tmp_path: Path) -> None:
    completed = subprocess.run(  # noqa: S603
        [taktusctl(), "tenant", "export", TENANT, "--out", str(tmp_path / "x.json")],
        capture_output=True,
        text=True,
        env={
            **{k: v for k, v in os.environ.items() if k != "TAKTUS_DATABASE_URL"},
            **PLAIN,
            "TAKTUS_STATE_DIR": str(tmp_path / "state"),
        },
        check=False,
    )
    assert completed.returncode == 2 and "TAKTUS_DATABASE_URL" in completed.stderr
