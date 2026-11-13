"""Views, the export, reports, explanations, the value ledger and a person's own view on the
HTTP surface (UC-5.7, UC-6.4, UC-6.2, UC-6.5, UC-6.10, UC-13.4, UC-13.5, UC-9.3; ADR-0241 to
ADR-0245).

One world: a process registered with takeover instructions, three runs recorded in the ledger,
four people in two roles, and the organisation's value basis stated by the owner.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from composition.test_warehouse_signals import SUBSCRIBERS
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryProvenanceStore, MemoryRepository
from taktus.components.catalog.domain.model import AgentCore
from taktus.components.governance.domain.model.domains import Domain
from taktus.components.identity.domain.model import Right
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.domain.model.proposal import Difference, Proposal
from taktus.components.reporting.domain.model import Corridor, Judged, Level
from taktus.components.run.domain.model import Run, StepState
from taktus.ports.ledger import Fact
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import LedgerRefs, Method, Provenance

from ..persistence.samples import agent_core
from ..persistence.samples import run as a_run
from .conftest import OTHER, TENANT, Services
from .test_process_level import bearer
from .test_roles import BUNDLE
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

ROOT = Path(__file__).resolve().parents[3]
DIGEST = "sha256:" + "3" * 64
K_01 = ROOT / "blueprints" / "knowledge" / "processes" / "K-01-answer-from-knowledge.yaml"


async def world(given: Services) -> dict[str, str]:
    keys: dict[str, str] = {}
    for name, roles in [
        ("idn_owner", ("owner",)),
        ("idn_ada", ("accounting",)),
        ("idn_bo", ("accounting",)),
        ("idn_cy", ("controlling",)),
        ("idn_di", ("accounting", "controlling")),
    ]:
        _, keys[name] = await given.identities.add(TENANT, name, (TENANT,), roles=roles)
    _, keys["other"] = await given.identities.add(OTHER, "idn_zed", (OTHER,), roles=("owner",))
    register = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    await register.execute(
        RegisterProcessVersion(instructed(BUNDLE), tenant=TENANT, by="idn_owner")
    )
    for n, end in enumerate(("run.finished", "run.finished", "run.escalated"), start=1):
        await fact(given, "run.created", f"run_{n}")
        await fact(
            given,
            "step.finished",
            f"run_{n}",
            step="total",
            outcome="succeeded",
            method=Method.RULE,
        )
        await fact(given, end, f"run_{n}")
    return keys


async def fact(given: Services, kind: str, run: str, **more: Any) -> None:
    step = more.pop("step", None)
    version = more.pop("version", "invoice@1")
    async with given.persistence.transaction(TENANT):
        await given.ledger.record(
            TENANT,
            Fact(
                kind=kind,
                refs=LedgerRefs(tenant=TENANT, process_version=version, run_id=run, step_id=step),
                **more,
            ),
        )


async def stated(http: httpx.AsyncClient, base: str, keys: dict[str, str]) -> None:
    answer = await http.put(
        f"{base}/value/basis",
        headers=bearer(keys["idn_owner"]),
        json={
            "pay": [{"role": "accounting", "per_hour": 60}],
            "processes": [
                {"process": "invoice", "minutes_by_hand": 30, "roles_by_hand": ["accounting"]}
            ],
        },
    )
    assert answer.status_code == 200, answer.text


async def configured(http: httpx.AsyncClient, base: str, keys: dict[str, str]) -> None:
    answer = await http.put(
        f"{base}/views/configuration",
        headers=bearer(keys["idn_owner"]),
        json={
            "views": [
                {
                    "id": "team",
                    "title": "Team",
                    "roles": ["accounting"],
                    "group_by": "process",
                    "figures": ["value.runs_ended", "value.time_saved_hours", "value.cost_money"],
                },
                {
                    "id": "control",
                    "title": "Control",
                    "roles": ["controlling"],
                    "persons": ["idn_ada"],
                    "group_by": "process",
                    "figures": ["value.quality", "value.escalation_rate"],
                },
            ],
            "entitlements": {
                "value.runs_ended": ["accounting", "owner"],
                "value.time_saved_hours": ["accounting", "owner"],
                "value.quality": ["controlling", "owner"],
                "value.escalation_rate": ["controlling", "owner"],
            },
            "depth": {"accounting": "short", "controlling": "full"},
            "language": {"controlling": "de"},
        },
    )
    assert answer.status_code == 200, answer.text


def figures_of(views: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for v in views["views"] for f in v["figures"]]


async def test_every_figure_a_view_shows_is_in_the_export_with_the_same_definition_and_value(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await stated(http, base, keys)
    await configured(http, base, keys)
    for name in ("idn_ada", "idn_cy", "idn_di"):
        views = (await http.get(f"{base}/views", headers=bearer(keys[name]))).json()
        export = (await http.get(f"{base}/figures", headers=bearer(keys[name]))).json()
        exported = {(f["id"], f["scope"], f["subject"]): f for f in export["figures"]}
        shown = figures_of(views)
        assert shown, f"{name} sees a view"
        for figure in shown:
            twin = exported[(figure["id"], figure["scope"], figure["subject"])]
            assert (twin["definition"], twin["value"]) == (figure["definition"], figure["value"])
    owner = (await http.get(f"{base}/figures", headers=bearer(keys["idn_owner"]))).json()
    ended = next(f for f in owner["figures"] if f["id"] == "value.runs_ended")
    assert (ended["value"], ended["component"]) == (3, "value")


async def test_a_figure_reaches_only_the_roles_entitled_to_it_and_a_view_never_widens_that(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await stated(http, base, keys)
    await configured(http, base, keys)

    def ids(views: dict[str, Any]) -> set[str]:
        return {f["id"] for f in figures_of(views)}

    ada = (await http.get(f"{base}/views", headers=bearer(keys["idn_ada"]))).json()
    assert [v["id"] for v in ada["views"]] == ["team", "control"], "given by name"
    assert ids(ada) == {"value.runs_ended", "value.time_saved_hours"}, (
        "the control view is given to her, and shows her nothing she is not entitled to"
    )
    cy = (await http.get(f"{base}/views", headers=bearer(keys["idn_cy"]))).json()
    assert ids(cy) == {"value.quality", "value.escalation_rate"}
    di = (await http.get(f"{base}/views", headers=bearer(keys["idn_di"]))).json()
    assert ids(di) == ids(ada) | ids(cy), "two roles: the union, and nothing more"
    export = (await http.get(f"{base}/figures", headers=bearer(keys["idn_cy"]))).json()
    assert {f["id"] for f in export["figures"]} == ids(cy), "the export respects visibility"
    assert "value.cost_money" not in ids(di), "a figure entitled to no role reaches nobody"
    other = (await http.get(f"{base}/figures", headers=bearer(keys["other"]))).json()
    assert all(f["subject"] != "invoice" for f in other["figures"]), "another tenant"


async def test_a_view_that_groups_by_person_or_names_an_unknown_figure_is_refused(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    for body in (
        {
            "views": [
                {"id": "p", "title": "P", "figures": ["value.quality"], "group_by": "person"}
            ],
            "entitlements": {},
        },
        {"views": [{"id": "p", "title": "P", "figures": ["value.made_up"]}], "entitlements": {}},
    ):
        answer = await http.put(
            f"{base}/views/configuration", headers=bearer(keys["idn_owner"]), json=body
        )
        assert is_problem(answer, 422)
    answer = await http.put(f"{base}/views/configuration", headers=bearer(keys["idn_ada"]), json={})
    assert is_problem(answer, 403)


async def test_the_csv_export_carries_the_rows_of_the_json_export(client: Client) -> None:
    http, given, base = client
    keys = await world(given)
    as_json = (await http.get(f"{base}/figures", headers=bearer(keys["idn_owner"]))).json()
    answer = await http.get(f"{base}/figures.csv", headers=bearer(keys["idn_owner"]))
    assert answer.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(answer.text)))
    assert [(r["id"], r["subject"]) for r in rows] == [
        (f["id"], f["subject"]) for f in as_json["figures"]
    ]


async def test_the_overview_s_counts_are_in_the_export_as_the_overview_counts_them(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    overview = await http.get(f"{base}/levels/overview", headers=bearer(keys["idn_owner"]))
    (area,) = overview.json()["areas"]
    (process,) = area["processes"]
    export = (await http.get(f"{base}/figures", headers=bearer(keys["idn_owner"]))).json()
    counted = {
        f["id"]: f["value"]
        for f in export["figures"]
        if f["subject"] == "invoice" and f["id"].startswith("run.")
    }
    assert counted == {"run.working": process["working"], "run.waiting": process["waiting"]}


async def test_the_run_and_process_levels_figures_are_in_the_export_as_the_levels_show_them(
    client: Client,
) -> None:
    """UC-6.10 §2, UC-5.7: what a run and each of its steps consumed, and the runs of the
    process level, are in the export with the levels' own values; whom the read API does not
    show the run, and a role the figure is not entitled to, finds none of them."""
    http, given, base = client
    keys = await world(given)
    async with given.persistence.transaction(TENANT):
        await MemoryRepository(given.persistence, Run).put(
            TENANT, a_run("run_used", TENANT).model_copy(update={"process_version": "invoice@1"})
        )
    owner = bearer(keys["idn_owner"])
    level = (await http.get(f"{base}/levels/runs/run_used", headers=owner)).json()
    process = (await http.get(f"{base}/levels/processes/invoice", headers=owner)).json()
    export = (await http.get(f"{base}/figures", headers=owner)).json()["figures"]
    consumed = {(f["unit"], f["value"]) for f in export if f["id"] == "run.consumed"}
    assert consumed and consumed == {(f["name"], f["value"]) for f in level["run"]["consumed"]}
    used = {(f["subject"], f["unit"], f["value"]) for f in export if f["id"] == "step.consumed"}
    assert used and used == {
        (f"run_used/{s['id']}", f["name"], f["value"])
        for s in level["steps"]
        for f in s["consumption"]
    }
    (runs,) = [f for f in export if f["id"] == "process.runs"]
    assert (runs["subject"], runs["value"]) == ("invoice", len(process["runs"]))
    rows = csv.DictReader(io.StringIO((await http.get(f"{base}/figures.csv", headers=owner)).text))
    assert {(r["unit"], float(r["value"])) for r in rows if r["id"] == "run.consumed"} == {
        (u, float(v)) for u, v in consumed
    }
    for who in (keys["other"], keys["idn_ada"]):
        theirs = (await http.get(f"{base}/figures", headers=bearer(who))).json()["figures"]
        assert not [f for f in theirs if f["id"] in {"run.consumed", "step.consumed"}], who
    other = await http.get(f"{base}/levels/runs/run_used", headers=bearer(keys["other"]))
    assert other.status_code == 404


async def test_the_balance_is_summed_per_domain_chain_and_assistant_in_the_export(
    client: Client,
) -> None:
    """UC-15.1, UC-9.3, UC-12.1, ADR-0288: the groups come from their owners — the governance
    component's domain, a chain's link runs, the catalogue's agent by its flow — and each sum
    equals the process's own figure, for whom may see it."""
    http, given, base = client
    keys = await world(given)
    await stated(http, base, keys)
    at = datetime(2026, 11, 1, tzinfo=UTC)
    async with given.persistence.transaction(TENANT):
        await MemoryRepository(given.persistence, Domain).put(
            TENANT,
            Domain(
                id="finance",
                tenant=TENANT,
                name="Finance",
                owner="idn_owner",
                jurisdiction="DE",
                processes=("invoice", "payroll"),
                created_at=at,
            ),
        )
        await MemoryRepository(given.persistence, AgentCore).put(
            TENANT,
            agent_core(TENANT).model_copy(
                update={"id": "clerk@1", "agent": "clerk", "version": "1", "flow": "invoice"}
            ),
        )
        await MemoryRepository(given.persistence, Run).put(
            TENANT,
            a_run("run_chain_1", TENANT).model_copy(
                update={"plan_id": "pln_month-end_1", "process_version": "invoice@1"}
            ),
        )
    export = (await http.get(f"{base}/figures", headers=bearer(keys["idn_owner"]))).json()
    found = {(f["id"], f["scope"], f["subject"]): f for f in export["figures"]}
    own = found[("value.balance", "process", "invoice")]
    for scope, subject in (("domain", "finance"), ("chain", "month-end"), ("assistant", "clerk")):
        summed = found[("value.balance", scope, subject)]
        assert summed["value"] == own["value"] and summed["value"] is not None, (scope, summed)
        assert summed["basis"]["processes"] == ["invoice"], "payroll is no process the tenant has"
        assert summed["component"] == "value" and summed["method"]
    for figure in export["figures"]:
        assert figure["scope"] != "person"


