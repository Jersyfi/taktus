"""A result built on a wrong one in another run is produced again by the engine (#92,
ADR-0227 §1, UC-4.12).

The world is `governance.test_remediation_run`'s: a run books a value and posts what is built on
it. A second run posted a result the analysis finds derived from the wrong one. Once the wrong
run's own remediation finished, the derived run is remedied too: the steps that produced the
derived results run again with everything built on them, every other done step is carried, and
it starts once."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fakes import FakeIdentifiers

from governance.test_anchors import AT, STARTER, TENANT, World, rule
from governance.test_remediation_run import derive
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.governance.domain.model.egress import ResultRef
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.run.application.service import (
    CorrectResult,
    CorrectResultHandler,
    ResumeRun,
)
from taktus.components.run.domain.model import RunState
from taktus.composition.defects import Remedies, remedy_id
from taktus.shared.v1 import Command, Plan


async def ran(w: World, run: Any) -> Any:
    """A submitted run, claimed from the queue and resumed, as a runner does."""
    async with w.persistence.transaction(TENANT):
        await w.queue.claim(TENANT, "runner-a", 5)
    return await w.engine.resume(
        ResumeRun(run_id=run.id, actor="runner-a", tenant=TENANT, on_claim=True)
    )


class Assessed:
    """The analysis as `ResultDefects.assess` gives it: what is affected, by run and step."""

    def __init__(self, *affected: tuple[str, str]) -> None:
        self.affected = affected

    async def assess(self, command: Any) -> Any:
        return SimpleNamespace(
            analysis=SimpleNamespace(
                affected=[
                    SimpleNamespace(result=ResultRef(run_id=run, step_id=step))
                    for run, step in self.affected
                ]
            )
        )


async def test_a_run_built_on_the_wrong_result_runs_again_after_the_wrong_run_s_remedy() -> None:
    w = await World(rule("book"), derive("post", "book"), level=4).setup()
    wrong = await w.start()
    other = await w.start()
    assert wrong.id != other.id and other.state is RunState.FINISHED
    await CorrectResultHandler(w.runs, w.persistence, w.engine._objects, w.ledger).execute(
        CorrectResult(tenant=TENANT, run_id=wrong.id, step_id="book", value=2, actor=STARTER)
    )
    incidents = MemoryRepository(w.persistence, Incident)
    async with w.persistence.transaction(TENANT):
        await incidents.put(
            TENANT,
            Incident(
                id="inc_1",
                tenant=TENANT,
                kind=IncidentKind.RESULT_DEFECT,
                process_id="p",
                process_version="p@1",
                run_id=wrong.id,
                rule="exact-or-sourced",
                facts={"step": "book", "found": "corrected", "verdict": "escalate"},
                raised_at=AT,
            ),
        )
    remedies = Remedies(
        w.engine,
        w.runs,
        incidents,
        CommissionPlanHandler(
            MemoryRepository(w.persistence, Command),
            MemoryRepository(w.persistence, Plan),
            w.persistence,
            w.clock,
            FakeIdentifiers(),
        ),
        w.ledger,
        w.persistence,
        w.clock,
        FakeIdentifiers(),
        defects=Assessed((wrong.id, "book"), (wrong.id, "post"), (other.id, "post")),  # type: ignore[arg-type]
    )
    assert await remedies.follow(TENANT) == [], "nothing follows before the wrong run's remedy"
    primary = await ran(w, await remedies.start(TENANT, "inc_1"))
    assert primary.state is RunState.FINISHED
    (submitted,) = await remedies.follow(TENANT)
    derived = await ran(w, submitted)
    assert derived.id == remedy_id(TENANT, "inc_1", other.id)
    assert derived.remedy is not None and derived.remedy.run_id == other.id
    assert derived.remedy.step_id == "post"
    assert derived.state is RunState.FINISHED
    async with w.persistence.transaction(TENANT):
        records = await w.engine._provenance.of_run(TENANT, derived.id)
        started = await w.ledger.of_kinds(TENANT, ("remediation.started",))
    assert {r.step_id for r in records} == {"post"}, "book carried, post produced again"
    assert [e.outcome for e in started] == ["carried", "derived"]
    assert all(e.refs.incident_id == "inc_1" for e in started)
    assert await remedies.follow(TENANT) == [], "it starts once"
