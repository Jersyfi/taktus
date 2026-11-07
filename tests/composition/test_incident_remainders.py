"""What #92 left of a result defect's incident (ADR-0227, UC-4.12, UC-6.8): steps done by hand
recorded in it, its closure refused while a correction waits, its delivery to a tracking system
other than a repository's issues, and the report a model may write.

The world and the issue tracker are `composition.test_defect_watch`'s: five daily runs of
`billing`, a person's correction of run r4, and the defect raised from it."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from fakes.model import FakeModel
from governance.test_result_defects import TENANT

from composition.test_defect_watch import Tracker, World
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryRepository
from taktus.adapters.driven.models import StaticModelPool
from taktus.components.governance.application.service import (
    CloseIncident,
    ExpectedRuns,
    IncidentHeld,
    NotAResultDefect,
    RecordByHand,
)
from taktus.components.governance.domain.model.incident import (
    IncidentState,
    WatchConfiguration,
)
from taktus.composition.defects import (
    CorrectionRequests,
    IncidentDelivery,
    IncidentReports,
)
from taktus.ports.connector import CallContext, Capabilities, Result
from taktus.ports.ledger import Fact
from taktus.shared.v1 import DecisionClass, LedgerRefs


async def raised(w: World) -> str:
    await w.ran()
    await w.corrected("r4", "import")
    (incident,) = await w.watch.sweep(TENANT)
    return incident


def by_hand(incident: str, **given: str) -> RecordByHand:
    return RecordByHand(
        tenant=TENANT,
        incident_id=incident,
        step=given.get("step", "1"),
        role=given.get("role", "accounting"),
        done=given.get("done", "corrected the invoice in the ledger by hand"),
        by="idn_clerk",
    )


# --- steps done by hand -------------------------------------------------------------------------


async def test_a_step_done_by_hand_is_recorded_on_the_incident_with_its_role_and_time() -> None:
    w = World()
    incident = await raised(w)
    recorded = await w.watch._defects.by_hand(by_hand(incident))
    (done,) = recorded.done_by_hand
    assert (done.step, done.role) == ("1", "accounting") and done.at <= w.clock.now()
    assert "idn_clerk" not in recorded.model_dump_json(), "the incident names no person"
    (entry,) = [e for e in await w.entries() if e.kind == "incident.by_hand"]
    assert entry.refs.incident_id == incident and entry.refs.actor == "idn_clerk"
    with pytest.raises(ValueError):
        await w.watch._defects.by_hand(by_hand(incident, role="Alice Smith"))
    with pytest.raises(NotAResultDefect):
        await w.watch._defects.by_hand(by_hand("inc_unknown"))


async def test_a_step_done_by_hand_reaches_the_tracking_system_as_a_comment() -> None:
    w = World()
    tracker = Tracker()
    delivery = IncidentDelivery(
        StaticConnectorPool([("tracker.issues", tracker)]),
        w.incidents,
        w.watch._defects,
        w.ledger,
        w.objects,
        w.persistence,
    )
    incident = await raised(w)
    assert await delivery.deliver(TENANT) == [incident]
    await w.watch._defects.by_hand(by_hand(incident))
    assert await delivery.deliver(TENANT) == [incident]
    ((_, text),) = tracker.comments
    assert "Step 1 was carried out by hand in the role accounting" in text
    assert "idn_clerk" not in text


# --- the closure refused while a correction waits ----------------------------------------------


class Requests:
    """The decision component's requests, as `CorrectionRequests` reads them."""

    def __init__(self, *requests: Any) -> None:
        self.requests = requests

    async def list(self, tenant: str) -> list[Any]:
        return list(self.requests)


def request(id: str, run: str, *, open: bool = True, class_: DecisionClass) -> Any:
    return SimpleNamespace(
        id=id,
        open=open,
        request=SimpleNamespace(class_=class_, raised_by=SimpleNamespace(run=run, step="send")),
    )