async def test_the_same_work_with_and_without_a_knowledge_source_is_compared_for_whom_may_read_it(
    client: Client,
) -> None:
    """UC-5.5 §2, ADR-0291: the comparison at `GET /value/knowledge`, entitled as the cockpit
    figure it compares."""
    http, given, base = client
    keys = await world(given)
    register = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    bundle = yaml.safe_load(K_01.read_text(encoding="utf-8"))
    await register.execute(RegisterProcessVersion(bundle, tenant=TENANT, by="idn_owner"))
    for run, served, end in (("run_k1", True, "run.finished"), ("run_k2", False, "run.escalated")):
        await fact(given, "run.created", run, version="k-01@1")
        await fact(
            given,
            "step.finished",
            run,
            version="k-01@1",
            step="search",
            outcome="succeeded",
            method=Method.RULE if served else Method.HUMAN,
            adapter="connector.knowledge" if served else None,
        )
        await fact(given, end, run, version="k-01@1")
    owner = await http.get(f"{base}/value/knowledge", headers=bearer(keys["idn_owner"]))
    assert owner.status_code == 200, owner.text
    found = {f["id"]: f for f in owner.json()["figures"] if f["subject"] == "k-01"}
    assert found["value.with_knowledge.runs_ended"]["basis"]["runs"] == ["run_k1"]
    assert found["value.without_knowledge.runs_ended"]["basis"]["runs"] == ["run_k2"]
    assert found["value.knowledge_effect.escalation_rate"]["value"] == -1
    assert found["value.knowledge_effect.quality"]["value"] == 1
    cost = found["value.knowledge_effect.cost_per_case"]
    assert cost["value"] is None and cost["withheld"], "never zero for want of a basis"
    assert not any(f["subject"] == "invoice" for f in owner.json()["figures"]), (
        "a process that reads no knowledge is not compared"
    )
    await configured(http, base, keys)
    cy = (await http.get(f"{base}/value/knowledge", headers=bearer(keys["idn_cy"]))).json()
    assert {f["id"].rsplit(".", 1)[1] for f in cy["figures"]} == {"quality", "escalation_rate"}
    other = (await http.get(f"{base}/value/knowledge", headers=bearer(keys["other"]))).json()
    assert other["figures"] == [], "another tenant"
    assert (await http.get(f"{base}/value/knowledge")).status_code == 401


