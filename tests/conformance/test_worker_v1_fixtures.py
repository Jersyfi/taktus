"""The stream rules, the capacity rule and the id rules against the fixtures of the worker
contract.

Every fixture under contracts/worker/v1/examples/transcript/valid/ must break no stream rule;
every fixture under invalid/W-NN-*.json must break exactly the check its name carries. The same
holds for the capacity probes under examples/capacity-probe/ and W-15, the unknown-id probes
under examples/unknown-id-probe/ and W-16, and the repeated-id probes under
examples/repeated-id-probe/ and W-17. This is
what makes the fixtures known good or known bad, and it is the test that pinned the rules when
they moved out of tools/validate_contracts.py (DEC-0003).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from taktus.conformance.findings import Violation
from taktus.conformance.rules import (
    capacity_violations,
    repeated_id_violations,
    stream_violations,
    unknown_id_violations,
)

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
    assert named == {"W-03", "W-04", "W-05", "W-06", "W-07", "W-10", "W-11", "W-13", "W-14", "W-18"}


PROBES = TRANSCRIPTS.parent / "capacity-probe"
VALID_PROBES = sorted((PROBES / "valid").glob("*.json"))
INVALID_PROBES = sorted((PROBES / "invalid").glob("W-*.json"))


@pytest.mark.parametrize("path", VALID_PROBES, ids=[p.stem for p in VALID_PROBES])
def test_valid_capacity_probe_breaks_no_rule(path: Path) -> None:
    assert not capacity_violations(load(path))


@pytest.mark.parametrize("path", INVALID_PROBES, ids=[p.stem for p in INVALID_PROBES])
def test_invalid_capacity_probe_breaks_w15(path: Path) -> None:
    violations = capacity_violations(load(path))
    assert {v.check for v in violations} == {"W-15"}, [str(v) for v in violations]


def test_the_capacity_rule_has_fixtures() -> None:
    assert VALID_PROBES and INVALID_PROBES


# W-16 and W-17 concern an assignment's id: each probe directory, its rule and its check.
ID_PROBES = [
    ("unknown-id-probe", unknown_id_violations, "W-16"),
    ("repeated-id-probe", repeated_id_violations, "W-17"),
]
ID_CASES = [
    (path, rule, check if path.parent.name == "invalid" else None)
    for directory, rule, check in ID_PROBES
    for path in sorted((TRANSCRIPTS.parent / directory).glob("*/*.json"))
]


@pytest.mark.parametrize(
    ("path", "rule", "check"),
    ID_CASES,
    ids=[f"{p.parent.parent.name}/{p.parent.name}/{p.stem}" for p, _, _ in ID_CASES],
)
def test_id_probe_breaks_exactly_its_check(
    path: Path, rule: Callable[[Any], list[Violation]], check: str | None
) -> None:
    violations = rule(load(path))
    expected = set() if check is None else {check}
    assert {v.check for v in violations} == expected, [str(v) for v in violations]


def test_the_id_rules_have_fixtures() -> None:
    for directory, _, check in ID_PROBES:
        valid = list((TRANSCRIPTS.parent / directory / "valid").glob("*.json"))
        invalid = list((TRANSCRIPTS.parent / directory / "invalid").glob(f"{check}-*.json"))
        assert valid and invalid, directory
