"""The rules of the removal test, as tables (ADR-0003, contracts.md §3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    Maturity,
    RemovalResult,
    RunSummary,
    StepFinding,
    Verdict,
)
from taktus.components.catalog.domain.service import removal
from taktus.shared.v1 import ConsumptionQuantities, Step

AT = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


def step(id: str = "s", method: str = "worker", fallback: str | None = "human") -> Step:
    fields = {
        "id": id,
        "method": method,
        "reason": "test",
        "rejected": [],
        "exactness": "tolerant",
        "requires": ["shell.script"] if method == "worker" else None,
    }
    if fallback is not None:
        fields["fallback"] = {"when": "it fails", "to": fallback}
    return Step.model_validate({k: v for k, v in fields.items() if v is not None})


@pytest.mark.parametrize(
    ("alternative", "fallback", "verdict", "reason_has"),
    [
        ("worker.other", "human", Verdict.CHANGED, "worker.other serves"),
        ("worker.other", None, Verdict.CHANGED, "worker.other serves"),
        (None, "human", Verdict.CHANGED, "falls back to a person"),
        (None, "rule", Verdict.BROKE, "cannot switch to"),
        (None, None, Verdict.BROKE, "names no fallback"),
    ],
)
def test_a_step_changes_with_an_alternative_or_a_person_and_breaks_otherwise(
    alternative: str | None, fallback: str | None, verdict: Verdict, reason_has: str
) -> None:
    method = "rule" if fallback is None else "worker"
    finding = removal.step_finding(
        step(method=method, fallback=fallback), "shell.script", alternative
    )
    assert finding.verdict is verdict
    assert reason_has in finding.reason
    assert finding.alternative == alternative


def finding(step_id: str, verdict: Verdict, fallback: str | None = None) -> StepFinding:
    return StepFinding(
        step=step_id,
        served="shell.script",
        alternative=None,
        fallback=fallback,
        verdict=verdict,
        reason="test",
    )


def test_a_process_breaks_if_any_step_does() -> None:
    assert removal.process_verdict([finding("a", Verdict.CHANGED)]) is Verdict.CHANGED
    assert (
        removal.process_verdict([finding("a", Verdict.CHANGED), finding("b", Verdict.BROKE)])
        is Verdict.BROKE
    )


def summary(state: str, at_step: str | None = None, compute: float | None = None) -> RunSummary:
    return RunSummary(
        run_id=f"run_{state}",
        state=state,
        cause=None if state == "finished" else "failure",
        at_step=at_step,
        consumption=None
        if compute is None
        else ConsumptionQuantities(compute_seconds=compute, resource_class="cpu.small"),
    )


@pytest.mark.parametrize(
    ("baseline", "withheld", "findings", "verdict", "words"),
    [
        # Both finish: changed, and the consumption delta is stated.
        (
            summary("finished", compute=2.0),
            summary("finished", compute=3.0),
            [],
            Verdict.CHANGED,
            "compute_seconds 2.0 → 3.0",
        ),
        # The baseline halts at the last step by design and the withheld run halts there too.
        (
            summary("halted", "overreach"),
            summary("halted", "overreach"),
            [],
            Verdict.CHANGED,
            "same point",
        ),
        # The withheld run stops where a person takes over.
        (
            summary("halted", "overreach"),
            summary("escalated", "compute"),
            [finding("compute", Verdict.CHANGED, fallback="human")],
            Verdict.CHANGED,
            "a person takes over",
        ),
        # The withheld run stops at a step nobody takes over.
        (
            summary("finished"),
            summary("escalated", "read"),
            [finding("read", Verdict.BROKE)],
            Verdict.BROKE,
            "ends escalated at read",
        ),
        # The withheld run could not even start.
        (
            summary("finished"),
            summary("not_started"),
            [],
            Verdict.BROKE,
            "ends not_started",
        ),
    ],
)
def test_two_runs_are_compared_by_where_they_came_to(
    baseline: RunSummary,
    withheld: RunSummary,
    findings: list[StepFinding],
    verdict: Verdict,
    words: str,
) -> None:
    got, said = removal.compare(findings, baseline, withheld)
    assert got is verdict
    assert words in said


def test_the_integration_breaks_if_any_process_does_and_changes_when_nothing_uses_it() -> None:
    changed = removal.resolved_only("p@1", [finding("a", Verdict.CHANGED)], "not run: x")
    broke = removal.resolved_only("q@1", [finding("b", Verdict.BROKE)], "not run: y")
    assert removal.overall([]) is Verdict.CHANGED
    assert removal.overall([changed]) is Verdict.CHANGED
    assert removal.overall([changed, broke]) is Verdict.BROKE
    assert changed.note == "not run: x" and changed.exercised == "resolved"


def test_a_process_is_run_only_when_nothing_leaves_and_every_input_has_an_example() -> None:
    assert removal.safe_to_run([], []) is None
    assert "would leave the system" in (removal.safe_to_run(["write"], []) or "")
    assert "no example for input" in (removal.safe_to_run([], ["issue"]) or "")


def test_the_database_is_the_known_exception() -> None:
    assert "persistence.database" in removal.EXCEPTIONS
    assert "ADR-0002" in removal.EXCEPTIONS["persistence.database"]


def result(verdict: Verdict) -> RemovalResult:
    return RemovalResult(
        integration="worker.endpoint",
        family="worker",
        verdict=verdict,
        tested_at=AT,
        run_id="run_removal",
    )


def test_verified_needs_both_halves_and_the_record_names_what_is_missing() -> None:
    nothing = AdapterMaturity(id="worker.endpoint", tenant="t", family="worker", updated_at=AT)
    assert nothing.maturity is Maturity.EXPERIMENTAL
    assert nothing.missing == (
        "the conformance suite has not been recorded as passed",
        "the removal test has not run",
    )
    removed = nothing.model_copy(update={"removal": result(Verdict.CHANGED)})
    assert removed.removal_passed and removed.maturity is Maturity.EXPERIMENTAL
    assert removed.missing == ("the conformance suite has not been recorded as passed",)
    broke = nothing.model_copy(update={"removal": result(Verdict.BROKE)})
    assert not broke.removal_passed and "ended broke" in broke.missing[1]
    both = removed.model_copy(update={"conformance_passed_at": AT})
    assert both.maturity is Maturity.VERIFIED and both.missing == ()
