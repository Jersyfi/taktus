"""How a process really runs (UC-9.7, ADR-0147 §4): its variants from a projection of the ledger
that equals the full computation, its waiting by cause, a role's figure only where two hold
it, and proposals a person decides. A rehearsal is no run of the work."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from taktus.components.reporting.domain.service import variants as v
from taktus.shared.v1 import LedgerEntry, LedgerRefs

AT = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
DESIGNED = ("classify", "approve", "book")


def entry(seq: int, kind: str, run: str, step: str | None = None, **more: Any) -> LedgerEntry:
    return LedgerEntry.model_validate(
        {
            "seq": seq,
            "ts": AT,
            "kind": kind,
            "prev_hash": None if seq == 1 else "sha256:" + "0" * 64,
            "hash": "sha256:" + "1" * 64,
            "refs": LedgerRefs(
                tenant="t", run_id=run, step_id=step, process_version=more.pop("pv", "pay@1")
            ).document(),
            **more,
        }
    )


def history(runs: int, fell_back: int, retried: int) -> list[LedgerEntry]:
    """`runs` runs of pay@1: the first `fell_back` fell back at classify, the next `retried`
    retried book, one escalated after its retry; one rehearsal and one of another process."""
    entries: list[LedgerEntry] = []
    seq = 0

    def add(kind: str, run: str, step: str | None = None, **more: Any) -> None:
        nonlocal seq
        seq += 1
        entries.append(entry(seq, kind, run, step, **more))

    for i in range(runs):
        run = f"run-{i:02d}"
        add("step.admitted", run, "classify")
        if i < fell_back:
            add("step.awaiting", run, "classify", outcome=v.FELL_BACK)
        elif i < fell_back + retried:
            add("step.retried", run, "book", outcome="after_failure")
        if i == fell_back + retried:
            add("step.retried", run, "book", outcome="after_failure")
            add("run.escalated", run)
        else:
            add("run.finished", run)
    add("step.awaiting", "rehearsal-1", "classify", outcome=v.FELL_BACK, rehearsal=True)
    add("run.finished", "rehearsal-1", rehearsal=True)
    add("run.finished", "other-1", pv="payroll@1")
    add("step.admitted", "in-flight", "classify")
    return entries


def test_the_projection_equals_the_full_computation_and_reads_only_its_kinds() -> None:
    entries = history(12, 3, 2)
    whole = v.travelled(entries)
    state = v.VARIANTS.empty()
    for e in entries[:10]:
        state = v.VARIANTS.fold(state, e)
    state = v.VARIANTS.load(v.VARIANTS.dump(state))
    for e in entries[10:]:
        state = v.VARIANTS.fold(state, e)
    assert state.runs == whole.runs
    assert "step.admitted" not in v.VARIANTS.kinds  # type: ignore[operator]


def test_variants_are_ranked_with_their_share_and_the_designed_path_is_named() -> None:
    view = v.variants("pay", "1", DESIGNED, v.travelled(history(12, 3, 2)), [], {}, {})
    assert view.runs == 12, "the rehearsal, the other process and the run in flight are not runs"
    texts = [variant.text for variant in view.variants]
    assert texts == [
        "The designed path: 6 of 12 runs (50 %).",
        "Fell back to a person at classify: 3 of 12 runs (25 %).",
        "Retried book: 2 of 12 runs (17 %).",
        "Retried book; ended escalated: 1 of 12 runs (8 %).",
    ]
    assert view.on_designed_path == 0.5 and view.variants[0].designed
    assert view.variants[1].examples == ("run-00", "run-01", "run-02")
    assert view.summary == "12 runs ended in 4 variants; 50 % took the designed path."


def test_a_frequent_fallback_to_a_person_is_proposed_for_a_method_change() -> None:
    view = v.variants("pay", "1", DESIGNED, v.travelled(history(12, 3, 2)), [], {}, {})
    (proposal,) = view.proposals
    assert proposal.kind == "method" and proposal.step_id == "classify"
    assert proposal.evidence == "3 of 12 runs fell back to a person at classify"
    too_few = v.variants("pay", "1", DESIGNED, v.travelled(history(9, 3, 0)), [], {}, {})
    assert too_few.proposals == (), "fewer than ten runs propose nothing"


def wait(step: str, account: str, seconds: float, role: str | None = None) -> v.WaitFact:
    return v.WaitFact(step_id=step, account=account, cause="c", seconds=seconds, role=role)


def test_waiting_is_shown_by_step_and_cause_and_dominant_waits_on_a_person_propose_a_rule() -> None:
    waits = [
        wait("approve", "wait.human", 3600 * 6),
        wait("approve", "wait.human", 3600 * 2),
        wait("classify", "limit.provider", 3600),
        wait("book", "wait.external", 3600),
    ]
    view = v.variants("pay", "1", DESIGNED, v.travelled([]), waits, {}, {})
    first = view.waiting[0]
    assert first.step_id == "approve" and first.by_cause == {"wait.human": 28800.0}
    assert first.share == 0.8
    (proposal,) = view.proposals
    assert proposal.kind == "rule" and proposal.step_id == "approve"
    assert view.summary == "No run of this process has been recorded yet."


def test_a_role_s_waiting_is_shown_only_where_at_least_two_hold_it() -> None:
    waits = [wait("approve", "wait.human", 7200), wait("check", "wait.human", 3600, role="audit")]
    view = v.variants(
        "pay",
        "1",
        DESIGNED,
        v.travelled([]),
        waits,
        {"accounts-approver": 2, "audit": 1},
        {"approve": "accounts-approver"},
    )
    by = {r.role: r for r in view.roles}
    assert by["accounts-approver"].seconds == 7200.0
    assert by["audit"].seconds is None and "too few hold it to show" in by["audit"].text
