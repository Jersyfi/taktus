"""A result a person corrected is assessed by itself and raised as a result defect, and the
defect counts in the process's quality history (#92, #645, ADR-0184), over the memory stores.

The provenance records and ledger entries are `tests/governance/test_result_defects.py`'s:
five daily runs of `billing`, the partner's adapter a new version from run r3.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from fakes.clock import FakeClock
from governance.test_result_defects import AT, RECORDS, TENANT

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.components.governance.application.service import ResultDefects
from taktus.components.governance.domain.model.anchors import AnchorConfiguration
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    WatchConfiguration,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.domain.service.autonomy import history
from taktus.components.run.ports.anchors import Verdict
from taktus.composition.defects import DefectWatch, IncidentDelivery
from taktus.ports.connector import CallContext, Capabilities, Effect, EffectReport, Record, Result
from taktus.ports.ledger import Fact
from taktus.shared.v1 import Consumption, LedgerEntry, LedgerRefs


class World:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(AT + timedelta(days=6))
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.incidents = MemoryRepository(self.persistence, Incident)
        self.objects = MemoryObjectStore()
        self.watch = DefectWatch(
            self.ledger,
            ResultDefects(
                self.provenance,
                self.ledger,
                self.incidents,
                MemoryRepository(self.persistence, WatchConfiguration),
                MemoryRepository(self.persistence, AnchorConfiguration),
                self.persistence,
                self.clock,
            ),
            self.persistence,
        )

    async def ran(self) -> None:
        async with self.persistence.transaction(TENANT):
            for r in RECORDS:
                refs = LedgerRefs(
                    tenant=TENANT,
                    run_id=r.run_id,
                    step_id=r.step_id,
                    process_version=r.process_version,
                )
                if r.step_id in ("import", "report"):
                    await self.ledger.record(
                        TENANT,
                        Fact(kind="run.created", refs=refs.model_copy(update={"step_id": None})),
                    )
                await self.ledger.record(
                    TENANT, Fact(kind="step.finished", refs=refs, outcome="succeeded")
                )
                if r.step_id in ("invoice", "report"):
                    await self.ledger.record(
                        TENANT,
                        Fact(
                            kind="run.finished",
                            refs=refs.model_copy(update={"step_id": None}),
                            outcome="succeeded",
                        ),
                    )
                await self.provenance.append(TENANT, r)

    async def corrected(self, run_id: str, step_id: str, *, rehearsal: bool = False) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind="step.corrected",
                    refs=LedgerRefs(
                        tenant=TENANT,
                        run_id=run_id,
                        step_id=step_id,
                        process_version="billing@1",
                        actor="idn_corrector",
                    ),
                    rehearsal=True if rehearsal else None,
                ),
            )

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))


async def test_a_correction_is_assessed_by_itself_and_raised_once() -> None:
    w = World()
    await w.ran()
    await w.corrected("r4", "import")
    (raised,) = await w.watch.sweep(TENANT)
    async with w.persistence.transaction(TENANT):
        incident = await w.incidents.get(TENANT, raised)
    assert incident is not None and incident.kind is IncidentKind.RESULT_DEFECT
    assert incident.facts["found"] == "corrected" and incident.facts["cause"] == "adapter_version"
    assert await w.watch.sweep(TENANT) == [], "a correction answered is not raised again"
    raised_entries = [e for e in await w.entries() if e.kind == "incident.raised"]
    assert len(raised_entries) == 1 and raised_entries[0].refs.actor is None


async def test_a_rehearsal_or_a_result_without_a_record_is_not_raised() -> None:
    w = World()
    await w.ran()
    await w.corrected("r2", "import", rehearsal=True)
    await w.corrected("r9", "import")
    assert await w.watch.sweep(TENANT) == []


async def test_the_raised_defect_ends_the_clean_row_of_the_quality_history() -> None:
    """#645: a raise of the level reads the history; a run found wrong after it ended counts."""
    w = World()
    await w.ran()
    before = history(await w.entries(), "billing")
    assert (before.clean, before.last_failed) == (5, None)
    await w.corrected("r4", "import")
    await w.watch.sweep(TENANT)
    after = history(await w.entries(), "billing")
    assert (after.clean, after.ended, after.last_failed) == (1, 5, "r4")


# --- a sample judged wrong and a result marked suspect, assessed by themselves (ADR-0179 §2) -----


class Answered:
    """The verdicts of sample requests, as the decision component would give them."""

    def __init__(self, **options: str) -> None:
        self.options = options

    async def verdict(self, tenant: str, request_id: str) -> Verdict | None:
        option = self.options.get(request_id)
        return None if option is None else Verdict(applied=True, option=option)


async def sampled(w: World, run_id: str, step_id: str, request: str) -> None:
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="check.sampled",
                refs=LedgerRefs(
                    tenant=TENANT,
                    run_id=run_id,
                    step_id=step_id,
                    process_version="billing@1",
                    decision_request_id=request,
                ),
                outcome="check_1",
            ),
        )


