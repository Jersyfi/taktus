"""`taktusctl residency`: a tenant's residency rule shown, set, narrowed per data class, and a
class wider than the tenant's own refused (ADR-0116 §3)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .test_first_slice import PLAIN, taktusctl


def residency(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "residency", *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_an_operator_sets_the_rule_and_a_class_never_widens_it(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shipped = residency(state, "show")
    assert shipped.returncode == 0, shipped.stderr
    document = json.loads(shipped.stdout)
    assert (document["shipped_default"], document["location"]) == (True, "anywhere")

    configured = residency(state, "set", "--location", "eu", "--class", "personal=own")
    assert configured.returncode == 0, configured.stderr
    again = json.loads(residency(state, "show").stdout)
    assert again["shipped_default"] is False
    assert (again["location"], again["classes"]) == ("eu", {"personal": "own"})

    wider = residency(state, "set", "--class", "public=anywhere")
    assert wider.returncode == 2 and "never widens" in wider.stderr
    unknown = residency(state, "set", "--location", "moon")
    assert unknown.returncode == 2 and "own, eu, anywhere" in unknown.stderr
