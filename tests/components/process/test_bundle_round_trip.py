"""A registered version written back as a bundle registers as the same version under a new name
(UC-4.15 *rolling back is one act*, ADR-0091 §5).

Every bundle the repository ships is read, written back and read again: the steps with their
work, the autonomy statement, the triggers, the inputs, the service level and the limits come
back unchanged; only the version's name, its author and its reason are the rollback's.

A bundle that declares every field a version has is written back and compared field by field:
a declaration added to the version and not carried by `bundle_of` fails here, as the caps on
open work once did (#611).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.process.domain.service.bundle import bundle_of, next_version

ROOT = Path(__file__).resolve().parents[3]
BUNDLES = sorted((ROOT / "blueprints").glob("*/processes/*.yaml"))


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
def test_a_version_written_back_registers_as_itself_under_a_new_name(path: Path) -> None:
    version = parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8")))
    again = parse_bundle(
        bundle_of(version, as_version="restored", author="idn_ada", reason="rolled back")
    )
    assert again.version == "restored"
    assert (again.author, again.reason) == ("idn_ada", "rolled back")
    assert (
        again.model_copy(
            update={"version": version.version, "author": version.author, "reason": version.reason}
        )
        == version
    )


EXAMPLE = ROOT / "examples" / "processes" / "six-times-seven.yaml"
RENAMED = {"version": "restored", "author": "idn_ada", "reason": "rolled back"}
"""The fields a rollback gives anew; every other one is the restored version's."""


def every_field() -> dict[str, Any]:
    """The worked example with every declaration a version can carry, none left at its default."""
    document: dict[str, Any] = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    document["inputs"] = {"due": {"description": "when the answer is due", "example": "2026-11-02"}}
    document["triggers"] = [
        {"schedule": "0 6 * * 1-5", "inputs": {"due": "2026-11-02"}},
        {
            "event": "issue.labelled",
            "filter": {"label": ["ready", "now"]},
            "inputs": {"due": "2026-11-02"},
        },
    ]
    document["slo"] = {"freshness": "24h", "latency": "90s"}
    document["expect"] = {"schedule": "0 7 * * 1-5", "bound": "2h"}
    document["open_work"] = {
        "pull_requests": {
            "cap": 2,
            "reading": {
                "operation": "repository.pullrequests.list",
                "input": {"state": "open"},
                "credentials": [{"name": "repository"}],
                "select": "pull_requests",
            },
            "check_every": "30m",
        },
        "tasks": {"cap": 5},
    }
    document["deadlines"] = {
        "answer": {
            "from": "run",
            "limit": "1d",
            "lead": "4h",
            "counts": "working",
            "until": {"step": "settle"},
            "at_lead": {"remind": "operations"},
            "at_limit": {"escalate": "operations-lead"},
        },
        "follow_up": {
            "from": {"after": "compute"},
            "limit": "2h",
            "until": {"step": "verify-answer"},
            "at_limit": {"start": {"process": "six-times-seven", "inputs": {"a": 1}}},
        },
        "due": {
            "from": {"date": "due"},
            "limit": "0s",
            "until": {"step": "verify-answer"},
            "at_limit": {"escalate": "operations"},
        },
    }
    document["evaluation"] = {
        "cases": [
            {
                "id": "forty-two",
                "inputs": {"due": "2026-11-02"},
                "targets": {"prepare-commands": {"commands": ["expr 6 '*' 7"]}, "compute": "42"},
            }
        ],
        "scorers": [
            {
                "step": "prepare-commands",
                "method": "rule",
                "reason": "the commands are fixed",
                "exactness": "exact",
                "rule": {"kind": "equals"},
            },
            {
                "step": "compute",
                "method": "llm",
                "reason": "the worker's answer may be phrased in many ways",
                "rejected": [{"method": "rule", "why": "a number may be written in words"}],
                "exactness": "tolerant",
                "fallback": {"when": "the judge gives no score", "to": "rule"},
                "rule": {"kind": "contains"},
                "purpose": "judging",
                "criterion": "Does the answer give the same number?",
            },
        ],
        "schedule": "weekly",
    }
    return document


def test_the_bundle_of_every_field_leaves_no_field_at_its_default() -> None:
    """The guard on the test below: a field added to the version and not declared here fails,
    so that the comparison covers it before `bundle_of` can lose it."""
    version = parse_bundle(every_field())
    defaulted = [
        name
        for name, field in ProcessVersion.model_fields.items()
        if getattr(version, name) == field.get_default(call_default_factory=True)
    ]
    assert defaulted == [], f"declare {defaulted} in every_field(), and carry it in bundle_of"


@pytest.mark.parametrize("name", sorted(ProcessVersion.model_fields))
def test_every_field_a_version_declares_survives_being_written_back(name: str) -> None:
    version = parse_bundle(every_field())
    again = parse_bundle(
        bundle_of(version, as_version="restored", author="idn_ada", reason="rolled back")
    )
    if name in RENAMED:
        assert getattr(again, name) == RENAMED[name]
    else:
        assert getattr(again, name) == getattr(version, name), f"`{name}` is lost on a rollback"


def test_there_are_bundles_to_write_back() -> None:
    assert len(BUNDLES) >= 5


def test_the_next_version_is_one_above_the_highest_number_and_never_taken() -> None:
    assert next_version(["1", "2", "7"]) == "8"
    assert next_version(["v1", "v2"]) == "3"
    assert next_version(["v1", "3"]) == "4"
    assert next_version(["a", "2"]) == "3"
    assert next_version(["a", "b"]) == "3"
