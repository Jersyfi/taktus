"""`taktusctl messages` and `taktusctl case`: a tenant's rules for outward messages shown and
changed, quiet hours that cannot hold refused, and a person's answer in a case recorded
(ADR-0142, UC-7.6)."""

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


def test_an_operator_sets_the_label_and_quiet_hours_and_records_an_answer(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shipped = ctl(state, "messages", "show")
    assert shipped.returncode == 0, shipped.stderr
    document = json.loads(shipped.stdout)
    assert document["shipped_default"] is True and document.get("label") is None

    configured = ctl(
        state,
        "messages",
        "set",
        "--label",
        "Written by an AI system.",
        "--quiet",
        "22:00-07:00",
        "--zone",
        "Europe/Berlin",
        "--recipient-limit",
        "3",
    )
    assert configured.returncode == 0, configured.stderr
    again = json.loads(ctl(state, "messages", "show").stdout)
    assert again["label"] == "Written by an AI system." and again["recipient_limit"] == 3
    assert (again["quiet_begins"], again["quiet_ends"]) == ("22:00:00", "07:00:00")

    wrong = ctl(state, "messages", "set", "--quiet", "07:00-07:00")
    assert wrong.returncode == 2 and "different times" in wrong.stderr

    answered = ctl(state, "case", "answered", "support", "T-17")
    assert answered.returncode == 0, answered.stderr
    assert json.loads(answered.stdout)["case"] == "T-17"
