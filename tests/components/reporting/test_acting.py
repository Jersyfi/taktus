"""What acts for a tenant and what depends on it, drawn from facts (UC-7.8, UC-6.16, ADR-0147).

The register puts the rows that need attention first, each with its reasons; the inventory says
it is not legally reviewed; removing an adapter splits what breaks from what degrades; a wrong
result is followed forward and every egress is marked; and what each adapter used is a
projection that equals the full computation. No row names a person."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from taktus.components.reporting.domain.model.acting import (
    ActorFacts,
    ActorUse,
    RemovalSeen,
    Used,
)
from taktus.components.reporting.domain.service import acting
from taktus.shared.v1 import (
    Consumption,
    ExactnessClass,
    LedgerEntry,
    LedgerRefs,
    Method,
    Provenance,
)

AT = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
NONE_USED = Used(days=28)


def use(
    process: str, step: str, *, level: int = 2, breaks: bool = False, **more: object
) -> ActorUse:
    return ActorUse(
        process_id=process,
        version="1",
        step_id=step,
        served="tickets.read",
        level=level,
        exactness=more.get("exactness", ExactnessClass.TOLERANT),  # type: ignore[arg-type]
        without="breaks" if breaks else "degrades",
        instead=None if breaks else "connector.other",
        role=more.get("role"),  # type: ignore[arg-type]
        reason="r",
    )


def facts(adapter: str, *uses: ActorUse, **more: object) -> ActorFacts:
    return ActorFacts.model_validate(
        {
            "adapter": adapter,
            "family": adapter.split(".", 1)[0],
            "serves": ["tickets.read"],
            "maturity": "verified",
            "uses": [u.document() for u in uses],
            "used": NONE_USED.document(),
            **more,
        }
    )


TESTED = RemovalSeen(verdict="changed", tested_at=AT)


def test_the_register_puts_what_needs_attention_first_each_with_its_reasons() -> None:
    register = acting.register(
        "t",
        [
            facts("connector.calm", use("support", "read"), removal=TESTED.document()),
            facts(
                "connector.only", use("billing", "fetch", breaks=True), removal=TESTED.document()
            ),
            facts("model.abroad", location="elsewhere", removal=TESTED.document()),
            facts("worker.untested", use("support", "code")),
        ],
        "eu",
    )
    order = [r.adapter for r in register.rows]
    assert order[-1] == "connector.calm" and not register.rows[-1].attention
    by = {r.adapter: r for r in register.rows}
    assert "without it 1 process would break: billing" in by["connector.only"].attention
    assert by["model.abroad"].residency == "outside"
    assert any("outside the tenant's residency rule" in a for a in by["model.abroad"].attention)
    assert "processes use it and it was never removal-tested" in by["worker.untested"].attention
    assert register.summary == "4 adapters can act for this tenant; 3 need attention."


def test_a_row_says_how_far_it_acts_and_flags_a_level_above_2_on_an_unverified_adapter() -> None:
    row = acting.row(
        facts(
            "worker.coder",
            use("dev", "code", level=3, exactness=ExactnessClass.SOURCED),
            use("dev", "review", level=1, exactness=ExactnessClass.FREE),
            maturity="experimental",
            removal=TESTED.document(),
        ),
        "anywhere",
    )
    assert row.level == 3 and row.exactness is ExactnessClass.SOURCED
    assert row.residency == "undeclared"
    assert row.attention == ("a step runs on it at level 3 while it is experimental",)
    assert "acts in 1 process up to level 3, producing sourced results at most" in row.text


def test_a_held_stop_is_shown_first_among_the_reasons() -> None:
    row = acting.row(facts("worker.coder", stopped=True, removal=TESTED.document()), "anywhere")
    assert row.stopped and row.attention[0] == "a stop of it is held"


def test_the_inventory_is_generated_and_marked_not_legally_reviewed() -> None:
    register = acting.register(
        "t", [facts("model.writer", use("support", "draft", role="support-lead"))], "eu"
    )
    document = acting.inventory(register, AT)
    assert document["legally_reviewed"] is False
    assert "Not legally reviewed" in document["notice"]
    (system,) = document["systems"]
    assert system["human_oversight"]["roles_taking_over"] == ["support-lead"]
    assert system["purpose"]["processes"] == ["support"]


def test_removing_an_adapter_splits_what_breaks_from_what_degrades() -> None:
    view = acting.remove_view(
        "connector.tickets",
        facts(
            "connector.tickets",
            use("billing", "fetch", breaks=True),
            use("support", "read"),
            removal=TESTED.document(),
        ),
    )
    assert [u.process_id for u in view.breaks] == ["billing"]
    assert [u.process_id for u in view.degrades] == ["support"]
    assert view.summary == (
        "Without connector.tickets: 1 process would break (billing); "
        "1 process would only degrade (support)."
    )
    assert view.removal == TESTED
    gone = acting.remove_view("connector.nothing", None)
    assert not gone.configured and "not configured" in gone.summary


def provenance(id: str, run: str, step: str, seq: int, *reads: tuple[str, str]) -> Provenance:
    return Provenance.model_validate(
        {
            "id": id,
            "run_id": run,
            "step_id": step,
            "process_version": f"{run.split('-')[0]}@1",
            "method": "rule",
            "exactness": "sourced",
            "inputs": [
                {
                    "kind": "result",
                    "run_id": r,
                    "step_id": s,
                    "digest": "sha256:" + "a" * 64,
                    "observed_at": AT,
                }
                for r, s in reads
            ],
            "outputs": [],
            "result_digest": "sha256:" + "b" * 64,
            "ledger_seq": seq,
            "recorded_at": AT,
        }
    )


def entry(kind: str, seq: int, run: str, step: str | None = None, **more: object) -> LedgerEntry:
    return LedgerEntry.model_validate(
        {
            "seq": seq,
            "ts": more.pop("ts", AT),
            "kind": kind,
            "prev_hash": None if seq == 1 else "sha256:" + "0" * 64,
            "hash": "sha256:" + "1" * 64,
            "refs": LedgerRefs(
                tenant="t", run_id=run, step_id=step, process_version="p@1"
            ).document(),
            **more,
        }
    )


def test_a_wrong_result_is_followed_forward_and_every_egress_is_marked() -> None:
    own = provenance("p0", "bill-1", "compute", 1)
    reached = [
        provenance("p1", "bill-1", "invoice", 2, ("bill-1", "compute")),
        provenance("p2", "remind-7", "letter", 3, ("bill-1", "invoice")),
    ]
    egress = [
        entry("egress.write", 4, "bill-1", "invoice"),
        entry("egress.delivery", 5, "remind-7", "letter"),
        entry("step.finished", 6, "remind-7", "letter"),
    ]
    view = acting.wrong_result("bill-1", "compute", own, reached, egress)
    assert [(r.run_id, r.step_id, r.left) for r in view.reached] == [
        ("bill-1", "invoice", ("egress.write",)),
        ("remind-7", "letter", ("egress.delivery",)),
    ]
    assert view.affected == 3 and view.left == 2 and view.left_itself == ()
    assert view.built_on == {"bill@1": 1, "remind@1": 1}
    assert "does not compute" in view.since_when


def test_where_data_goes_is_held_against_the_rule() -> None:
    view = acting.residency_view(
        [
            facts("model.own", location="own"),
            facts("model.abroad", location="elsewhere"),
            facts("connector.tickets"),
        ],
        "eu",
    )
    by = {r.adapter: r.residency for r in view.rows}
    assert by == {
        "model.own": "inside",
        "model.abroad": "outside",
        "connector.tickets": "undeclared",
    }
    assert "Outside it: model.abroad" in view.summary


def finished(seq: int, run: str, adapter: str, day: int, **used: object) -> LedgerEntry:
    return entry(
        "step.finished",
        seq,
        run,
        "s",
        ts=AT + timedelta(days=day),
        adapter=adapter,
        method=str(Method.LLM),
        consumption=Consumption.model_validate(used).document() if used else None,
    )


def test_what_an_adapter_used_is_a_projection_that_equals_the_full_computation() -> None:
    entries = [
        finished(1, "r1", "model.writer", 0, tokens_in=100, tokens_out=20, currency={"eur": 0.5}),
        finished(2, "r1", "model.writer", 0, tokens_in=10, tokens_out=0),
        finished(3, "r2", "model.writer", 40, tokens_in=1, tokens_out=1),
        finished(4, "r2", "worker.coder", 40, compute_seconds=12.5, resource_class="cpu"),
    ]
    whole = acting.every_use(entries)
    folded = acting.USED.load(acting.USED.dump(acting.USED.empty()))
    for e in entries[:2]:
        folded = acting.USED.fold(folded, e)
    folded = acting.USED.load(acting.USED.dump(folded))
    for e in entries[2:]:
        folded = acting.USED.fold(folded, e)
    assert folded.days == whole.days
    since = (AT + timedelta(days=40 - 27)).date()
    assert whole.used("model.writer", since) == Used(days=28, steps=1, runs=1, tokens=2)
    assert whole.used("worker.coder", since).compute_seconds == 12.5
    early = acting.every_use(entries[:2]).used("model.writer", date(2026, 10, 1))
    assert early.tokens == 130 and early.money == {"eur": 0.5} and early.runs == 1
