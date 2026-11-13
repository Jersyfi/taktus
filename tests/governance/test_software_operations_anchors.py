"""The anchors the blueprint `software-operations` proposes hold a level-4 run where UC-03 §6
keeps an act with a person (ADR-0192, UC-03 §9).

The world is the one of `test_anchors.py`: the run engine over fakes of every port, with the
governance and decision components wired as the composition root wires them. What is real
here is the blueprint's own `anchors.json`, configured for the tenant as `taktusctl anchors
set` configures it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from components.run.test_case_scope import ACCOUNT, CustomerConnector, Declared, Scoped, step
from components.run.test_outward_messages import Outward, support

from governance.test_anchors import World, call, correcting, requests_of, rule, states
from taktus.components.governance.domain.model import AnchorConfiguration
from taktus.components.governance.domain.service.anchors import applying
from taktus.components.run.domain.model import RunState, StepState
from taktus.shared.v1 import DecisionStatus

ROOT = Path(__file__).resolve().parents[2]
PROPOSED = ROOT / "blueprints" / "software-operations" / "anchors.json"


def proposed() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(PROPOSED.read_text(encoding="utf-8"))
    return document


def with_decider(role: str) -> dict[str, Any]:
    """The proposal as a tenant takes it over: the decider is its own role."""
    document = proposed()
    for anchor in document["anchors"]:
        anchor["decider"] = {"role": role}
    return document


def test_the_proposal_is_a_configuration_that_keeps_the_legal_and_the_correction_class() -> None:
    configuration = AnchorConfiguration(id="t", tenant="t", **proposed())
    assert {a.id for a in configuration.anchors} == {
        "anc-money",
        "anc-legal",
        "anc-staff",
        "anc-limits",
        "anc-correction",
    }


@pytest.mark.parametrize(
    ("operation", "anchored"),
    [
        ("payment.release.submit", ["anc-money"]),
        ("payment.refund.create", ["anc-money"]),
        ("legal.filing.submit", ["anc-legal"]),
        ("staff.contracts.create", ["anc-staff"]),
        ("partnerships.agreements.end", ["anc-staff"]),
        ("orchestrator.levels.raise", ["anc-limits"]),
        ("orchestrator.limits.set", ["anc-limits"]),
        ("orchestrator.spend.read", []),
        ("payments.subscriptions.read", []),
        ("billing.costs.daily", []),
        ("repository.pullrequests.open", []),
    ],
)
def test_money_and_legal_acts_are_anchored_and_reading_a_payment_is_not(
    operation: str, anchored: list[str]
) -> None:
    """`payment.release.submit` is served today (UC-15.8); `payment.refund.create` and
    `legal.filing.submit` are served by no connector yet, and stand for any act a connector
    adds under those capabilities: the anchor holds it from the first call."""
    configuration = AnchorConfiguration(id="t", tenant="t", **proposed())
    found = applying(configuration, process="b-3-04", actions=[operation])
    assert [a.id for a in found] == anchored


@pytest.mark.parametrize(
    ("act", "kind"),
    [
        (call("act", "payment.release.submit"), "legal"),
        (call("act", "payment.refund.create"), "legal"),
        (correcting("act"), "correction"),
    ],
)
async def test_a_level_four_run_halts_where_money_would_move_and_raises_a_decision_request(
    act: Any, kind: str
) -> None:
    """UC-03 §6, the row on moving money, and §9: a level-4 process runs into the anchor and is
    halted at the step's boundary with a decision request, and nothing of the act started."""
    w = await World(
        rule("prepare"), act, rule("report"), level=4, configuration=with_decider("finance.lead")
    ).setup()
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN
    assert states(run) == {
        "prepare": StepState.SUCCEEDED,
        "act": StepState.WAITING_HUMAN,
        "report": StepState.SUCCEEDED,
    }
    assert w.connector.calls == [], "nothing of the anchored step started"
    (request_id,) = requests_of(run, "act")
    request = await w.request(request_id)
    assert request.status is DecisionStatus.OPEN and str(request.request.class_) == kind


# --- UC-03 §9: every row of §6 halts a level-4 run ---------------------------------------------


@pytest.mark.parametrize(
    ("act", "anchor"),
    [
        (call("act", "staff.contracts.create"), "anc-staff"),
        (call("act", "partnerships.agreements.end"), "anc-staff"),
        (call("act", "orchestrator.levels.raise"), "anc-limits"),
        (call("act", "orchestrator.limits.set"), "anc-limits"),
    ],
    ids=["staff", "partnerships", "own-level", "own-limit"],
)
async def test_a_level_four_run_halts_at_staff_partnerships_and_its_own_limits(
    act: Any, anchor: str
) -> None:
    """UC-03 §6, the rows on staff and partnerships and on its own limits and levels: a strategic
    anchor holds the act at every level. No connector serves these acts today; the anchor holds
    the first one a connector adds, as `payment.refund.create` stands for moving money."""
    w = await World(
        rule("prepare"), act, rule("report"), level=4, configuration=with_decider("owner")
    ).setup()
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN
    assert states(run)["act"] is StepState.WAITING_HUMAN
    assert w.connector.calls == [], "nothing of the anchored step started"
    (request_id,) = requests_of(run, "act")
    request = await w.request(request_id)
    assert request.status is DecisionStatus.OPEN and str(request.request.class_) == "strategic"
    assert anchor in json.dumps(request.model_dump(mode="json", by_alias=True))


@pytest.mark.parametrize("classified", ["date", "feature", "legal_advice"])
async def test_a_level_four_run_halts_at_a_promise(classified: str) -> None:
    """UC-03 §6, the row on promises: an outward message that promises a date, a feature or
    legal advice is held for a person (UC-7.6)."""
    h = Outward(support(), classified=classified, level=4)
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN, run.reason
    assert [d.anchor for d in h.requests.raised] == ["anc-promise"]
    assert h.sent() == []


async def test_a_level_four_run_halts_at_mass_sending() -> None:
    """UC-03 §6, the row on mass sending: more recipients than the tenant's limit wait for a
    person (UC-7.6)."""
    h = Outward(support(recipients=[f"r{n}@example.org" for n in range(11)]), level=4)
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN
    assert [d.anchor for d in h.requests.raised] == ["anc-mass-sending"]
    assert h.sent() == []


async def test_a_level_four_run_halts_at_user_data_outside_its_case() -> None:
    """UC-03 §6, the row on user data: a step that reads personal data outside a specific case
    halts for a person before anything is read (UC-7.7)."""
    h = Scoped(
        step("export", ACCOUNT, {"account": "cust-2"}),
        connector=CustomerConnector(scoped=True),
        sources=Declared(),
        level=4,
    )
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN, run.reason
    assert h.customers.calls == [], "nothing was read before a person decided"
    assert [d.anchor for d in h.requests.raised] == ["anc-personal-data"]
