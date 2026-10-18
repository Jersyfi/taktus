"""`taktusctl signal`: the signals in force listed, and a change by an identity the tenant does
not know refused and nothing changed (ADR-0109 §3)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .test_first_slice import PLAIN, taktusctl


def signal(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "signal", *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_an_unknown_identity_changes_no_corridor(tmp_path: Path) -> None:
    state = tmp_path / "state"
    listed = signal(state, "list")
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout) == []

    refused = signal(
        state,
        "configure",
        "cost.cloud_daily",
        "--process",
        "read-cost",
        "--step",
        "read",
        "--bounds",
        "fixed",
        "--yellow",
        "100",
        "--red",
        "150",
        "--role",
        "owner",
        "--case",
        "https://tickets.example/board/cost",
        "--identity",
        "idn_nobody",
    )
    assert refused.returncode == 2 and "is not known" in refused.stderr
    history = signal(state, "history", "cost.cloud_daily")
    assert history.returncode == 0 and json.loads(history.stdout) == []
