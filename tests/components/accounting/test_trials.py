"""A model trial reports each candidate's runs of the same cases side by side (#448, ADR-0149).

Per candidate: the cases passed, the money at each run's own table, tokens in and out, the
wall time, and each case's results beside the other candidates'. A verdict per case, the score
of its evaluation, replaces the run's own ending. Nothing here chooses a model.
"""

from __future__ import annotations

import pytest

from taktus.components.accounting.application.service import SpendHandler
from taktus.components.accounting.application.service.trials import ReportTrial, TrialReports
from taktus.ports.worker import Limits

from ..run.test_estimates import ISSUE, priced
from ..run.test_llm_steps import WORK, ModelHarness, llm


async def test_each_candidate_is_reported_per_case_and_in_total() -> None:
    h = priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))
    runs = {
        "model-a": {"case-1": (await h.start(Limits(currency={"usd": 1.0}))).id},
        "model-b": {"case-1": (await h.start(Limits(currency={"usd": 1.0}))).id},
    }
    spend = SpendHandler(h.ledger, h.objects, h.persistence)
    reports = TrialReports(h.ledger, spend, h.persistence)
    report = await reports.execute(ReportTrial("reasoning", "t", runs))
    assert [c.model for c in report.candidates] == ["model-a", "model-b"]
    a, b = report.candidates
    assert a.passed == 1 and b.passed == 1
    assert a.amount == pytest.approx(b.amount or 0) and a.currency == "usd"
    assert a.tokens_in > 0 and a.tokens_out > 0
    [case] = a.cases
    assert case.state == "finished" and case.wall_seconds is not None
    assert report.differing == (), "the same fake model answered both"

    judged = await reports.execute(
        ReportTrial("reasoning", "t", runs, verdicts={"model-b": {"case-1": False}})
    )
    assert [c.passed for c in judged.candidates] == [1, 0], "the evaluation's verdict decides"