async def test_every_warehouse_figure_the_signals_view_shows_is_in_the_export(
    client: Client,
) -> None:
    """UC-5.6 §2, ADR-0291 §3: a signal over a step that queries the warehouse, shown at
    `GET /signals`, is in `GET /figures` and its CSV with the same value; a view may name it."""
    http, given, base = client
    keys = await world(given)
    register = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    await register.execute(
        RegisterProcessVersion(instructed(SUBSCRIBERS), tenant=TENANT, by="idn_owner")
    )
    at = datetime(2026, 11, 6, 6, 0, tzinfo=UTC)
    corridor = Corridor(
        id="product.subscribers_daily@1",
        tenant=TENANT,
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
        changed_at=at,
    )
    judged = Judged(
        signal=corridor.signal,
        corridor=corridor.id,
        level=Level.YELLOW,
        value=90.0,
        yellow_at=100,
        red_at=80,
        run_id="run_w1",
        step_id="read",
        process_version="read-subscribers@1",
        at=at,
    )
    given.operation.signals_of[TENANT] = [(corridor, judged)]
    owner = bearer(keys["idn_owner"])
    (signal,) = (await http.get(f"{base}/signals", headers=owner)).json()["signals"]
    export = (await http.get(f"{base}/figures", headers=owner)).json()
    (figure,) = [f for f in export["figures"] if f["id"] == "signal.warehouse"]
    assert (figure["subject"], figure["value"]) == ("read-subscribers", signal["value"])
    assert figure["basis"]["signal"] == signal["signal"]
    assert figure["basis"]["query"]["operation"] == "warehouse.queries.run"
    assert figure["basis"]["query"]["fixed"] is True
    rows = list(
        csv.DictReader(io.StringIO((await http.get(f"{base}/figures.csv", headers=owner)).text))
    )
    assert ("signal.warehouse", "read-subscribers") in {(r["id"], r["subject"]) for r in rows}
    stored = await http.put(
        f"{base}/views/configuration",
        headers=owner,
        json={
            "views": [
                {
                    "id": "data",
                    "title": "Data",
                    "roles": ["owner"],
                    "group_by": "process",
                    "figures": ["signal.warehouse"],
                }
            ],
            "entitlements": {"signal.warehouse": ["owner"]},
        },
    )
    assert stored.status_code == 200, stored.text
    (view,) = (await http.get(f"{base}/views", headers=owner)).json()["views"]
    assert [f["value"] for f in view["figures"]] == [90.0]
    cy = (await http.get(f"{base}/figures", headers=bearer(keys["idn_cy"]))).json()
    assert all(f["id"] != "signal.warehouse" for f in cy["figures"]), "entitled to owner only"


