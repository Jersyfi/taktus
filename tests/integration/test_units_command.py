"""`taktusctl units`: a tenant's quotas per organisational unit set, shown and cleared, and a
quota on a person refused (ADR-0166, UC-7.11)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .test_first_slice import PLAIN, taktusctl


def ctl(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_an_operator_sets_shows_and_clears_a_unit_s_quota(tmp_path: Path) -> None:
    state = tmp_path / "state"
    assert json.loads(ctl(state, "units", "show").stdout) == []

    configured = ctl(
        state,
        "units",
        "set",
        "sales",
        "--concurrent",
        "2",
        "--budget",
        "250eur",
        "--identity",
        "ada",
    )
    assert configured.returncode == 0, configured.stderr
    (shown,) = json.loads(ctl(state, "units", "show").stdout)
    assert shown["org_unit"] == "sales" and shown["concurrent_runs"] == 2
    assert shown["budget"] == {"eur": 250.0}

    nothing = ctl(state, "units", "set", "sales")
    assert nothing.returncode == 2, "a quota names a limit"
    wrong = ctl(state, "units", "set", "sales", "--budget", "many")
    assert wrong.returncode == 2 and "250eur" in wrong.stderr

    cleared = ctl(state, "units", "clear", "sales")
    assert cleared.returncode == 0, cleared.stderr
    assert json.loads(ctl(state, "units", "show").stdout) == []


def test_a_quota_on_an_identity_is_refused(tmp_path: Path) -> None:
    state = tmp_path / "state"
    created = ctl(state, "identity", "add", "idn_ada")
    assert created.returncode == 0, created.stderr
    refused = ctl(state, "units", "set", "idn_ada", "--concurrent", "1")
    assert refused.returncode == 2 and "principle 14" in refused.stderr
