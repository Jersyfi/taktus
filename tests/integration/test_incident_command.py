"""`taktusctl incident`: the tenant's watch configured and shown, the incidents listed, and an
unknown one refused (ADR-0107)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .test_first_slice import PLAIN, taktusctl


def incident(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "incident", *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_an_operator_configures_the_watch_lists_incidents_and_closes_none_unknown(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    shipped = incident(state, "configure")
    assert shipped.returncode == 0, shipped.stderr
    document = json.loads(shipped.stdout)
    assert document["shipped_default"] is True and document["grace"] == "PT15M"

    configured = incident(state, "configure", "--grace", "5m", "--empty-share", "0.8")
    assert configured.returncode == 0, configured.stderr
    assert json.loads(configured.stdout)["grace"] == "PT5M"
    again = json.loads(incident(state, "configure").stdout)
    assert again["shipped_default"] is False and again["empty_share"] == 0.8

    refused = incident(state, "configure", "--empty-share", "2")
    assert refused.returncode == 2 and "empty_share" in refused.stderr

    blind = incident(state, "blind")
    assert blind.returncode == 0 and json.loads(blind.stdout) == []
    listed = incident(state, "list", "--all")
    assert listed.returncode == 0 and json.loads(listed.stdout) == []
    unknown = incident(state, "close", "inc_none")
    assert unknown.returncode == 2 and "no incident" in unknown.stderr
