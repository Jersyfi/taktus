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
                "checks": [{"kind": "recomputation"}],
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


P03 = Path(__file__).resolve().parents[3] / (
    "blueprints/dev-orchestration/processes/P-03-implementation.yaml"
)


def test_p03_reacts_to_a_ready_label_and_its_trigger_needs_no_closing_section() -> None:
    """NTC-0112: the worker generates the closing section (#77), so `closing_section` is
    optional and the trigger of the blueprint's `issue.ready` is in place."""
    version = parse_bundle(yaml.safe_load(P03.read_text(encoding="utf-8")))
    assert version.inputs["closing_section"].required is False
    assert "closing_section" not in version.required_inputs
    trigger = version.reacting_to(event())
    assert trigger is not None and trigger.condition == "capacity.available"
    given = version.given_by(trigger, event())
    assert given["issue"] == 76 and "closing_section" not in given
    assert set(given) == set(version.required_inputs)
    assert version.reacting_to(event(label="wontfix", repository="a/b", issue="1")) is None


def test_a_trigger_need_not_give_an_optional_input_but_must_give_every_required_one() -> None:
    optional = bundle({"event": "issue.labelled", "from_event": {"issue": "issue"}})
    optional["inputs"]["path"]["required"] = False
    assert parse_bundle(optional).required_inputs == ("issue",)
    with pytest.raises(InvalidProcess) as refused:
        parse_bundle(bundle({"event": "issue.labelled", "from_event": {"issue": "issue"}}))
    assert refused.value.findings == (
        "the event trigger 'issue.labelled' gives no value for the input(s) path; a run started "
        "by an event has nobody to ask, so the trigger names them in `inputs` or `from_event`",
    )
