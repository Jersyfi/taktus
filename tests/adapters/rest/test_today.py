"""`GET /levels/today`: the start page in one request (ADR-0318).

The overview is the overview's own answer; the counts and the operation's marks are the same
figures the routes that read them alone answer; what waits is one short list, the most urgent
first; a reader who may not read the owner's reports gets no figure of them; and the `ETag`
answers `304` while nothing changed.
"""

from __future__ import annotations

from datetime import date

import httpx

from taktus.components.reporting.application.service import RaiseReport
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.run.domain.model import RunState
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .conftest import TENANT, Services, a_run
from .test_operation import OUTSIDER, OWNER, readers
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]


async def scene(given: Services) -> dict[str, dict[str, str]]:
    """The operation's records of `test_operation`, a run that waits on a person, one that
    escalated, and a need that is past its date."""
    keys = await readers(given)
    waiting = await a_run(given, "run_wait")
    failed = await a_run(given, "run_failed")
    async with given.persistence.transaction(TENANT):
        await given.runs.put(TENANT, waiting.model_copy(update={"state": RunState.WAITING_HUMAN}))
        await given.runs.put(TENANT, failed.model_copy(update={"state": RunState.ESCALATED}))
        await given.ledger.record(
            TENANT,
            Fact(
                kind="run.escalated",
                refs=LedgerRefs(
                    tenant=TENANT, run_id="run_failed", process_version="p@1", plan_id="pln_1"
                ),
                outcome="failure",
            ),
        )
    await given.owner.raising.execute(
        RaiseReport(
            tenant=TENANT,
            id="need-1",
            kind=ReportKind.NEED,
            title="A credential for the mail connector\nwith more on a second line",
            needed=["Provide the credential."],
            steps=["Create it.", "Map it."],
            standing_still=["Mail stands still."],
            due=date(2000, 1, 1),
        )
    )
    return keys


async def test_a_key_is_needed(client: Client) -> None:
    http, _, base = client
    is_problem(await http.get(f"{base}/levels/today"), 401)


async def test_the_start_page_is_one_answer_with_the_figures_of_the_routes_it_replaces(
    client: Client,
) -> None:
    http, given, base = client
    keys = await scene(given)
    answer = await http.get(f"{base}/levels/today", headers=keys[OWNER])
    assert answer.status_code == 200, answer.text
    today = answer.json()
    overview = (await http.get(f"{base}/levels/overview", headers=keys[OWNER])).json()
    operation = (await http.get(f"{base}/operation", headers=keys[OWNER])).json()
    assert today["overview"] == overview
    assert today["marks"]["operation"] == operation
    counts = today["counts"]
    assert counts["waiting_on_a_person"] == 1
    assert counts["failed_last_24h"] == 1
    assert counts["open_incidents"] == operation["incidents"]["open"]
    assert counts["open_alerts"] == operation["alerts"]["in_effect"]
    assert counts["running_now"] == sum(a["working"] for a in overview["areas"])
    assert counts["waiting_for_you"] == 2, "the need and the alert"
    kinds = [w["kind"] for w in today["waits"]]
    assert kinds[:2] == ["need", "alert"] or kinds[:2] == ["alert", "need"], "urgent first"
    assert kinds[-1] == "failure" and len(today["waits"]) <= 5
    need = next(w for w in today["waits"] if w["kind"] == "need")
    assert need == {
        "kind": "need",
        "title": "A credential for the mail connector",
        "link": "#/reports/need-1",
        "since": need["since"],
        "urgent": True,
    }
    failure = next(w for w in today["waits"] if w["kind"] == "failure")
    assert failure["link"] == "#/runs/run_failed"
    assert today["marks"]["needs"] == {"readable": True, "open": 1}
    assert today["marks"]["requests"] == {"waiting": 0, "overdue": 0}


async def test_a_reader_who_does_not_read_the_reports_gets_no_figure_of_them(
    client: Client,
) -> None:
    http, given, base = client
    keys = await scene(given)
    today = (await http.get(f"{base}/levels/today", headers=keys[OUTSIDER])).json()
    assert today["counts"]["open_alerts"] is None
    assert today["marks"]["needs"] == {"readable": False, "open": None}
    assert today["marks"]["findings"] == {"readable": False}
    assert {w["kind"] for w in today["waits"]} == {"failure"}


async def test_an_unchanged_start_page_is_answered_304_without_a_body(client: Client) -> None:
    http, given, base = client
    keys = await scene(given)
    first = await http.get(f"{base}/levels/today", headers=keys[OWNER])
    tag = first.headers["etag"]
    again = await http.get(f"{base}/levels/today", headers={**keys[OWNER], "If-None-Match": tag})
    assert again.status_code == 304 and again.content == b""
    assert again.headers["etag"] == tag
    await a_run(given, "run_new")
    changed = await http.get(f"{base}/levels/today", headers={**keys[OWNER], "If-None-Match": tag})
    assert changed.status_code == 200 and changed.headers["etag"] != tag
