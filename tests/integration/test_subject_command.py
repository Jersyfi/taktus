"""`taktusctl subject` and `taktusctl evidence`: a request prepared, refused without the
identity check, withdrawn; the evidence printed and marked as not legally reviewed (ADR-0176,
UC-11.2). What a request finds and erases is proven in `tests/composition/test_subjects.py`."""

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


def test_a_request_is_prepared_and_never_carried_out_without_the_identity_check(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    prepared = ctl(state, "subject", "prepare", "--kind", "erasure", "--subject", "cust-1")
    assert prepared.returncode == 0, prepared.stderr
    request = json.loads(prepared.stdout)
    assert (request["state"], request["holds"]["runs"]) == ("prepared", 0)

    refused = ctl(state, "subject", "confirm", request["id"])
    assert refused.returncode == 2 and "checked the requester's identity" in refused.stderr
    assert json.loads(ctl(state, "subject", "show", request["id"]).stdout)["state"] == "prepared"

    withdrawn = ctl(state, "subject", "withdraw", request["id"])
    assert json.loads(withdrawn.stdout)["state"] == "withdrawn"
    again = ctl(state, "subject", "confirm", request["id"], "--identity-checked")
    assert again.returncode == 2 and "withdrawn" in again.stderr
    (listed,) = json.loads(ctl(state, "subject", "list").stdout)
    assert listed["state"] == "withdrawn" and "subject" not in listed


def test_the_evidence_is_generated_and_says_it_is_not_legally_reviewed(tmp_path: Path) -> None:
    printed = ctl(tmp_path / "state", "evidence")
    assert printed.returncode == 0, printed.stderr
    document = json.loads(printed.stdout)
    assert document["legally_reviewed"] is False
    assert {k["record"] for k in document["keeping"]} >= {"ledger", "provenance", "trace"}
