"""`taktusctl sources`: a tenant's declaration of its sources shown, changed, and a capability
on both lists refused (ADR-0130, UC-7.7)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .test_first_slice import PLAIN, taktusctl


def sources(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "sources", *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_an_operator_declares_a_source_free_and_another_personal(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shipped = sources(state, "show")
    assert shipped.returncode == 0, shipped.stderr
    document = json.loads(shipped.stdout)
    assert document["shipped_default"] is True
    assert "free" not in document or document["free"] == []

    declared = sources(
        state, "declare", "--free", "analytics.cohorts", "--personal", "customers.accounts"
    )
    assert declared.returncode == 0, declared.stderr
    again = json.loads(sources(state, "show").stdout)
    assert again["shipped_default"] is False
    assert (again["free"], again["personal"]) == (["analytics.cohorts"], ["customers.accounts"])

    both = sources(state, "declare", "--free", "a.b", "--personal", "a.b")
    assert both.returncode == 2 and "at once" in both.stderr