async def test_a_sample_judged_wrong_is_raised_by_itself_and_one_judged_right_is_not() -> None:
    w = World()
    w.watch = DefectWatch(
        w.ledger, w.watch._defects, w.persistence, verdicts=Answered(req_wrong="B", req_right="A")
    )
    await w.ran()
    await sampled(w, "r4", "import", "req_wrong")
    await sampled(w, "r5", "import", "req_right")
    await sampled(w, "r3", "import", "req_open")
    (raised,) = await w.watch.sweep(TENANT)
    async with w.persistence.transaction(TENANT):
        incident = await w.incidents.get(TENANT, raised)
    assert incident is not None and incident.facts["found"] == "sampled"
    assert incident.run_id == "r4"
    assert await w.watch.sweep(TENANT) == []


async def test_a_result_marked_suspect_by_a_check_applied_again_is_raised() -> None:
    w = World()
    await w.ran()
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="check.suspect",
                refs=LedgerRefs(
                    tenant=TENANT, run_id="r5", step_id="import", process_version="billing@1"
                ),
                outcome="check_1",
            ),
        )
    (raised,) = await w.watch.sweep(TENANT)
    async with w.persistence.transaction(TENANT):
        incident = await w.incidents.get(TENANT, raised)
    assert incident is not None and incident.facts["found"] == "rechecked"


# --- the incident delivered into the tracking system (ADR-0179 §4, UC-6.8) -----------------------


class Tracker:
    """A tracking system reached through `repository.issues`: issues and their comments."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, Any]] = {}
        self.comments: list[tuple[int, str]] = []
        self.keys: dict[str, int] = {}

    async def capabilities(self) -> Capabilities:
        return Capabilities.model_validate(
            {
                "contract": "connector/v1",
                "version": "1.0.0",
                "capabilities": ["repository.issues", "repository.comments"],
                "operations": [
                    {
                        "name": "repository.issues.create",
                        "capability": "repository.issues",
                        "effect": "write",
                        "idempotency": "marked",
                        "demand": {"quota_units": 1},
                        "summary": "open an issue",
                    },
                    {
                        "name": "repository.comments.create",
                        "capability": "repository.comments",
                        "effect": "write",
                        "idempotency": "marked",
                        "demand": {"quota_units": 1},
                        "summary": "comment on an issue",
                    },
                ],
                "credentials": [{"name": "TRACKER_TOKEN", "purpose": "actions"}],
                "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
                "permissions": "passthrough",
            }
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        assert context.identity == "taktus"
        assert [c.name for c in context.credentials] == ["TRACKER_TOKEN"]
        if operation == "repository.issues.create":
            number = self.keys.setdefault(context.idempotency_key, len(self.issues) + 1)
            self.issues[number] = dict(input)
            output: dict[str, Any] = {"number": number}
        else:
            self.comments.append((int(input["number"]), str(input["body"])))
            output = {"id": len(self.comments)}
        return Result(
            output=output,
            effect=EffectReport(
                kind=Effect.WRITE, replayed=False, records=(Record(kind="issue", id="1"),)
            ),
            consumption=Consumption(quota_units=1),
        )


async def test_a_result_defect_is_delivered_once_with_its_package_and_updated_in_place() -> None:
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
    await w.ran()
    await w.corrected("r4", "import")
    (raised,) = await w.watch.sweep(TENANT)
    assert await delivery.deliver(TENANT) == [raised]
    ((number, issue),) = tracker.issues.items()
    body = issue["body"]
    for part in (
        "What happened",
        "What was tried",
        "What is affected",
        "Options and their risks",
        "Documentation and access needed",
        "Remediation plan",
    ):
        assert part in body, part
    assert "This package lacks" not in body
    assert "idn_corrector" not in body and "idn_corrector" not in issue["title"], "no person"
    assert await delivery.deliver(TENANT) == [], "delivered once"
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="remediation.started",
                refs=LedgerRefs(tenant=TENANT, incident_id=raised, run_id="run_remedy_x"),
                outcome="carried",
            ),
        )
    assert await delivery.deliver(TENANT) == [raised]
    assert len(tracker.issues) == 1, "an update goes to the same object"
    assert tracker.comments == [(number, tracker.comments[0][1])]
    assert "run_remedy_x" in tracker.comments[0][1]
    assert await delivery.deliver(TENANT) == []
    egress = [e for e in await w.entries() if e.kind == "egress.delivery"]
    assert [e.outcome for e in egress] == ["delivered", "updated"]
    assert all(e.refs.incident_id == raised and e.adapter == "tracker.issues" for e in egress)
    located = [e for e in await w.entries() if e.kind == "residency.egress"]
    assert [e.outcome for e in located] == ["elsewhere", "elsewhere"], "undeclared: elsewhere"
    assert all(e.refs.incident_id == raised and e.adapter == "tracker.issues" for e in located)


async def test_without_a_connector_for_the_tracking_system_nothing_is_delivered() -> None:
    w = World()
    delivery = IncidentDelivery(
        StaticConnectorPool([]), w.incidents, w.watch._defects, w.ledger, w.objects, w.persistence
    )
    await w.ran()
    await w.corrected("r4", "import")
    await w.watch.sweep(TENANT)
    assert await delivery.deliver(TENANT) == []
