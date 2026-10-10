"""Event triggers in the process component (`contracts/events/v1`, ADR-0048): how a filter
decides, which trigger a version reacts with, the inputs it gives, and what registration
refuses — every finding at once."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import Event, InvalidProcess, Kind, holds

AT = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


def event(kind: Kind = Kind.ISSUE_LABELLED, **context: Any) -> Event:
    return Event(
        id="dlv_1",
        kind=kind,
        channel="channel.repo",
        occurred_at=AT,
        received_at=AT,
        context=context or {"repository": "acme/taktus", "issue": "76", "label": "ready"},
    )


def bundle(*triggers: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "p",
        "version": "1",
        "name": "P",
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "inputs": {
            "issue": {"description": "the issue", "example": 11},
            "path": {"description": "a path", "example": "docs"},
        },
        "triggers": list(triggers),
        "steps": [
            {
                "id": "one",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "exact",
                "work": {"rule": "constant", "value": 1},
            }
        ],
    }


def test_every_entry_must_hold_and_each_holds_for_any_of_its_values() -> None:
    labelled = event()
    assert holds(None, labelled)
    assert holds({"label": "ready"}, labelled)
    assert holds({"label": ("wontfix", "ready"), "repository": "acme/taktus"}, labelled)
    assert not holds({"label": "ready", "repository": "other/repo"}, labelled)
    assert not holds({"branch": "main"}, labelled), "a field the event lacks fails its entry"


def test_a_list_valued_field_holds_when_any_element_does() -> None:
    pushed = event(
        Kind.BRANCH_PUSHED,
        repository="acme/taktus",
        branch="main",
        head="c0ffee",
        paths=("docs/roadmap.md", "docs/status.md"),
    )
    assert holds({"branch": "main", "paths": "docs/roadmap.md"}, pushed)
    assert not holds({"paths": "README.md"}, pushed)


def test_a_flag_is_not_a_string() -> None:
    comment = event(
        Kind.ISSUE_COMMENT_CREATED,
        repository="a/b",
        issue="1",
        comment="9",
        is_pull_request=True,
    )
    assert holds({"is_pull_request": True}, comment)
    assert not holds({"is_pull_request": "true"}, comment)


def test_the_first_matching_trigger_gives_the_inputs_with_an_integer_as_declared() -> None:
    version = parse_bundle(
        bundle(
            {
                "event": "issue.labelled",
                "filter": {"label": "wontfix"},
                "inputs": {"path": "x"},
                "from_event": {"issue": "issue"},
            },
            {"event": "issue.labelled", "inputs": {"path": "y"}, "from_event": {"issue": "issue"}},
            {"event": "issue.labelled", "inputs": {"path": "z"}, "from_event": {"issue": "issue"}},
        )
    )
    trigger = version.reacting_to(event())
    assert trigger is not None and trigger.inputs == {"path": "y"}
    assert version.given_by(trigger, event()) == {"path": "y", "issue": 76}
    assert version.reacting_to(event(Kind.ISSUE_OPENED, repository="a/b", issue="1")) is None


def test_registration_refuses_what_the_contract_refuses_with_every_finding_at_once() -> None:
    with pytest.raises(InvalidProcess) as refused:
        parse_bundle(
            bundle(
                {"event": "issue.ready", "inputs": {"issue": 1, "path": "a"}},
                {
                    "event": "issue.labelled",
                    "filter": {"branch": "main"},
                    "condition": "the issue looks finished",
                    "from_event": {"issue": "issue", "path": "comment"},
                },
                {"event": "pipeline_run.completed", "from_event": {"issue": "pull_request"}},
            )
        )
    findings = " | ".join(refused.value.findings)
    assert "'issue.ready', which is not a kind" in findings
    assert "filters on branch" in findings
    assert "the condition 'the issue looks finished'" in findings
    assert "path <- comment" in findings
    assert "issue <- pull_request" in findings, "an optional field may be missing"
    assert "gives no value for the input(s) path" in findings


def test_p03_with_its_event_trigger_is_refused_until_closing_section_is_generated() -> None:
    """NTC-0103: a trigger cannot give `closing_section`, so P-03 carries no trigger until #77."""
    path = Path(__file__).resolve().parents[3] / (
        "blueprints/dev-orchestration/processes/P-03-implementation.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["triggers"] == []
    document["triggers"] = [
        {
            "event": "issue.labelled",
            "filter": {"label": "ready"},
            "condition": "capacity.available",
            "inputs": {
                "records_path": "docs/decisions/open",
                "repository_url": "https://repo.example/owner/name.git",
                "repository_host": "repo.example",
                "coding_credential": "CODING_AGENT_API_KEY",
            },
            "from_event": {"issue": "issue"},
        }
    ]
    with pytest.raises(InvalidProcess) as refused:
        parse_bundle(document)
    assert refused.value.findings == (
        "the event trigger 'issue.labelled' gives no value for the input(s) closing_section; "
        "a run started by an event has nobody to ask, so the trigger names them in `inputs` or "
        "`from_event`",
    )
