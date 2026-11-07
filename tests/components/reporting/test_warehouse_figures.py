"""A warehouse figure as the export carries it (UC-5.6 §2, ADR-0291 §3): the value its corridor
judged, or withheld with why; its basis names the query by reference, never by its text."""

from __future__ import annotations

from datetime import UTC, datetime

from taktus.components.reporting.domain.model import Corridor, Judged, Level
from taktus.components.reporting.domain.service import warehouse

AT = datetime(2026, 11, 6, 6, 0, tzinfo=UTC)
QUERY = "SELECT day, subscribers FROM daily_subscribers"


def corridor() -> Corridor:
    return Corridor(
        id="product.subscribers_daily@1",
        tenant="default",
        signal="product.subscribers_daily",
        version=1,
        process="read-subscribers",
        step="read",
        select="output.rows.0.subscribers",
        bounds="fixed",
        direction="below",
        yellow=100,
        red=80,
        role="owner",
        case="https://tickets.example/board/subscribers",
        changed_at=AT,
    )


READING = warehouse.Reading(
    operation="warehouse.queries.run",
    fixed=True,
    seq=7,
    digest="sha256:" + "a" * 64,
    sent_at=AT,
)


def test_a_judged_warehouse_reading_is_a_figure_with_its_query_by_reference() -> None:
    judged = Judged(
        signal="product.subscribers_daily",
        corridor="product.subscribers_daily@1",
        level=Level.YELLOW,
        value=90.0,
        yellow_at=100,
        red_at=80,
        run_id="run_3",
        step_id="read",
        process_version="read-subscribers@1",
        at=AT,
    )
    shown = warehouse.figure(corridor(), judged, READING)
    assert (shown.id, shown.scope, shown.subject, shown.value) == (
        "signal.warehouse",
        "process",
        "read-subscribers",
        90.0,
    )
    assert shown.withheld is None and shown.definition and "fixed" in shown.method
    assert shown.basis["signal"] == "product.subscribers_daily"
    assert shown.basis["level"] == "yellow" and shown.basis["run_id"] == "run_3"
    assert shown.basis["query"] == {
        "operation": "warehouse.queries.run",
        "fixed": True,
        "ledger_seq": 7,
        "digest": "sha256:" + "a" * 64,
        "sent_at": AT.isoformat(),
        "text_at": "/levels/runs/run_3/steps/read/queries",
    }
    assert QUERY not in str(shown.model_dump()), "the query by reference, never its text"


def test_a_signal_not_measured_is_withheld_with_why_never_zero() -> None:
    judged = Judged(
        signal="product.subscribers_daily",
        corridor="product.subscribers_daily@1",
        level=Level.UNMEASURED,
        reason="no_measurement",
    )
    shown = warehouse.figure(
        corridor(), judged, warehouse.Reading(operation="warehouse.queries.run", fixed=False)
    )
    assert shown.value is None
    assert shown.withheld == "no reading of the warehouse is recent enough"
    assert "a query given at run time" in shown.method
    assert shown.basis["query"] == {"operation": "warehouse.queries.run", "fixed": False}
