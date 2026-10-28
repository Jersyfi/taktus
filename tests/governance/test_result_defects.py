"""A result defect, bounded, decided on by rule and planned for (UC-4.11, UC-4.12, UC-6.8,
ADR-0022, ADR-0023, ADR-0153, #92).

Table tests over provenance records and ledger entries for the analysis, the rule and the plan;
the incident through the application service over memory stores.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes.clock import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.components.governance.application.service import ReportDefect, ResultDefects
from taktus.components.governance.domain.model import ResultRef
from taktus.components.governance.domain.model.anchors import AnchorConfiguration
from taktus.components.governance.domain.model.defects import (
    SHIPPED,
    EmptiedRules,
    Facts,
    Found,
    Kind,
    Position,
    Rule,
    Verdict,
    When,
)
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    WatchConfiguration,
)
from taktus.components.governance.domain.service import defects
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import (
    ExactnessClass,
    InputKind,
    LedgerEntry,
    LedgerRefs,
    Provenance,
    ProvenanceInput,
)

AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
ZERO = "sha256:" + "0" * 64
TENANT = "t"


def digest(n: int) -> str:
    return "sha256:" + f"{n:02x}" * 32


def record(
    run: str,
    step: str,
    seq: int,
    *,
    day: int,
    version: str = "billing@1",
    model: str | None = None,
    adapter_version: str | None = None,
    exactness: str = "exact",
    reads: tuple[tuple[str, str, int], ...] = (),
    result: int,
) -> Provenance:
    return Provenance(
        id=f"prov_{run}_{step}",
        run_id=run,
        step_id=step,
        process_version=version,
        method="rule",
        exactness=exactness,
        model=model,
        adapter="connector.partner" if adapter_version else None,
        adapter_version=adapter_version,
        inputs=tuple(
            ProvenanceInput(
                kind=InputKind.RESULT,
                run_id=r,
                step_id=s,
                digest=digest(n),
                observed_at=AT + timedelta(days=day),
            )
            for r, s, n in reads
        ),
        outputs=(),
        result_digest=digest(result),
        ledger_seq=seq,
        recorded_at=AT + timedelta(days=day),
    )


def entry(seq: int, kind: str, run: str, step: str, content: int) -> LedgerEntry:
    return LedgerEntry.model_validate(
        {
            "seq": seq,
            "ts": AT,
            "kind": kind,
            "prev_hash": ZERO,
            "hash": ZERO,
            "refs": {"run_id": run, "step_id": step},
            "content_digest": digest(content),
            "adapter": "connector.mail",
        }
    )


# Five daily runs of `billing` read a partner file with step `import`. From run r3 the partner's
# adapter is a new version. Each run's `invoice` reads its `import`; `report`, a step of another
# process, reads r4's invoice and is delivered by mail.
SERIES = [
    record(f"r{n}", "import", 10 * n, day=n, adapter_version="1" if n < 3 else "2", result=n)
    for n in range(1, 6)
]
INVOICES = [
    record(f"r{n}", "invoice", 10 * n + 1, day=n, reads=((f"r{n}", "import", n),), result=50 + n)
    for n in range(1, 6)
]
REPORT = record(
    "q1",
    "report",
    61,
    day=5,
    version="month@1",
    exactness="sourced",
    reads=(("r4", "invoice", 54),),
    result=90,
)
RECORDS = [*SERIES, *INVOICES, REPORT]
DELIVERED = entry(70, "egress.delivery", "q1", "report", 90)


def analysis(found: Found = Found.CORRECTED, records: list[Provenance] | None = None) -> Any:
    defect = ResultRef(run_id="r4", step_id="import", digest=digest(4))
    return defects.analyse(defect, found, records or RECORDS, [DELIVERED])


# --- UC-4.11: since when, what is affected, what was built on it, what has left -----------------


def test_the_window_starts_after_the_change_and_ends_at_the_newest_result() -> None:
    found = analysis()
    assert found.cause is not None
    assert (found.cause.field, found.cause.before, found.cause.after) == (
        "adapter_version",
        "1",
        "2",
    )
    assert found.cause.at_run == "r3"
    assert not found.unbounded
    assert found.window_start == AT + timedelta(days=3)
    assert found.window_end == AT + timedelta(days=5)
    assert found.window_runs == 3
    own = [a for a in found.affected if a.result.step_id == "import"]
    assert [a.result.run_id for a in own] == ["r3", "r4", "r5"]
    assert [a.position for a in own] == [Position.FIRST, Position.INSIDE, Position.LAST]


def test_every_derived_result_across_two_processes_is_listed_with_its_class() -> None:
    found = analysis()
    derived = {(a.result.run_id, a.result.step_id): a for a in found.affected}
    assert ("r3", "invoice") in derived and ("r5", "invoice") in derived
    assert ("r1", "invoice") not in derived  # before the window
    report = derived[("q1", "report")]
    assert report.process_version == "month@1"
    assert report.exactness is ExactnessClass.SOURCED
    assert report.position is Position.DERIVED
    assert derived[("r4", "invoice")].readers == ("month@1/report",)


def test_a_result_delivered_through_a_channel_is_marked_as_having_left() -> None:
    found = analysis()
    left = {(a.result.run_id, a.result.step_id) for a in found.left}
    assert left == {("r4", "import"), ("r4", "invoice"), ("q1", "report")}
    (report,) = [a for a in found.affected if a.result.step_id == "report"]
    assert report.left is not None and report.left.kind == "egress.delivery"


def test_a_window_without_a_found_cause_says_so_and_is_unbounded_at_the_first_record() -> None:
    steady = [
        record(f"r{n}", "import", 10 * n, day=n, adapter_version="1", result=n) for n in range(1, 6)
    ]
    found = analysis(records=steady)
    assert found.cause is None
    assert found.unbounded
    assert found.window_start == AT + timedelta(days=1)


def test_a_result_older_than_the_chain_is_not_reconstructed() -> None:
    with pytest.raises(defects.NotRecorded):
        defects.analyse(ResultRef(run_id="r0", step_id="import"), Found.CORRECTED, RECORDS, [])


def test_the_analysis_changes_nothing() -> None:
    before = [r.model_dump() for r in RECORDS]
    analysis()
    assert [r.model_dump() for r in RECORDS] == before


# --- ADR-0023: the rule decides, with the facts and the thresholds -------------------------------


def facts(**given: Any) -> Facts:
    base: dict[str, Any] = {
        "strictest": ExactnessClass.TOLERANT,
        "left": False,
        "legal_downstream": False,
        "window_runs": 1,
        "window": timedelta(hours=1),
    }
    return Facts.model_validate({**base, **given})


@pytest.mark.parametrize(
    ("given", "verdict", "fired"),
    [
        ({}, Verdict.CONTINUE, ()),
        ({"strictest": ExactnessClass.EXACT}, Verdict.ESCALATE, ("exact-or-sourced",)),
        ({"strictest": ExactnessClass.SOURCED}, Verdict.ESCALATE, ("exact-or-sourced",)),
        ({"window": timedelta(days=8)}, Verdict.ESCALATE, ("window-over-a-week",)),
        ({"left": True}, Verdict.ESCALATE, ("anything-left",)),
        (
            {"strictest": ExactnessClass.EXACT, "left": True, "legal_downstream": True},
            Verdict.STOP,
            ("exact-left-under-a-legal-anchor", "exact-or-sourced", "anything-left"),
        ),
    ],
)
def test_each_criterion_on_its_own_triggers_what_the_shipped_rule_says(
    given: dict[str, Any], verdict: Verdict, fired: tuple[str, ...]
) -> None:
    decided = defects.decide(facts(**given), SHIPPED)
    assert decided.verdict is verdict
    assert decided.fired == fired
    assert set(decided.thresholds) == set(fired)


def test_the_same_facts_give_the_same_decision() -> None:
    given = facts(strictest=ExactnessClass.EXACT, left=True)
    assert defects.decide(given, SHIPPED) == defects.decide(given, SHIPPED)


def test_a_criterion_may_be_added_and_a_threshold_changed() -> None:
    relevant = Rule(id="relevant", when=When(relevance_at_least=4), then=Verdict.STOP)
    shorter = Rule(id="window", when=When(window_over=timedelta(hours=2)), then=Verdict.ESCALATE)
    rules = (relevant, shorter)
    assert defects.decide(facts(window=timedelta(hours=3)), rules).verdict is Verdict.ESCALATE
    assert defects.decide(facts(relevance=5), rules).verdict is Verdict.STOP
    assert defects.decide(facts(relevance=2), rules).verdict is Verdict.CONTINUE


def test_a_configuration_that_empties_the_set_is_refused() -> None:
    quiet = Rule(id="quiet", when=When(left=False), then=Verdict.CONTINUE)
    with pytest.raises(EmptiedRules):
        WatchConfiguration(id=TENANT, tenant=TENANT, defect_rules=(quiet,))
    with pytest.raises(EmptiedRules):
        WatchConfiguration(id=TENANT, tenant=TENANT, defect_rules=())
    stop_turned_escalate = tuple(
        r.model_copy(update={"then": Verdict.ESCALATE}) if r.then is Verdict.STOP else r
        for r in SHIPPED
    )
    assert WatchConfiguration(id=TENANT, tenant=TENANT, defect_rules=stop_turned_escalate)


# --- UC-4.12: the plan, executable by hand, with every outward correction under the anchor -------


def test_a_plan_for_results_inside_the_system_runs_without_a_halt() -> None:
    inside = defects.analyse(
        ResultRef(run_id="r4", step_id="import", digest=digest(4)), Found.CORRECTED, RECORDS, []
    )
    planned = defects.plan(inside)
    assert planned.runs_unattended
    assert all(s.kind is Kind.INSIDE for s in planned.steps)


def test_every_result_that_left_gets_an_outward_correction_after_it_is_produced_again() -> None:
    planned = defects.plan(analysis(), {70: "the mail system"})
    outward = planned.outward
    assert len(outward) == 3
    for step in outward:
        (produced,) = step.after_steps
        assert planned.steps[produced - 1].kind is Kind.INSIDE
        assert step.order > produced
        assert step.system == "the mail system"
    assert not planned.runs_unattended


def test_every_plan_step_says_what_a_person_needs_to_carry_it_out_without_taktus() -> None:
    planned = defects.plan(analysis(), {70: "the mail system"})
    text = defects.render(planned)
    for step in planned.steps:
        for part in (step.system, step.record, step.before, step.after, step.done_when):
            assert part and part in text
        assert f"## {step.order}." in text
    assert "dr_" not in text and "prov_" not in text  # nothing a person could not look up


def test_a_correction_that_cannot_be_made_at_once_says_so() -> None:
    planned = defects.plan(analysis(), {70: "the mail system"})
    delivered = [s for s in planned.outward if not s.atomic]
    assert delivered
    assert all("holds two" in (s.note or "") for s in delivered)
    assert "Not at once:" in defects.render(planned)


# --- UC-6.8: the incident, raised once, naming no person ------------------------------------------


async def test_a_reported_result_raises_one_incident_with_what_the_rule_read() -> None:
    persistence = MemoryPersistence()
    clock = FakeClock(AT + timedelta(days=6))
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    provenance = MemoryProvenanceStore(persistence)
    async with persistence.transaction(TENANT):
        for r in RECORDS:
            await ledger.record(
                TENANT,
                Fact(
                    kind="step.finished",
                    refs=LedgerRefs(tenant=TENANT, run_id=r.run_id, step_id=r.step_id),
                    outcome="succeeded",
                ),
            )
            await provenance.append(TENANT, r)
    service = ResultDefects(
        provenance,
        ledger,
        MemoryRepository(persistence, Incident),
        MemoryRepository(persistence, WatchConfiguration),
        MemoryRepository(persistence, AnchorConfiguration),
        persistence,
        clock,
    )
    report = ReportDefect(tenant=TENANT, run_id="r4", step_id="import", found=Found.CORRECTED)
    incident, assessed = await service.raise_incident(report)
    assert incident.kind is IncidentKind.RESULT_DEFECT
    assert incident.facts["verdict"] == "escalate" == assessed.decision.verdict.value
    assert incident.facts["strictest"] == "exact"
    assert incident.facts["cause"] == "adapter_version"
    assert incident.rule == "exact-or-sourced"
    again, _ = await service.raise_incident(report)
    assert again.id == incident.id
    async with persistence.transaction(TENANT):
        raised = [e for e in await ledger.entries(TENANT) if e.kind == "incident.raised"]
    assert [e.outcome for e in raised] == ["escalate"]
    assert all(e.refs.actor is None for e in raised)
    assert "idn_" not in str(incident.model_dump())
