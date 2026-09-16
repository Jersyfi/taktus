"""The stream rules against the transcript fixtures of the worker contract.

Every fixture under contracts/worker/v1/examples/transcript/valid/ must break no stream rule;
every fixture under invalid/W-NN-*.json must break exactly the check its name carries. This is
what makes the fixtures known good or known bad, and it is the test that pinned the rules when
they moved out of tools/validate_contracts.py (DEC-0003).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from taktus.conformance.rules import stream_violations

TRANSCRIPTS = Path(__file__).resolve().parents[2] / "contracts" / "worker" / "v1" / "examples"
TRANSCRIPTS /= "transcript"
VALID = sorted((TRANSCRIPTS / "valid").glob("*.json"))
INVALID = sorted((TRANSCRIPTS / "invalid").glob("W-*.json"))


type Json = dict[str, Any]


def load(path: Path) -> Json:
    with path.open(encoding="utf-8") as handle:
        result: Json = json.load(handle)
        return result


@pytest.mark.parametrize("path", VALID, ids=[p.stem for p in VALID])
def test_valid_transcript_breaks_no_rule(path: Path) -> None:
    transcript = load(path)
    assert not stream_violations(
        transcript["assignment"], transcript["estimate"], transcript["events"]
    )


@pytest.mark.parametrize("path", INVALID, ids=[p.stem for p in INVALID])
def test_invalid_transcript_breaks_its_check(path: Path) -> None:
    match = re.match(r"(W-\d{2})-", path.name)
    assert match is not None
    transcript = load(path)
    violations = stream_violations(
        transcript["assignment"], transcript["estimate"], transcript["events"]
    )
    assert match.group(1) in {v.check for v in violations}, [str(v) for v in violations]


def test_every_stream_check_has_a_fixture() -> None:
    named = {p.name[:4] for p in INVALID}
    assert named == {"W-03", "W-04", "W-05", "W-06", "W-07", "W-10", "W-11"}
