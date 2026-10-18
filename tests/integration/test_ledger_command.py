"""`taktusctl ledger verify` end to end (ADR-0105): a chain in the development store verifies,
and one whose entry was altered on disk does not, with the finding and exit code 1."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .test_first_slice import PLAIN, taktusctl


async def recorded(state_dir: Path) -> None:
    persistence = MemoryPersistence(state_dir)
    ledger = ChainedLedger(MemoryLedgerStore(persistence), FakeClock())
    async with persistence.transaction("default"):
        for kind in ("run.created", "run.started", "run.finished"):
            await ledger.record("default", Fact(kind=kind, refs=LedgerRefs(run_id="run_1")))


def verify(state_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_")}
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "ledger", "verify", *args],
        capture_output=True,
        text=True,
        env={**inherited, **PLAIN, "TAKTUS_STATE_DIR": str(state_dir)},
        check=False,
    )


def test_a_chain_verifies_and_an_altered_one_does_not(tmp_path: Path) -> None:
    state = tmp_path / "state"
    asyncio.run(recorded(state))

    intact = verify(state)
    assert intact.returncode == 0, intact.stderr
    assert "chain of 3 entries, walked from the first entry: verifies" in intact.stdout
    full = verify(state, "--full", "--json")
    assert full.returncode == 0, full.stderr
    assert json.loads(full.stdout) == {
        "entries": 3,
        "intact": True,
        "findings": [],
        "checkpoint": 0,
    }

    path = state / "ledger.json"
    stored = json.loads(path.read_text())
    stored["default"][1]["kind"] = "run.forged"
    path.write_text(json.dumps(stored))
    altered = verify(state, "--full")
    assert altered.returncode == 1
    assert "DOES NOT VERIFY" in altered.stdout
    assert "entry 2: hash does not match its content" in altered.stdout