async def test_a_report_without_a_reader_is_refused_and_one_with_one_tells_what_bears_on_it(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    owner = bearer(keys["idn_owner"])
    refused = await http.put(
        f"{base}/reports/definitions/weekly",
        headers=owner,
        json={"trigger": "request", "channel": "channel.chat", "address": "C1"},
    )
    assert is_problem(refused, 422) and "reader" in refused.json()["detail"]
    answer = await http.put(
        f"{base}/reports/definitions/daily",
        headers=owner,
        json={
            "reader_role": "owner",
            "trigger": "schedule",
            "every": "day",
            "hour": 0,
            "channel": "channel.chat",
            "address": "C1",
        },
    )
    assert answer.status_code == 200, answer.text
    now = (await http.get(f"{base}/reports/definitions/daily/now", headers=owner)).json()
    kinds = [i["kind"] for i in now["items"]]
    assert "escalation" in kinds, "the escalated run bears on the owner"
    assert all("idn_" not in line for line in now["lines"]), "no person in a report"
    hidden = await http.get(
        f"{base}/reports/definitions/daily/now", headers=bearer(keys["idn_ada"])
    )
    assert is_problem(hidden, 404), "a report is for its reader role"

    said = await given.reading.reports.tick(TENANT, frozenset({"invoice"}))
    again = await given.reading.reports.tick(TENANT, frozenset({"invoice"}))
    assert (said, again) == (["daily"], []), "a slot is said once"
    (message,) = [s for s in given.deliveries.said if s.key.startswith("report:daily:")]
    assert message.channel == "channel.chat" and message.address == "C1"
    assert "reply here" in message.text


async def test_a_quiet_period_is_one_sentence(client: Client) -> None:
    http, given, base = client
    keys = await world(given)
    owner = bearer(keys["idn_owner"])
    await http.put(
        f"{base}/reports/definitions/acct",
        headers=owner,
        json={
            "reader_role": "marketing",
            "trigger": "request",
            "channel": "channel.chat",
            "address": "C2",
        },
    )
    now = (await http.get(f"{base}/reports/definitions/acct/now", headers=owner)).json()
    assert now["quiet"] and len(now["lines"]) == 1
    assert now["lines"][0].startswith("Nothing was outside its range from ")


async def explained_run(given: Services) -> None:
    async with given.persistence.transaction(TENANT):
        version = await MemoryRepository(given.persistence, ProcessVersion).get(TENANT, "invoice@1")
        assert version is not None
        run = Run(
            id="run_x",
            plan_id="pln_1",
            process_version="invoice@1",
            tenant=TENANT,
            identity="idn_owner",
            autonomy_level=2,
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            steps=version.steps,
            work=dict(version.work),
            created_at=given.clock.now(),
            updated_at=given.clock.now(),
        )
        run = run.model_copy(
            update={
                "step_runs": tuple(
                    s.model_copy(update={"state": StepState.SUCCEEDED}) for s in run.step_runs
                )
            }
        )
        await given.runs.put(TENANT, run)
        await MemoryProvenanceStore(given.persistence).append(
            TENANT,
            Provenance.model_validate(
                {
                    "id": "prv_total",
                    "run_id": "run_x",
                    "step_id": "total",
                    "process_version": "invoice@1",
                    "method": "rule",
                    "exactness": "exact",
                    "inputs": [],
                    "outputs": [],
                    "result_digest": DIGEST,
                    "ledger_seq": 1,
                    "recorded_at": given.clock.now(),
                }
            ),
        )


async def test_an_explanation_states_what_the_records_hold_at_the_depth_of_the_role(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await configured(http, base, keys)
    await explained_run(given)
    path = f"{base}/levels/runs/run_x/steps/total/explanation"
    short = (await http.get(path, headers=bearer(keys["idn_ada"]))).json()
    full = (await http.get(path, headers=bearer(keys["idn_cy"]))).json()
    assert short["depth"] == "short" and full["depth"] == "full"
    assert full["language"] == "de" and short["language"] == "en"
    assert "Why this method: a fixed sum" in short["lines"]
    assert any(DIGEST in line for line in full["lines"]), "the result, from provenance"
    assert short["grounded"] and full["grounded"]
    assert short["facts"] == full["facts"], "the same facts, at two depths"
    assert is_problem(await http.get(path, headers=bearer(keys["other"])), 404)
    summary = (await http.get(f"{base}/summary", headers=bearer(keys["idn_owner"]))).json()
    assert summary["lines"][0].startswith("invoice: runs_ended 3")


async def test_nobody_but_the_person_reads_their_own_view_until_they_share_it(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await stated(http, base, keys)
    mine = (await http.get(f"{base}/me/relief", headers=bearer(keys["idn_ada"]))).json()
    (relief,) = mine["processes"]
    assert relief["process"] == "invoice" and relief["hours_regained"] == 1.0
    assert relief["takeover"] == "processes/invoice/takeover"
    assert mine["reader"] == "idn_ada" and "regained" in mine["sentence"]
    for word in ("score", "rank", "points", "badge", "streak", "level"):
        assert word not in repr(mine).lower()
    theirs = f"{base}/people/idn_ada/relief"
    assert is_problem(await http.get(theirs, headers=bearer(keys["idn_cy"])), 404)
    assert is_problem(await http.get(theirs, headers=bearer(keys["idn_owner"])), 404)
    shared = await http.put(
        f"{base}/me/relief/settings",
        headers=bearer(keys["idn_ada"]),
        json={
            "shared_with": ["controlling"],
            "goals": [{"title": "Friday free", "hours_per_week": 1}],
        },
    )
    assert shared.status_code == 200, shared.text
    seen = await http.get(theirs, headers=bearer(keys["idn_cy"]))
    assert seen.status_code == 200 and seen.json()["goals"][0]["reached"] is True
    assert is_problem(await http.get(theirs, headers=bearer(keys["idn_owner"])), 404), (
        "shared with a role the owner does not hold: still not the owner's (principle 14)"
    )
    assert is_problem(await http.get(theirs, headers=bearer(keys["idn_bo"])), 404), (
        "a colleague of the same role does not read it either"
    )
    await http.put(
        f"{base}/me/relief/settings", headers=bearer(keys["idn_ada"]), json={"shared_with": []}
    )
    assert is_problem(await http.get(theirs, headers=bearer(keys["idn_cy"])), 404), "withdrawn"


async def test_what_taktus_took_off_a_role_one_person_holds_is_withheld_elsewhere(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await http.put(
        f"{base}/value/basis",
        headers=bearer(keys["idn_owner"]),
        json={
            "processes": [
                {"process": "invoice", "minutes_by_hand": 30, "roles_by_hand": ["controlling-lead"]}
            ]
        },
    )
    await given.identities.add(TENANT, "idn_lone", (TENANT,), roles=("controlling-lead",))
    export = (await http.get(f"{base}/figures", headers=bearer(keys["idn_owner"]))).json()
    saved = next(
        f
        for f in export["figures"]
        if f["id"] == "value.time_saved_hours" and f["scope"] == "process"
    )
    assert saved["value"] is None and "one person's" in saved["withheld"]


async def test_the_value_basis_is_set_by_owner_and_its_figures_say_who_set_it_when(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await stated(http, base, keys)
    refused = await http.put(
        f"{base}/value/basis",
        headers=bearer(keys["idn_owner"]),
        json={"pay": [{"role": "accounting", "per_hour": 1, "identity": "idn_ada"}]},
    )
    assert is_problem(refused, 422), "a rate per person cannot be configured"
    history = (await http.get(f"{base}/value/basis", headers=bearer(keys["idn_owner"]))).json()
    assert [v["set_by"] for v in history["versions"]] == ["idn_owner"]
    export = (await http.get(f"{base}/figures", headers=bearer(keys["idn_owner"]))).json()
    saved = next(
        f
        for f in export["figures"]
        if f["id"] == "value.time_saved_hours" and f["scope"] == "process"
    )
    assert saved["assumption"] and saved["basis"]["basis"]["set_by"] == "idn_owner"
    proposals = (
        await http.get(f"{base}/value/proposals", headers=bearer(keys["idn_owner"]))
    ).json()["proposals"]
    assert {p["kind"] for p in proposals} <= {
        "raise_autonomy",
        "observe",
        "optimise",
        "switch_off",
        "target",
        "deterioration",
    }
    index = (await http.get(f"{base}/value/index", headers=bearer(keys["idn_owner"]))).json()
    assert any(f["id"] == "value.bus_factor.without_taktus" for f in index["figures"])
    assert index["trend"]


TARGETS = {
    "processes": [{"process": "invoice", "minutes_by_hand": 30}],
    "targets": [{"process": "invoice", "figure": "value.quality", "low": 0.9}],
}


async def test_once_a_role_holds_the_right_to_steer_only_its_holders_set_targets(
    client: Client,
) -> None:
    """UC-9.1, ADR-0293: a target is set by a person with the right to steer. Until a role of
    the tenant holds `process.steer`, the owner sets it and a role without it is refused; from
    the first grant on, a role holding it sets it and every other role — the owner's too — is
    refused with the right named."""
    http, given, base = client
    keys = await world(given)
    owner, controller = bearer(keys["idn_owner"]), bearer(keys["idn_cy"])

    before = await http.put(f"{base}/value/basis", headers=controller, json=TARGETS)
    assert is_problem(before, 403) and "owner" in before.json()["detail"]
    assert (await http.put(f"{base}/value/basis", headers=owner, json=TARGETS)).status_code == 200

    await given.identities.grant(TENANT, "controlling", Right.PROCESS_STEER, by="idn_owner")

    steered = await http.put(f"{base}/value/basis", headers=controller, json=TARGETS)
    assert steered.status_code == 200, steered.text
    history = (await http.get(f"{base}/value/basis", headers=controller)).json()
    assert [v["set_by"] for v in history["versions"]] == ["idn_owner", "idn_cy"]
    assert history["versions"][-1]["basis"]["targets"][0]["figure"] == "value.quality"
    for refused in (
        await http.put(f"{base}/value/basis", headers=owner, json=TARGETS),
        await http.put(f"{base}/value/basis", headers=bearer(keys["idn_ada"]), json=TARGETS),
        await http.get(f"{base}/value/basis", headers=owner),
    ):
        assert is_problem(refused, 403), refused.text
        assert "process.steer" in refused.json()["detail"]


async def test_a_discovered_process_passes_its_stages_in_order_and_a_person_decides(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    owner = bearer(keys["idn_owner"])
    guided = (await http.get(f"{base}/discoveries/interview?mode=guided", headers=owner)).json()
    expert = (await http.get(f"{base}/discoveries/interview?mode=expert", headers=owner)).json()
    assert [q["key"] for q in guided["questions"]] == [q["key"] for q in expert["questions"]]
    found = (
        await http.post(
            f"{base}/discoveries",
            headers=owner,
            json={
                "title": "Bank check",
                "origin": "interview",
                "found": "open invoices against the bank, Fridays",
            },
        )
    ).json()
    stage = f"{base}/discoveries/{found['id']}/stages"
    early = await http.post(f"{stage}/decided", headers=owner, json={"decision": "automate"})
    assert is_problem(early, 409), "no stage without the one before"
    for name, body in (
        ("documented", {"description": "What: the check", "owner_role": "accounting"}),
        ("valued", {"minutes_by_hand": 45, "cases_per_month": 4}),
        ("decided", {"decision": "automate"}),
    ):
        answer = await http.post(f"{stage}/{name}", headers=owner, json=body)
        assert answer.status_code == 200, answer.text
    high = await http.post(
        f"{stage}/automated",
        headers=owner,
        json={"process_id": "invoice", "level": 3, "instructions": True},
    )
    assert is_problem(high, 409), "a discovered process enters at level 1 or 2"
    done = await http.post(
        f"{stage}/automated",
        headers=owner,
        json={"process_id": "invoice", "level": 2, "instructions": True},
    )
    assert done.json()["stage"] == "automated"
    async with given.persistence.transaction(TENANT):
        kinds = [
            e.kind for e in await given.ledger.entries(TENANT) if e.kind.startswith("discovery.")
        ]
    assert kinds == [
        f"discovery.{s}" for s in ("visible", "documented", "valued", "decided", "automated")
    ]


async def test_the_backlog_takes_a_proposal_a_discovered_process_and_entered_potential(
    client: Client,
) -> None:
    """UC-9.2: every entry of the backlog comes from a recorded source — an open proposal, a
    discovered process the organisation agreed on, potential a person entered with the basis —
    and names its expected benefit with the basis of that figure, marked as an expectation."""
    http, given, base = client
    keys = await world(given)
    owner = bearer(keys["idn_owner"])
    async with given.persistence.transaction(TENANT):
        version = await MemoryRepository(given.persistence, ProcessVersion).get(TENANT, "invoice@1")
        assert version is not None
        await MemoryRepository(given.persistence, Proposal).put(
            TENANT,
            Proposal(
                id="prp_1",
                tenant=TENANT,
                process_id="invoice",
                base_version="1",
                version="2",
                bundle={},
                requested_by="idn_owner",
                difference=Difference(
                    autonomy_before=version.autonomy, autonomy_after=version.autonomy
                ),
                created_at=given.clock.now(),
            ),
        )
    found = (
        await http.post(
            f"{base}/discoveries",
            headers=owner,
            json={"title": "Bank check", "origin": "interview", "found": "open items, Fridays"},
        )
    ).json()
    stage = f"{base}/discoveries/{found['id']}/stages"
    for name, body in (
        ("documented", {"description": "What: the check", "owner_role": "accounting"}),
        ("valued", {"minutes_by_hand": 45, "cases_per_month": 4}),
    ):
        answer = await http.post(f"{stage}/{name}", headers=owner, json=body)
        assert answer.status_code == 200, answer.text
    answer = await http.put(
        f"{base}/value/basis",
        headers=owner,
        json={
            "processes": [{"process": "invoice", "minutes_by_hand": 30}],
            "backlog": [
                {
                    "id": "dunning",
                    "title": "Dunning letters",
                    "hours_per_month": 12,
                    "basis": "two clerks' estimate, March",
                }
            ],
        },
    )
    assert answer.status_code == 200, answer.text

    answer = await http.get(f"{base}/value/transformation", headers=owner)
    assert answer.status_code == 200, answer.text
    backlog = {entry["kind"]: entry for entry in answer.json()["backlog"]}
    assert set(backlog) == {"proposal", "discovered", "entered"}
    assert all(entry["expectation"] is True for entry in backlog.values())
    assert backlog["proposal"]["id"] == "prp_1"
    assert backlog["proposal"]["basis"] == "30 minutes by hand per case, stated"
    assert backlog["discovered"]["id"] == found["id"]
    assert backlog["discovered"]["hours_per_month"] == 3
    assert backlog["discovered"]["basis"] == "45 minutes by hand, 4 cases a month"
    assert backlog["entered"]["id"] == "dunning"
    assert backlog["entered"]["hours_per_month"] == 12
    assert backlog["entered"]["basis"] == "two clerks' estimate, March"
    assert [e["kind"] for e in answer.json()["backlog"]] == ["entered", "discovered", "proposal"]


WEB = ROOT / "web" / "src"
CALL = re.compile(r"(?:read|readAs|send|sendAs|post|put)(?:<[^>]*>)?\(\s*[^,]+,\s*[`'\"]([^`'\"]+)")


async def test_every_path_the_web_app_calls_is_a_route_of_the_surface(client: Client) -> None:
    """Nobody is bound to the dashboard: whatever the web app does, the interface offers
    (UC-5.7 §2)."""
    http, _, base = client
    spec = (await http.get(f"{base}/openapi.json")).json()
    routes = [
        re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p.removeprefix(base).lstrip("/")) + "$")
        for p in spec["paths"]
    ]
    called: set[str] = set()
    for source in [*WEB.rglob("*.ts"), *WEB.rglob("*.svelte")]:
        if source.name.endswith(".test.ts"):
            continue
        for path in CALL.findall(source.read_text()):
            literal = re.sub(r"\$\{[^}]+\}", "x", path).split("?")[0]
            if "$" in literal or literal.startswith(("http", "#", "x/")) or literal == "x":
                continue
            called.add(literal.lstrip("/"))
    assert called, "the scan finds the web app's calls"
    missing = sorted(p for p in called if not any(r.match(p) for r in routes))
    assert not missing, f"the web app calls what the surface does not offer: {missing}"


async def test_a_persons_line_reaches_their_channel_at_the_interval_they_chose_or_never(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await stated(http, base, keys)
    ada = bearer(keys["idn_ada"])
    await http.put(f"{base}/me/relief/settings", headers=ada, json={"line": "never"})
    assert await given.reading.own.tick(TENANT, frozenset({"invoice"})) == []
    await http.put(
        f"{base}/me/relief/settings",
        headers=ada,
        json={"line": "day", "channel": "channel.chat", "address": "D-ada"},
    )
    given.clock.current = given.clock.current.replace(hour=9)
    assert await given.reading.own.tick(TENANT, frozenset({"invoice"})) == ["idn_ada"]
    assert await given.reading.own.tick(TENANT, frozenset({"invoice"})) == [], "once a day"
    (line,) = [s for s in given.deliveries.said if s.address == "D-ada"]
    assert line.text.endswith("regained this week.")
