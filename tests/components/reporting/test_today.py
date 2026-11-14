"""What waits on the start page: one short list, the most urgent first (ADR-0318 §2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from taktus.components.reporting.domain.service.today import (
    TITLE_LENGTH,
    Waiting,
    WaitKind,
    one_line,
    waits,
)

AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


def wait(n: int, *, urgent: bool = False) -> Waiting:
    return Waiting(
        kind=WaitKind.FAILURE,
        title=f"Run {n} failed",
        link=f"#/runs/run_{n}",
        since=AT + timedelta(minutes=n),
        urgent=urgent,
    )


def test_the_urgent_come_first_then_the_newest_and_five_at_most() -> None:
    shown = waits([wait(1), wait(2, urgent=True), wait(3), wait(4), wait(5), wait(6), wait(0)])
    assert [w.link for w in shown] == [
        "#/runs/run_2",
        "#/runs/run_6",
        "#/runs/run_5",
        "#/runs/run_4",
        "#/runs/run_3",
    ]


def test_a_title_is_one_line_of_bounded_length() -> None:
    assert one_line("First line\nsecond line") == "First line"
    assert one_line("  spaced   out  ") == "spaced out"
    long = one_line("x" * 500)
    assert len(long) == TITLE_LENGTH and long.endswith("…")
    assert one_line("") == "—"