async def test_an_incident_does_not_close_while_its_outward_correction_waits() -> None:
    w = World()
    incident = await raised(w)
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="remediation.started",
                refs=LedgerRefs(tenant=TENANT, incident_id=incident, run_id="run_remedy_x"),
                outcome="carried",
            ),
        )
    requests = Requests(
        request("dr_wait", "run_remedy_x", class_=DecisionClass.CORRECTION),
        request("dr_other", "run_elsewhere", class_=DecisionClass.CORRECTION),
        request("dr_legal", "run_remedy_x", class_=DecisionClass.LEGAL),
    )
    corrections = CorrectionRequests(w.ledger, requests, w.persistence)  # type: ignore[arg-type]
    watch = ExpectedRuns(
        w.incidents,
        MemoryRepository(w.persistence, WatchConfiguration),
        w.ledger._store,
        w.ledger,
        w.persistence,
        w.clock,
        corrections=corrections,
    )
    with pytest.raises(IncidentHeld) as held:
        await watch.close(CloseIncident(tenant=TENANT, incident_id=incident, by="idn_clerk"))
    assert held.value.requests == ("dr_wait",)
    requests.requests = (
        request("dr_wait", "run_remedy_x", open=False, class_=DecisionClass.CORRECTION),
    )
    closed = await watch.close(CloseIncident(tenant=TENANT, incident_id=incident, by="idn_clerk"))
    assert closed.state is IncidentState.CLOSED


# --- a tracking system of work items ----------------------------------------------------------


class Board:
    """A tracking system reached through `tasks.items`: work items and their comments."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.comments: list[tuple[str, str]] = []

    async def capabilities(self) -> Capabilities:
        declared = await Tracker().capabilities()
        document = declared.model_dump(mode="json", by_alias=True, exclude_none=True)
        document["capabilities"] = ["tasks.items", "tasks.comments"]
        document["operations"] = [
            {
                **document["operations"][0],
                "name": "tasks.items.create",
                "capability": "tasks.items",
            },
            {
                **document["operations"][1],
                "name": "tasks.comments.create",
                "capability": "tasks.comments",
            },
        ]
        return Capabilities.model_validate(document)

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        tracker = Tracker()
        if operation == "tasks.items.create":
            item = f"ITEM-{len(self.items) + 1}"
            self.items[item] = dict(input)
            done = await tracker.call("repository.issues.create", context, {"title": "t"})
            return done.model_copy(update={"output": {"id": item}})
        self.comments.append((str(input["id"]), str(input["body"])))
        return await tracker.call("repository.comments.create", context, {"number": 1, "body": ""})


async def test_without_a_repository_s_issues_the_incident_goes_to_a_board_of_work_items() -> None:
    w = World()
    board = Board()
    delivery = IncidentDelivery(
        StaticConnectorPool([("tracker.board", board)]),
        w.incidents,
        w.watch._defects,
        w.ledger,
        w.objects,
        w.persistence,
    )
    incident = await raised(w)
    assert await delivery.deliver(TENANT) == [incident]
    ((item, created),) = board.items.items()
    assert "What happened" in created["description"] and created["title"].startswith("Result")
    await w.watch._defects.by_hand(by_hand(incident))
    assert await delivery.deliver(TENANT) == [incident]
    assert [i for i, _ in board.comments] == [item], "an update goes to the same item"


# --- the report a model may write ---------------------------------------------------------------


async def test_a_model_writes_the_report_naming_what_it_narrates_and_it_is_delivered() -> None:
    w = World()
    tracker = Tracker()
    model = FakeModel(answer="The partner's import changed on r3; four results are affected.")
    reports = IncidentReports(
        StaticModelPool([("model.fake", ["incident.report"], model, "fake@1")]),
        w.incidents,
        w.watch._defects,
        w.ledger,
        w.objects,
        w.persistence,
    )
    delivery = IncidentDelivery(
        StaticConnectorPool([("tracker.issues", tracker)]),
        w.incidents,
        w.watch._defects,
        w.ledger,
        w.objects,
        w.persistence,
        reports=reports,
    )
    incident = await raised(w)
    assert await delivery.deliver(TENANT) == [incident]
    (entry,) = [e for e in await w.entries() if e.kind == "incident.reported"]
    assert entry.outcome == "free" and entry.adapter == "model.fake"
    assert "What happened" in model.prompts[0].user, "it reads the package"
    assert "idn_corrector" not in model.prompts[0].user, "it is given no person"
    assert await delivery.deliver(TENANT) == [incident]
    ((_, text),) = tracker.comments
    assert text.startswith("The partner's import changed on r3")
    assert f"This report of {incident} was written by a model (class free)" in text
    assert await reports.write(TENANT) == [], "written once"


async def test_without_a_model_for_the_report_none_is_written() -> None:
    w = World()
    reports = IncidentReports(
        StaticModelPool([]), w.incidents, w.watch._defects, w.ledger, w.objects, w.persistence
    )
    await raised(w)
    assert await reports.write(TENANT) == []
