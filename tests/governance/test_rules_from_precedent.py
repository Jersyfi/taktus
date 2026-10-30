"""Recurring decisions become rules on proposal (UC-7.10, ADR-0161, issue #648).

Each case runs a process through the run engine with the governance, decision and identity
components wired as the composition root wires them, answers its anchored step as a person
would, and reads back the requests, the rules, the register and the ledger.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from fakes.connector import READ, WRITE

from governance.test_anchors import (
    CORRECTION,
    DECIDER,
    TENANT,
    World,
    anchor,
    call,
    requests_of,
    rule,
)
from taktus.components.decision.application.service import UnknownRule
from taktus.components.decision.domain.model import DecisionRule, RuleStatus
from taktus.components.decision.domain.service import precedent
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.shared.v1 import AutonomyLevel, DecisionClass, DecisionStatus

ROOT = Path(__file__).resolve().parents[2]
STRATEGIC = anchor("anc-direction", "strategic", actions=[WRITE])
LEGAL = anchor("anc-legal", "legal", actions=[WRITE])
N = precedent.PRECEDENTS


def configured(*anchors: dict[str, Any]) -> dict[str, Any]:
    return {"anchors": [*anchors, CORRECTION, anchor("anc-read", "legal", actions=[READ])]}


async def world(*anchors: dict[str, Any], level: AutonomyLevel = 3, ask: bool = False) -> World:
    step, work = call("write", WRITE)
    if ask:
        work = {
            **work,
            "ask": {
                "question": "Write it?",
                "situation": "s",
                "proposal": "p",
                "role": "finance.lead",
            },
        }
    return await World(
        rule("prep"), (step, work), level=level, configuration=configured(*anchors)
    ).setup()


async def decided(w: World, *, option: str = "A", text: str | None = None) -> Run:
    """One run whose anchored step a person decides; the run as it ends."""
    run = await w.start()
    for request_id in requests_of(run, "write"):
        if text is not None:
            await w.answer(request_id, text=text)
        else:
            await w.answer(request_id, option=option)
        run = await w.confirm(request_id)
    return run


async def rules(w: World) -> list[DecisionRule]:
    return await w.decisions.rules.all(TENANT)


async def adopt(w: World, found: DecisionRule, *, option: str = "A") -> None:
    await w.answer(found.request_id, option=option)
    await w.confirm(found.request_id)


# --- what counts as consistent, and the proposal ----------------------------------------------


async def test_a_consistent_pattern_is_proposed_as_a_decision_request_naming_its_precedents() -> (
    None
):
    w = await world(STRATEGIC)
    for _ in range(N - 1):
        assert (await decided(w)).state is RunState.FINISHED
    assert await rules(w) == [], f"{N - 1} decisions are no pattern yet"
    await decided(w)
    (found,) = await rules(w)
    assert found.status is RuleStatus.PROPOSED and found.option == "A"
    assert found.kind.process == "p" and found.kind.step_id == "write"
    assert found.kind.anchor == "anc-direction"
    entries = await w.decisions.queries.entries(TENANT)
    assert found.precedents == tuple(e.id for e in entries[-N:])
    proposal = await w.request(found.request_id)
    assert proposal.status is DecisionStatus.OPEN
    assert proposal.request.class_ is DecisionClass.STRATEGIC
    assert proposal.decider == "finance.lead", "addressed to the role that decided them"
    for precedent_id in found.precedents:
        assert precedent_id in proposal.request.situation
    assert [o.id for o in proposal.request.options] == ["A", "B"]


async def test_nothing_changes_before_the_proposal_is_accepted() -> None:
    w = await world(STRATEGIC)
    for _ in range(N):
        await decided(w)
    (found,) = await rules(w)
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN, "a proposed rule answers nothing"
    assert run.step_run("write").state is StepState.WAITING_HUMAN
    (request_id,) = requests_of(run, "write")
    assert (await w.request(request_id)).status is DecisionStatus.OPEN
    assert (await rules(w))[0].status is RuleStatus.PROPOSED
    assert found.id == (await rules(w))[0].id


async def test_an_accepted_rule_answers_its_kind_and_names_itself() -> None:
    w = await world(STRATEGIC)
    for _ in range(N):
        await decided(w)
    (found,) = await rules(w)
    await adopt(w, found)
    (adopted,) = await rules(w)
    assert adopted.status is RuleStatus.ADOPTED and adopted.decided_by == DECIDER
    calls = len(w.connector.calls)

    run = await w.start()
    assert run.state is RunState.FINISHED, "nobody waited"
    assert len(w.connector.calls) == calls + 1, "the act was performed"
    (request_id,) = requests_of(run, "write")
    request = await w.request(request_id)
    assert request.status is DecisionStatus.APPLIED
    assert request.decided_by == adopted.actor and request.answered_by is None
    entry = (await w.decisions.queries.entries(TENANT))[-1]
    assert entry.request_id == request_id and entry.rule == adopted.id
    kinds = await w.kinds(run)
    assert "step.anchored:write:strategic" in kinds, "the request is still raised"
    ledger = [e for e in await w.entries(run) if e.kind == "rule.applied"]
    assert [e.refs.decision_request_id for e in ledger] == [request_id]
    assert ledger[0].refs.actor is None, "no person decided it"


async def test_a_declined_proposal_changes_nothing_and_is_not_proposed_again_at_once() -> None:
    w = await world(STRATEGIC)
    for _ in range(N):
        await decided(w)
    (found,) = await rules(w)
    await adopt(w, found, option="B")
    assert (await rules(w))[0].status is RuleStatus.DECLINED
    for _ in range(N - 1):
        await decided(w)
    assert len(await rules(w)) == 1, "the pattern starts afresh after the decline"
    assert (await w.start()).state is RunState.WAITING_HUMAN


async def test_one_decision_otherwise_or_with_a_modification_breaks_the_pattern() -> None:
    w = await world(STRATEGIC)
    for _ in range(N - 1):
        await decided(w)
    await decided(w, option="B")
    for _ in range(N - 1):
        await decided(w)
    assert await rules(w) == []
    w = await world(STRATEGIC)
    for _ in range(N - 1):
        await decided(w)
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    await w.answer(request_id, text="A, but only after noon")
    await w.confirm(request_id)
    assert await rules(w) == []


async def test_a_rule_that_declines_halts_the_run_as_a_person_s_decline_would() -> None:
    w = await world(STRATEGIC)
    for _ in range(N):
        assert (await decided(w, option="B")).cause is Cause.DECLINED
    (found,) = await rules(w)
    assert found.option == "B"
    await adopt(w, found)
    calls = len(w.connector.calls)
    run = await w.start()
    assert run.state is RunState.HALTED and run.cause is Cause.DECLINED
    assert len(w.connector.calls) == calls, "the act was not performed"


async def test_a_retired_rule_answers_nothing() -> None:
    w = await world(STRATEGIC)
    for _ in range(N):
        await decided(w)
    (found,) = await rules(w)
    await adopt(w, found)
    retired = await w.decisions.rules.retire(TENANT, found.id, DECIDER)
    assert retired.status is RuleStatus.RETIRED
    assert (await w.start()).state is RunState.WAITING_HUMAN
    with pytest.raises(UnknownRule):
        await w.decisions.rules.retire(TENANT, found.id, DECIDER)


async def test_a_rule_is_no_person_s_confirmation_at_level_two() -> None:
    w = await world(STRATEGIC, level=2)
    for _ in range(N):
        run = await w.start()
        run = await w.engine.confirm(_confirm(run, "prep"))
        (request_id,) = requests_of(run, "write")
        await w.answer(request_id, option="A")
        run = await w.confirm(request_id)
        if run.state is RunState.WAITING_HUMAN:
            run = await w.engine.confirm(_confirm(run, "write"))
    (found,) = await rules(w)
    await adopt(w, found)
    run = await w.start()
    run = await w.engine.confirm(_confirm(run, "prep"))
    assert run.state is RunState.WAITING_HUMAN
    write = run.step_run("write")
    assert write.state is StepState.WAITING_HUMAN and write.confirmed_by is None
    assert write.anchoring is not None and write.anchoring.proceeds, "the rule decided the anchor"


def _confirm(run: Run, step: str) -> Any:
    from taktus.components.run.application.service import ConfirmSteps

    return ConfirmSteps(run_id=run.id, steps=(step,), actor=DECIDER, tenant=TENANT)


# --- never a rule over an act an anchor keeps with a person -------------------------------------


@pytest.mark.parametrize("kept", ["legal", "ask"])
async def test_no_rule_is_proposed_over_an_act_an_anchor_keeps_with_a_person(kept: str) -> None:
    w = await (world(LEGAL) if kept == "legal" else world(ask=True))
    for _ in range(N + 2):
        assert (await decided(w)).state is RunState.FINISHED
    assert await rules(w) == []
    assert (await w.start()).state is RunState.WAITING_HUMAN


@pytest.mark.parametrize(
    ("class_", "anchor_id", "refused"),
    [
        (DecisionClass.LEGAL, "a", True),
        (DecisionClass.CORRECTION, "a", True),
        (DecisionClass.DOMAIN, "a", True),
        (DecisionClass.CONCEPTUAL, "a", True),
        (DecisionClass.STRATEGIC, None, True),
        (DecisionClass.STRATEGIC, "a", False),
    ],
)
def test_only_a_tenant_s_strategic_anchor_may_ever_be_answered_by_a_rule(
    class_: DecisionClass, anchor_id: str | None, refused: bool
) -> None:
    assert (precedent.refusal(class_, anchor_id) is not None) is refused


def test_the_pattern_is_found_by_count_and_no_language_model_reads_the_register() -> None:
    """The detection imports no model port and no model adapter (UC-7.10 §2)."""
    sources = [
        ROOT / "src/taktus/components/decision/domain/service/precedent.py",
        ROOT / "src/taktus/components/decision/application/service/rules.py",
    ]
    for source in sources:
        tree = ast.parse(source.read_text())
        imported = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ] + [a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names]
        forbidden = [m for m in imported if m.startswith(("taktus.ports.model", "taktus.adapters"))]
        assert forbidden == [], source


async def test_a_decision_a_rule_took_is_nobody_s_response_time() -> None:
    w = await world(STRATEGIC)
    for _ in range(N):
        await decided(w)
    (found,) = await rules(w)
    await adopt(w, found)
    await w.start()
    times = await w.decisions.queries.response_times(TENANT, DECIDER)
    assert len(times.own) == N + 1, "the precedents and the proposal; none by the rule"
