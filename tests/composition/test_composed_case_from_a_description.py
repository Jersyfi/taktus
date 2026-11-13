"""A composed case worked out in the plan dialogue, from a description to a registered process
version, without a line of code (UC-12.3 §2, ADR-0290, UC-1.2, UC-4.1).

What is real: the plan dialogue and its acts, the describe process S-08 as shipped, the run
engine and its queue, the process component's proposals and registration, the value ledger.
What is faked: the language model, which answers the bundle its script holds, and the connector
the case reaches.

What is proven: a person describes an onboarding assistant for new staff, one of the use case's
examples, in a plan draft; commissioning the plan hands the description to the describe
process, whose run keeps a proposal; the proposal is rehearsed and commissioned by the person,
and only then is the process registered. The composed case then runs as any process does: its
run is in the ledger, counted by the value balance, and runs at the level its autonomy statement
sets, with its reason.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes.connector import READ, WRITE
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import PlanDialogue, PlanningError
from taktus.components.command.domain.model import PlanDraft
from taktus.components.run.domain.model import DemandToAccept, RunState
from taktus.components.value.application.query import ValueLedger
from taktus.components.value.domain.service import figures as value
from taktus.composition.planning import PlanActs
from taktus.shared.v1 import Command, Plan, PlanResult

from .test_process_from_a_description import TENANT, WHO, World

DESCRIPTION = (
    "an onboarding assistant for new staff: read the newcomer's record, then create their "
    "first-week checklist"
)
S08 = "s08-process-from-a-description@2"


def onboarding() -> dict[str, Any]:
    """The bundle the model answers for DESCRIPTION: two rule steps, by capability."""
    return instructed(
        {
            "id": "onboarding",
            "version": "1",
            "name": "Onboarding",
            "autonomy": {
                "level": 3,
                "reason": "reading a record and creating a checklist are reversible acts",
                "toward_next": "a hundred runs without a correction",
            },
            "limits": {"quota": {"units": 6}},
            "inputs": {"record": {"description": "the newcomer's record", "example": "r1"}},
            "steps": [
                {
                    "id": "read",
                    "method": "rule",
                    "reason": "the record is read as it is stored",
                    "rejected": [{"method": "llm", "why": "a record is read, not judged"}],
                    "exactness": "tolerant",
                    "work": {
                        "rule": "connector",
                        "operation": READ,
                        "input": {"id": {"$input": "record"}},
                    },
                },
                {
                    "id": "create",
                    "method": "rule",
                    "reason": "the checklist is created with the record's identifier",
                    "rejected": [{"method": "llm", "why": "the fields are fixed"}],
                    "exactness": "tolerant",
                    "depends_on": ["read"],
                    "work": {
                        "rule": "connector",
                        "operation": WRITE,
                        "input": {"follows": {"$from": "read", "$select": "output.id"}},
                    },
                },
            ],
        }
    )


def planning(world: World, *, describing: bool = True) -> PlanActs:
    drafts = MemoryRepository(world.persistence, PlanDraft)
    commands = MemoryRepository(world.persistence, Command)
    dialogue = PlanDialogue(
        commands,
        drafts,
        MemoryRepository(world.persistence, Plan),
        world.ledger,
        world.persistence,
        world.clock,
        world.ids,
    )
    return PlanActs(
        dialogue,
        drafts,
        commands,
        world.versions,
        world.persistence,
        world.clock,
        world.ids,
        describe=world.acts if describing else None,
    )


async def worked_out(plans: PlanActs) -> PlanDraft:
    """The draft as a person works it out in the expert mode: the description is the goal, the
    describe process does it, a date, a level and its reason, an estimate for each step."""
    draft = await plans.open(TENANT, WHO, (TENANT, "ops"), DESCRIPTION, describes="onboarding")
    assert draft.results_in is PlanResult.PROCESS_VERSION
    chosen = await plans.set(TENANT, WHO, draft.id, {"steps": {"process_version": S08}})
    return await plans.set(
        TENANT,
        WHO,
        draft.id,
        {
            "due": "2026-12-01",
            "autonomy_level": 2,
            "autonomy_reason": "a person commissions what the description becomes",
            "estimates": [
                {"step_id": s.id, "figure": 30, "basis": "the describe process's last runs"}
                for s in chosen.steps
            ],
        },
    )


async def test_a_case_is_described_in_the_plan_dialogue_registered_and_runs_like_any_process() -> (
    None
):
    world = await World(json.dumps(onboarding())).setup()
    await world.seeded()
    plans = planning(world)
    draft = await worked_out(plans)
    assert draft.missing() == () and draft.unestimable() == ()

    plan, described = await plans.commission_and_start(TENANT, WHO, draft.id)
    assert plan.results_in is PlanResult.PROCESS_VERSION and described is not None
    assert described.process_version == S08
    assert (await world.run_through(described.id)).state is RunState.FINISHED
    (proposal,) = await world.proposals.of_process(TENANT, "onboarding")
    assert proposal.request == DESCRIPTION and proposal.requested_by == WHO
    assert not await world.exists("onboarding"), "commissioning the plan registers nothing"

    _, rehearsal = await world.acts.rehearse(TENANT, "onboarding", proposal.id, WHO)
    assert (await world.run_through(rehearsal.id)).state is RunState.FINISHED
    version = await world.acts.commission(TENANT, "onboarding", proposal.id, WHO)
    assert version.ref == "onboarding@1" and await world.exists("onboarding")

    # The composed case runs as any process version does.
    started = await world.acts._started(
        TENANT,
        "onboarding",
        "TAKTUS_ONBOARDING",
        {"record": "r7"},
        "onboard the newcomer r7",
        WHO,
        recognised="process.run",
        goal="onboard the newcomer r7",
        instead="",
    )
    run = await world.run_through(started.id)
    assert run.state is RunState.FINISHED, run
    assert run.autonomy_level == version.autonomy.level == 3
    assert version.autonomy.reason and version.autonomy.toward_next
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    mine = [e for e in entries if e.refs.run_id == run.id]
    assert {"run.created", "run.finished"} <= {e.kind for e in mine}
    assert all(e.refs.process_version == "onboarding@1" for e in mine)

    activity = await ValueLedger(world.ledger, world.persistence).activity(TENANT)
    facts = value.Facts(
        tenant=TENANT,
        since=datetime(2026, 11, 1, tzinfo=UTC),
        until=datetime(2026, 11, 8, tzinfo=UTC),
        processes=(
            value.ProcessFacts(
                process="onboarding",
                version=version.ref,
                level=version.autonomy.level,
                methods=tuple(s.method.value for s in version.steps),
                instructions=version.takeover is not None,
            ),
        ),
    )
    figures = {f.id: f for f in value.process_figures(facts, activity)}
    assert figures["value.runs_ended"].value == 1, "its run is counted by the value balance"
    assert figures["value.balance"].withheld is not None, "no basis stated: withheld, never 0"


async def test_a_plan_that_describes_a_process_is_refused_where_no_describe_process_is_named() -> (
    None
):
    world = await World(json.dumps(onboarding())).setup()
    plans = planning(world, describing=False)
    draft = await worked_out(plans)
    with pytest.raises(PlanningError, match="TAKTUS_DESCRIBE_PROCESS"):
        await plans.commission(TENANT, WHO, draft.id)
    assert not (await plans.get(TENANT, WHO, draft.id)).is_commissioned, "nothing is written"


async def test_a_describe_run_that_needs_much_shows_its_demand_before_it_is_commissioned() -> None:
    """UC-8.10 §2, ADR-0299 §1: commissioning in the plan dialogue starts the describe run; where
    it needs much, the commissioning is refused with its demand, nothing is commissioned, and
    the person's acceptance commissions it."""
    world = await World(json.dumps(onboarding())).setup()
    await world.seeded()
    plans = planning(world)
    draft = await worked_out(plans)

    async def much(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "much": True,
            "estimate": {"tokens": 90000.0},
            "basis": "the run's budget",
            "share": 0.5,
            "limits": [{"limit": "ops_month", "unit": "ops", "reaches": ["tokens"]}],
        }

    world.acts._engine.demand = much  # type: ignore[method-assign]
    with pytest.raises(DemandToAccept) as refused:
        await plans.commission_and_start(TENANT, WHO, draft.id)
    assert refused.value.shown["limits"][0]["limit"] == "ops_month"
    assert (await plans.get(TENANT, WHO, draft.id)).commissioned_version is None
    plan, described = await plans.commission_and_start(TENANT, WHO, draft.id, accept_demand=True)
    assert described is not None and plan.results_in is PlanResult.PROCESS_VERSION
