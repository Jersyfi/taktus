"""`taktusctl capacity` end to end: the machine it runs on observed, the growth per run from
the ledger, a crossing written once, and — with a database — the database as its own place,
measured by the database and held against the volume it is told."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

from taktus.adapters.driven.clock import SystemClock
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .test_first_slice import PLAIN, taktusctl

TENANT = "default"


def capacity(state_dir: Path, *args: str, **environment: str) -> subprocess.CompletedProcess[str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_")}
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "capacity", *args],
        capture_output=True,
        text=True,
        env={**inherited, **PLAIN, "TAKTUS_STATE_DIR": str(state_dir), **environment},
        check=False,
    )


async def two_runs(state_dir: Path) -> None:
    """Two runs in the development store's ledger, as `taktusctl run` would have left them."""
    persistence = MemoryPersistence(state_dir)
    ledger = ChainedLedger(MemoryLedgerStore(persistence), SystemClock())
    for n in (1, 2):
        async with persistence.transaction(TENANT):
            await ledger.record(TENANT, Fact(kind="run.created", refs=LedgerRefs(run_id=f"r{n}")))


def test_the_report_names_figures_and_records_a_crossing_once(tmp_path: Path) -> None:
    state = tmp_path / "state"
    asyncio.run(two_runs(state))
    # 100 % free memory is below no threshold; a warning share of 99 % makes storage and
    # memory findings a person must act on, whatever this machine has.
    tight = {
        "TAKTUS_CAPACITY_STORAGE_WARN_PERCENT": "99",
        "TAKTUS_CAPACITY_MEMORY_WARN_PERCENT": "99",
    }
    first = capacity(state, "--json", **tight)
    assert first.returncode == 1, first.stdout + first.stderr
    report = json.loads(first.stdout)
    storage = next(f for f in report["findings"] if f["subject"] == "storage (state directory)")
    assert storage["status"] == "act" and "below 99 %: a person must act now" in storage["text"]
    assert storage["bytes_per_run"] > 0, "the snapshot's size over the two runs it holds"
    assert "capacity.storage.state_directory=act" in report["recorded"]

    second = capacity(state, **tight)
    assert second.returncode == 1
    assert "[act] storage (state directory):" in second.stdout
    assert "recorded in the ledger" not in second.stdout, "the same state is not written twice"

    calm = capacity(state, "--no-record", "--json")
    assert json.loads(calm.stdout)["recorded"] == []


def test_the_database_is_measured_by_itself_and_held_against_its_volume(
    postgres_url: str, tmp_path: Path
) -> None:
    """A volume of 1 MiB cannot hold a migrated database: the report says so with the
    database's own size, and exits 1. `--no-record` keeps the shared database's chain as it
    was."""
    completed = capacity(
        tmp_path / "state",
        "--no-record",
        TAKTUS_DATABASE_URL=postgres_url,
        TAKTUS_CAPACITY_DATABASE_VOLUME_MB="1",
        TAKTUS_CAPACITY_STORAGE_EXPANDABLE="false",
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    line = next(li for li in completed.stdout.splitlines() if "storage (database)" in li)
    assert line.startswith("  [act] storage (database): 0 B free of 1.0 MiB (0 %)")
    assert "per run at most" in line or "no run is recorded yet" in line
    assert "expanding this volume is impossible on its storage class: plan a migration" in line


def test_a_wrong_setting_is_one_sentence_and_exit_2(tmp_path: Path) -> None:
    completed = capacity(tmp_path, TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT="50")
    assert completed.returncode == 2
    assert "TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT" in completed.stderr
    assert "Traceback" not in completed.stderr
