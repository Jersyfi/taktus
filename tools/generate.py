"""`make generate`: regenerate what is generated. Runs in the project environment.

Three things are generated today, each never edited by hand:

- `api/openapi.yaml`, the OpenAPI 3.1 document of Taktus' own REST interface, from the FastAPI
  application under `src/taktus/adapters/driving/rest` — built at the root; the path prefix an
  instance is served under is a server variable of the document.
  `tests/adapters/rest/test_openapi.py` fails when the file differs from what this script writes.
- `web/src/lib/generated/fixtures.json`, what the web app's tests draw: the visual vocabulary
  and a run level drawn by `reporting` from example facts that use every method kind, every
  exactness class and every motion, the process level of the same steps, an overview, the
  origin of a result, what the routes of what keeps the operation running answer, and the
  spend per step and a model trial as their routes answer, and the catalogue and the value
  streams (ADR-0063, ADR-0064, ADR-0067, ADR-0068, ADR-0121, ADR-0148, ADR-0149, ADR-0159).
  The web app's tests hold what it draws to these glyphs;
  `tests/components/reporting/test_run_level.py` fails when the file differs from what this
  script writes. The web app itself reads the vocabulary and every
  level from the surface.
- `src/taktus/composition/shipped.json`, the list of what the release ships: every connector's
  capabilities and operations from its own declaration, and every worker's `CAPABILITIES`
  (ADR-0118). Every lack is classified against it. `tests/composition/test_shipped.py` fails
  when the file differs from what this script writes.

The shared kernel's Python types under src/taktus/shared/ are a hand-written binding checked
against the schemas by tests/contract, not generated (docs/architecture/project-structure.md
§4 says why).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = ROOT / "api" / "openapi.yaml"
FIXTURES = ROOT / "web" / "src" / "lib" / "generated" / "fixtures.json"


def openapi_document() -> str:
    from taktus.adapters.driving.rest import build_app

    # The document depends on the routes alone; no service is called to produce it.
    app = build_app(_NoServices(), prefix="/")  # type: ignore[arg-type]
    return yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True, width=100)


def web_fixtures() -> str:
    from datetime import UTC, datetime

    from taktus.components.reporting.domain.model import (
        DecisionFacts,
        OriginFacts,
        OverviewFacts,
        PlannedStep,
        ProcessFacts,
        ProcessStepFacts,
        ProcessSummary,
        RunActivity,
        RunAtVersion,
        RunCount,
        RunFacts,
        RunningStep,
        Statement,
        StepFacts,
        VersionRef,
        Wait,
    )
    from taktus.components.reporting.domain.model.vocabulary import VOCABULARY
    from taktus.components.reporting.domain.service.levels import (
        origin_level,
        overview_level,
        process_level,
        run_level,
    )
    from taktus.shared.v1 import Autonomy, ConsumptionQuantities, DecisionStatus, Provenance

    at = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
    # The exactness statement every level shows, generated from an example bundle as the
    # process component generates it for any version (UC-6.9).
    from taktus.components.process.application.service.register_version import statement_of

    example = yaml.safe_load((ROOT / "examples/processes/six-times-seven.yaml").read_text())
    statement = Statement.model_validate(statement_of(example).as_document())

    def step(
        name: str, method: str, exactness: str | None, state: str, **more: object
    ) -> StepFacts:
        return StepFacts.model_validate(
            {"id": name, "method": method, "exactness": exactness, "state": state, **more}
        )

    facts = RunFacts(
        id="run_example",
        tenant="default",
        process_version="example@1",
        state="running",
        consumed=ConsumptionQuantities.model_validate(
            {"tokens_in": 1200, "tokens_out": 300, "currency": {"eur": 0.04}}
        ),
        steps=(
            step("load", "rule", "exact", "succeeded"),
            step("score", "statistics", "sourced", "running", depends_on=["load"]),
            step("classify", "ml", "tolerant", "failed", depends_on=["load"]),
            step("embed", "neural", "free", "stopped", depends_on=["load"]),
            step(
                "draft",
                "llm",
                "free",
                "running",
                depends_on=["score"],
                consumption={"tokens_in": 1200, "tokens_out": 300},
            ),
            step("build", "worker", "tolerant", "rejected", depends_on=["draft"]),
            step("review", "human", None, "running", depends_on=["draft"]),
            step(
                "pipeline",
                "wait",
                None,
                "waiting_human",
                depends_on=["review"],
                wait=Wait(
                    account="wait.human",
                    cause="awaiting_decision",
                    since=at,
                    role="finance.lead",
                    requests=("dr_example",),
                ),
                decisions=[DecisionFacts(id="dr_example", status=DecisionStatus.OPEN)],
            ),
            step("check", "rule", "exact", "admitted", depends_on=["pipeline"]),
            step("close", "rule", "exact", "planned", depends_on=["check"]),
        ),
        created_at=at,
        updated_at=at,
        exactness=statement,
    )
    process = ProcessFacts(
        id="example",
        tenant="default",
        name="Example",
        version="1",
        autonomy=Autonomy.model_validate(
            {
                "level": 2,
                "reason": "a person confirms each step",
                "toward_next": "twenty runs without a result defect",
            }
        ),
        steps=tuple(
            ProcessStepFacts(
                id=s.id,
                method=s.method,
                exactness=s.exactness,
                reason=f"the {s.method} suits {s.id}",
                depends_on=s.depends_on,
                # A person's step names its role, never a person (ADR-0146).
                role="reviewer" if s.method == "human" else None,
                expertise=("the release's scope",) if s.method == "human" else (),
            )
            for s in facts.steps
        ),
        versions=(VersionRef(version="1", active=True),),
        runs=(
            RunAtVersion(
                id="run_example",
                tenant="default",
                state="running",
                running=("score", "draft", "review"),
                created_at=at,
            ),
        ),
        exactness=statement,
    )
    overview = OverviewFacts(
        tenant="default",
        processes=(
            ProcessSummary(
                id="example",
                name="Example",
                active_version="1",
                autonomy_level=2,
                steps=tuple(
                    PlannedStep(
                        id=s.id, method=s.method, exactness=s.exactness, depends_on=s.depends_on
                    )
                    for s in facts.steps
                ),
                exactness=statement,
            ),
            ProcessSummary(id="quiet", name="Quiet", active_version="3", autonomy_level=4),
        ),
        counts=(RunCount(tenant="default", process_version="example@1", working=1, waiting=1),),
        runs=(
            RunActivity(
                id="run_example",
                tenant="default",
                process_version="example@1",
                state="running",
                running=tuple(
                    RunningStep(id=s.id, method=s.method, exactness=s.exactness)
                    for s in facts.steps
                    if s.state == "running"
                ),
            ),
        ),
    )
    digest = "sha256:" + "0" * 64
    read = {"kind": "source", "capability": "repository.files", "ref": "main:README.md"}
    origin = origin_level(
        OriginFacts(
            tenant="default",
            run_id="run_example",
            step_id="draft",
            records=(
                Provenance.model_validate(
                    {
                        "id": "prv_draft",
                        "run_id": "run_example",
                        "step_id": "draft",
                        "process_version": "example@1",
                        "method": "llm",
                        "exactness": "free",
                        "model": "model@1",
                        "inputs": [
                            {
                                "kind": "result",
                                "run_id": "run_example",
                                "step_id": "score",
                                "digest": digest,
                                "observed_at": at,
                            }
                        ],
                        "outputs": ["draft.md"],
                        "result_digest": digest,
                        "ledger_seq": 9,
                        "recorded_at": at,
                    }
                ),
                Provenance.model_validate(
                    {
                        "id": "prv_score",
                        "run_id": "run_example",
                        "step_id": "score",
                        "process_version": "example@1",
                        "method": "statistics",
                        "exactness": "sourced",
                        "inputs": [{**read, "digest": digest, "observed_at": at}],
                        "outputs": [],
                        "result_digest": digest,
                        "ledger_seq": 7,
                        "recorded_at": at,
                    }
                ),
            ),
        )
    )
    if origin is None:
        raise SystemExit("the example result has no origin to draw")
    document = {
        "vocabulary": VOCABULARY.document(),
        "overview": overview_level(overview).document(),
        "run_level": run_level(facts).document(),
        "process_level": process_level(process).document(),
        "origin": origin.document(),
        "takeover": takeover_fixtures(at, step),
        "governance": governance_fixtures(at, process_level(process).process),
        "operation": operation_fixtures(),
        "acting": acting_fixtures(at),
        "spend": spend_fixtures(),
        "views": views_fixtures(),
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def views_fixtures() -> dict[str, Any]:
    """What the catalogue and the value streams draw, written by the reporting component's own
    functions (ADR-0159): a catalogue with an entry a reply can start and one that needs an
    input, the map of three streams, and one stream as role swimlanes."""
    from taktus.components.reporting.domain.service import streams as v
    from taktus.components.reporting.domain.service.catalogue import (
        CatalogueFacts,
        CatalogueInput,
        catalogue,
    )

    listed = catalogue(
        [
            CatalogueFacts(
                process="daily",
                name="Daily report",
                description="The figures of yesterday.",
                version="daily@3",
                level=3,
            ),
            CatalogueFacts(
                process="offer",
                name="An offer",
                version="offer@1",
                level=2,
                inputs=(CatalogueInput(name="client", description="who asks", required=True),),
                roles=("sales",),
            ),
        ],
        agent_may_start=False,
        chat_word="start",
    )
    order = v.ProcessFacts(
        process="order",
        name="Order",
        version="order@2",
        level=3,
        steps=(
            v.StepFacts(id="read", method="llm", exactness="tolerant", fallback_role="sales"),
            v.StepFacts(id="price", method="rule", exactness="exact"),
            v.StepFacts(id="accept", method="human", role="sales"),
        ),
        runs=(v.RunFacts(lead_seconds=3600, blocked={"wait.human": 1800}),),
        waits={"sales": 1800},
    )
    invoice = v.ProcessFacts(
        process="invoice",
        name="Invoice",
        version="invoice@1",
        level=2,
        steps=(
            v.StepFacts(id="book", method="rule", exactness="exact"),
            v.StepFacts(id="release", method="human", role="accounting"),
        ),
        waits={"accounting": 3600},
    )
    budget = v.ProcessFacts(process="budget", name="Budget", version="budget@1", level=1)
    loose = v.ProcessFacts(process="loose", name="Loose")
    roles = {
        "sales": v.RoleFacts(holders=3, units=("acme/sales",)),
        "accounting": v.RoleFacts(holders=1, units=("acme/finance",)),
    }
    cash = v.StreamFacts(
        stream="order-to-cash",
        revision=1,
        name="Order to cash",
        kind="core",
        trigger="A customer wants to buy",
        outcome="the customer has what they paid for",
        role="sales-lead",
        processes=("order", "invoice"),
    )
    plan = v.StreamFacts(
        stream="planning",
        revision=1,
        name="Planning",
        kind="management",
        trigger="A year begins",
        outcome="the budget is set",
        role="executive",
        processes=("budget",),
    )
    processes = [order, invoice, budget, loose]
    return {
        "catalogue": listed.document(),
        "streams": v.stream_map([cash, plan], processes, roles, 30).document(),
        "lanes": v.stream_lanes(cash, processes, roles).document(),
    }


def takeover_fixtures(at: Any, step: Any) -> dict[str, Any]:
    """What the take-over of a running step draws (ADR-0128): a run level with a step held and
    one whose take-over lapsed, and the state as `GET /runs/{id}/takeovers/{tko}` answers it —
    the engine's document of kind `takeover.state` (§3)."""
    from datetime import timedelta

    from taktus.components.reporting.domain.model import (
        RunFacts,
        TakeoverFacts,
        Wait,
    )
    from taktus.components.reporting.domain.service.levels import run_level
    from taktus.shared.v1 import ConsumptionQuantities

    until = at + timedelta(hours=8)
    taken = RunFacts(
        id="run_taken",
        tenant="default",
        process_version="example@1",
        state="waiting_human",
        consumed=ConsumptionQuantities.model_validate({"tokens_in": 900}),
        steps=(
            step("load", "rule", "exact", "succeeded"),
            step("build", "worker", "tolerant", "running", depends_on=["load"]),
            step(
                "fix",
                "worker",
                "tolerant",
                "waiting_human",
                depends_on=["load"],
                wait=Wait(account="wait.human", cause="taken_over", since=at),
                takeover=TakeoverFacts(id="tko_example", standing="held", until=until),
            ),
            step(
                "lint",
                "worker",
                "tolerant",
                "stopped",
                depends_on=["load"],
                takeover=TakeoverFacts(id="tko_lapsed", standing="lapsed"),
            ),
        ),
        created_at=at,
        updated_at=at,
    )
    state = {
        "kind": "takeover.state",
        "takeover": "tko_example",
        "run_id": "run_taken",
        "step_id": "fix",
        "process_version": "example@1",
        "held_until": until.isoformat(),
        "goal": "Fix the failing test in the parser",
        "acceptance": ["the suite passes", "no test is skipped"],
        "inputs": {"repository": "example/repo", "branch": "main"},
        "credentials": ["REPOSITORY_TOKEN"],
        "checkpoint": "ckpt/run_taken/fix/2",
        "artifacts": [
            {
                "id": "patch.diff",
                "kind": "patch",
                "digest": "sha256:" + "0" * 64,
                "media_type": "text/x-diff",
                "title": "The patch so far",
            }
        ],
    }
    return {"level": run_level(taken).document(), "state": state}


def governance_fixtures(at: Any, process: Any) -> dict[str, Any]:
    """What the governance pages draw, written by the surface's own functions (ADR-0122): the
    answer of `GET /autonomy`, of `GET /findings`, a need as `GET /owner/reports` answers it,
    and the tenants as `GET /administration/tenants` answers them."""
    from datetime import timedelta

    from taktus.adapters.driving.rest import autonomy, review, tenants
    from taktus.components.governance.domain.model import (
        Figures,
        Incident,
        IncidentKind,
        Lowered,
        Rate,
        Unit,
        shipped_limits,
    )
    from taktus.components.reporting.application.query import view as report_view
    from taktus.components.reporting.application.service import Outgoing
    from taktus.components.reporting.domain.model import (
        Classified,
        Finding,
        Lack,
        Occurrence,
        Offered,
        Report,
        ReportKind,
    )
    from taktus.components.reporting.domain.service import texts
    from taktus.ports.persistence import TenantEntry

    def rate(days: int, released: int, corrected: int, rejected: int) -> Rate:
        return Rate(
            window=timedelta(days=days),
            since=at - timedelta(days=days),
            decided=released + corrected + rejected,
            released=released,
            corrected=corrected,
            rejected=rejected,
        )

    figures = [
        Figures(
            unit=Unit(process_id="example"),
            at=at,
            week=rate(7, 1, 1, 2),
            month=rate(28, 9, 1, 2),
            counted_since=at - timedelta(days=20),
        ),
        Figures(
            unit=Unit(process_id="example", action="mail.send"),
            at=at,
            week=rate(7, 0, 0, 0),
            month=rate(28, 3, 0, 0),
            counted_since=at - timedelta(days=12),
        ),
    ]
    lowering = Incident(
        id="inc_example",
        tenant="default",
        kind=IncidentKind.CORRECTIONS,
        process_id="example",
        process_version="example@1",
        run_id="run_example",
        rule="corrections.rate",
        facts={
            "rate": 0.75,
            "limit": 0.25,
            "unit": "process",
            "level_before": "2",
            "level_after": "1",
        },
        raised_at=at,
    )
    processes = [autonomy.process_document(process, Lowered(level=1), figures, [], [lowering])]

    def finding(lacking: str, run: str) -> Finding:
        return Finding(
            lack=Lack(cause="no_worker", lacking=lacking),
            occurrences=(Occurrence(run_id=run, step_id="draft", since=at, seconds=600),),
        )

    candidate, local = finding("code.review", "run_example"), finding("code.edit", "run_example")
    outgoing = [
        Outgoing(candidate, candidate, texts.shown(candidate), (), Classified(kind="product")),
        Outgoing(
            local,
            local,
            texts.shown(local),
            (),
            Classified(kind="configuration", adapters=("coder",)),
        ),
    ]
    need = Report(
        id="need_example",
        tenant="default",
        kind=ReportKind.NEED,
        title="A token for the live test",
        needed=("A token in the environment `live`.",),
        steps=("Create it.", "Store it."),
        standing_still=("The live test.",),
        due=at.date() + timedelta(days=7),
        offered=(Offered(id="done", label="It is done"),),
        raised_at=at,
    )
    return {
        "autonomy": autonomy.autonomy_document(processes, shipped_limits("default")),
        "findings": review.findings_document("review", outgoing, frozenset({candidate.lack.key})),
        "reports": {"reports": [report_view(need, "idn_owner")]},
        "tenants": {
            "tenants": [
                tenants.tenant_document(TenantEntry(id="default", name="Default", created_at=at)),
                tenants.tenant_document(
                    TenantEntry(id="tnt_example", name="Acme Software", created_at=at)
                ),
            ]
        },
    }


def acting_fixtures(at: Any) -> dict[str, Any]:
    """What the pages of what acts, what depends on it and how a process really runs draw,
    written by the reporting component's own functions (ADR-0147): the register and its
    inventory, an adapter removed, a wrong result followed forward, where data goes, and the
    variants of a process."""
    from datetime import timedelta

    from taktus.components.reporting.domain.model.acting import (
        ActorFacts,
        ActorUse,
        RemovalSeen,
        Used,
    )
    from taktus.components.reporting.domain.service import acting
    from taktus.components.reporting.domain.service import variants as v
    from taktus.shared.v1 import ExactnessClass, LedgerEntry, LedgerRefs, Provenance

    def use(process: str, step: str, level: int, breaks: bool, role: str | None = None) -> Any:
        return ActorUse(
            process_id=process,
            version="1",
            step_id=step,
            served="tickets.read" if not role else "purpose summary",
            level=level,
            exactness=ExactnessClass.SOURCED if not role else ExactnessClass.FREE,
            without="breaks" if breaks else "degrades",
            instead=None if breaks or role else "connector.mirror",
            role=role,
            reason="no other adapter serves tickets.read and the step names no fallback"
            if breaks
            else "another adapter, or a person of the role, takes the step",
        )

    tested = RemovalSeen(verdict="changed", tested_at=at - timedelta(days=3))
    facts = [
        ActorFacts(
            adapter="connector.tickets",
            family="connector",
            serves=("tickets",),
            maturity="verified",
            removal=RemovalSeen(verdict="broke", tested_at=at - timedelta(days=3)),
            uses=(use("billing", "fetch", 2, True), use("support", "read", 3, False)),
            used=Used(days=28, steps=412, runs=206),
        ),
        ActorFacts(
            adapter="model.writer",
            family="model",
            serves=("summary",),
            maturity="verified",
            removal=tested,
            location="elsewhere",
            uses=(use("support", "draft", 2, False, role="support-lead"),),
            used=Used(days=28, steps=198, runs=198, tokens=241000, money={"eur": 3.12}),
        ),
        ActorFacts(
            adapter="worker.coder",
            family="worker",
            serves=("vcs.write",),
            maturity="verified",
            removal=tested,
            used=Used(days=28),
        ),
    ]
    register = acting.register("default", facts, "eu")
    entry = LedgerEntry.model_validate(
        {
            "seq": 9,
            "ts": at,
            "kind": "egress.delivery",
            "prev_hash": "sha256:" + "0" * 64,
            "hash": "sha256:" + "1" * 64,
            "refs": {"tenant": "default", "run_id": "run_remind", "step_id": "letter"},
        }
    )

    def record(id: str, run: str, step: str, pv: str, reads: tuple[str, str] | None) -> Any:
        return Provenance.model_validate(
            {
                "id": id,
                "run_id": run,
                "step_id": step,
                "process_version": pv,
                "method": "rule",
                "exactness": "sourced",
                "inputs": []
                if reads is None
                else [
                    {
                        "kind": "result",
                        "run_id": reads[0],
                        "step_id": reads[1],
                        "digest": "sha256:" + "a" * 64,
                        "observed_at": at,
                    }
                ],
                "outputs": [],
                "result_digest": "sha256:" + "b" * 64,
                "ledger_seq": 3,
                "recorded_at": at,
            }
        )

    wrong = acting.wrong_result(
        "run_bill",
        "compute",
        record("p0", "run_bill", "compute", "billing@1", None),
        [
            record("p1", "run_bill", "invoice", "billing@1", ("run_bill", "compute")),
            record("p2", "run_remind", "letter", "reminders@2", ("run_bill", "invoice")),
        ],
        [entry],
    )
    travelled = v.Travelled()
    seq = 0
    for i in range(12):
        run = f"run_{i:02d}"
        path = (
            [("step.awaiting", "classify", "fell_back")]
            if i < 3
            else [("step.retried", "book", "after_failure")]
            if i < 5
            else []
        )
        for kind, step, outcome in [*path, ("run.finished", None, None)]:
            seq += 1
            v.fold(
                travelled,
                LedgerEntry.model_validate(
                    {
                        "seq": seq,
                        "ts": at,
                        "kind": kind,
                        "prev_hash": "sha256:" + "0" * 64,
                        "hash": "sha256:" + "1" * 64,
                        "refs": LedgerRefs(
                            tenant="default",
                            run_id=run,
                            step_id=step,
                            process_version="invoices@1",
                        ).document(),
                        **({} if outcome is None else {"outcome": outcome}),
                    }
                ),
            )
    variants = v.variants(
        "invoices",
        "1",
        ("classify", "approve", "book"),
        travelled,
        [
            v.WaitFact(step_id="approve", account="wait.human", cause="c", seconds=7200 * 6),
            v.WaitFact(step_id="classify", account="limit.provider", cause="c", seconds=1800),
        ],
        {"accounts-approver": 3},
        {"approve": "accounts-approver"},
    )
    return {
        "register": register.document(),
        "inventory": acting.inventory(register, at),
        "remove": acting.remove_view("connector.tickets", facts[0]).document(),
        "wrong_result": wrong.document(),
        "residency": acting.residency_view(facts, "eu").document(),
        "variants": variants.document(),
    }


def operation_fixtures() -> dict[str, object]:
    """What the surface answers on the routes of what keeps the operation running (ADR-0121),
    written by the same functions the routes answer with, from example records: an open
    missing-run incident and a closed overdue one, a lost claim, a failing backup, a red and a
    yellow signal and one not measured, and the daily report that lists them."""
    from datetime import UTC, datetime, timedelta

    from taktus.adapters.driving.rest.operation import (
        alert_view,
        backup_view,
        incident_view,
        signal_view,
        summary,
    )
    from taktus.components.governance.domain.model import (
        Happening,
        Incident,
        IncidentKind,
        IncidentState,
        RunSeen,
    )
    from taktus.components.reporting.application.query import view as report_view
    from taktus.components.reporting.application.service import Alerted, BackupWatched
    from taktus.components.reporting.domain.model import (
        BackupRun,
        BackupState,
        ClaimLost,
        Corridor,
        Judged,
        Level,
        Offered,
        Report,
        ReportKind,
    )
    from taktus.components.reporting.domain.service import alerts as rule

    now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    hour = timedelta(hours=1)
    incidents = [
        Incident(
            id="inc_missing",
            tenant="default",
            kind=IncidentKind.MISSING,
            process_id="watch",
            process_version="watch@1",
            expected_at=now - 2 * hour,
            last_run=RunSeen(at=now - 3 * hour, run_id="run_watch_3", kind="run.started"),
            rule="expected.slot",
            facts={"schedule": "0 * * * *", "grace_seconds": 900.0},
            raised_at=now - hour,
            timeline=(
                Happening(
                    at=now - hour,
                    what="missed",
                    expected_at=now - 2 * hour,
                    deadline=now - 2 * hour + timedelta(minutes=15),
                ),
            ),
        ),
        Incident(
            id="inc_overdue",
            tenant="default",
            kind=IncidentKind.OVERDUE,
            process_id="example",
            process_version="example@1",
            expected_at=now - 30 * hour,
            run_id="run_example",
            rule="expected.bound",
            facts={"bound_seconds": 3600.0},
            raised_at=now - 29 * hour,
            state=IncidentState.CLOSED,
            closed_at=now - 20 * hour,
            timeline=(Happening(at=now - 20 * hour, what="closed"),),
        ),
    ]
    lost = rule.claims_lost([ClaimLost(seq=7, at=now - 4 * hour, run_id="run_example")], {})
    alerted = [
        Alerted(alert=a, report=None, closed=False, delivered=False, reason="no_channel")
        for a in lost
    ]
    state = BackupState(
        watched_since=now - 240 * hour,
        expected_hours=26,
        last_ok=BackupRun(name="taktus-20261020T020000Z", at=now - 31 * hour),
        failed=(BackupRun(name="taktus-20261021T020000Z", at=now - 7 * hour, reason="store"),),
        failed_count=1,
    )
    backup = rule.backup(state, now)
    if backup is not None:
        alerted.append(
            Alerted(alert=backup, report=None, closed=False, delivered=False, reason="no_channel")
        )
    watched = BackupWatched(state=state, next_due=rule.backup_due(state), alert=backup)

    def corridor(signal: str, process: str, step: str, **more: object) -> Corridor:
        return Corridor.model_validate(
            {
                "id": f"{signal}@1",
                "tenant": "default",
                "signal": signal,
                "version": 1,
                "process": process,
                "step": step,
                "bounds": "fixed",
                "yellow": 5,
                "red": 10,
                "role": "sales",
                "case": f"https://tracker.example/cases/{signal}",
                "changed_at": now - 240 * hour,
                **more,
            }
        )

    def judged(c: Corridor, level: Level, **more: object) -> Judged:
        return Judged.model_validate({"signal": c.signal, "corridor": c.id, "level": level, **more})

    late = corridor("orders.late", "orders", "count")
    open_ = corridor(
        "tickets.open", "tickets", "count", about={"kind": "department", "name": "support"}
    )
    stock = corridor("stock.low", "stock", "measure", direction="below", yellow=20, red=10)
    measured = {
        "yellow_at": 5.0,
        "red_at": 10.0,
        "step_id": "count",
        "at": now - hour,
    }
    signals = [
        (
            late,
            judged(
                late,
                Level.RED,
                value=12.0,
                run_id="run_orders_9",
                process_version="orders@2",
                **measured,
            ),
        ),
        (
            open_,
            judged(
                open_,
                Level.YELLOW,
                value=7.0,
                run_id="run_tickets_4",
                process_version="tickets@1",
                **measured,
            ),
        ),
        (stock, judged(stock, Level.UNMEASURED, reason="no_measurement")),
    ]
    daily = Report(
        id="signals-2026-10-22",
        tenant="default",
        kind=ReportKind.SIGNALS,
        title="Daily report: 2 signals deviate, 1 not measured",
        needed=(
            "orders.late is red: 12 above 10, run run_orders_9, step count.",
            "tickets.open is yellow: 7 above 5, run run_tickets_4, step count.",
            "stock.low is not measured: no_measurement.",
        ),
        steps=("Open the case each line names: that is where a deviation is worked.",),
        standing_still=(
            "1 red signals have open incidents; whatever they steer waits for a person.",
        ),
        due=now.date(),
        offered=(Offered(id="done", label="Done"),),
        raised_at=now - 3 * hour,
    )
    return {
        "summary": summary(
            "default", incidents, [j for _, j in signals], (alerted, watched, daily)
        ),
        "summary_withheld": summary("default", incidents, [j for _, j in signals], None),
        "incidents": {"incidents": [incident_view(i) for i in incidents]},
        "alerts": {"alerts": [alert_view(a) for a in alerted]},
        "backup": backup_view(watched),
        "signals": {"signals": [signal_view(c, j) for c, j in signals]},
        "daily_report": report_view(daily, "idn_owner"),
    }


def spend_fixtures() -> dict[str, object]:
    """What the routes of spend per step and of model trials answer (ADR-0148, ADR-0149), as
    the documents of the types they answer with: a run of three steps, the same task run with
    another model beside it, the process over a window, a trial of two candidates with one
    case whose results differ, and the trials offered."""
    from datetime import UTC, datetime, timedelta

    from taktus.components.accounting.application.service import (
        CandidateReport,
        CaseOutcome,
        Offer,
        ProcessSpend,
        RunComparison,
        RunSpend,
        StepDifference,
        StepSpend,
        Trial,
        TrialCase,
        TrialRead,
        TrialReport,
    )
    from taktus.components.accounting.domain.service import Meter
    from taktus.shared.v1 import Compression, PriceKinds

    at = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)

    def step(
        step_id: str,
        method: str,
        amount: float | None,
        takte: float,
        kinds: dict[str, int],
        result: str,
        turns: int = 0,
        compression: Compression | None = None,
    ) -> StepSpend:
        tokens = {"draft-model-20261001": PriceKinds(**kinds)} if kinds else {}
        return StepSpend(
            step_id=step_id,
            method=method,
            finished=1,
            meter=Meter(
                tokens=tokens,
                steps={method: 1},
                turns=turns,
                compression=compression,
                compute_seconds={} if kinds else {"cpu.small": 1.5},
            ),
            amount=amount,
            takte=takte,
            outcome="succeeded",
            result="sha256:" + result * 64,
        )

    left = RunSpend(
        run_id="run_replies_1",
        process_version="replies@3",
        currency="usd",
        table="2026-10",
        steps=(
            step("read", "rule", 0.0, 1.0, {}, "a"),
            step(
                "draft",
                "llm",
                0.0184,
                12.4,
                {"input": 1200, "cache_read": 8000, "cache_write": 400, "output": 310},
                "b",
                turns=3,
                compression=Compression(before=12000, after=9600),
            ),
            step("check", "llm", 0.0021, 1.6, {"input": 420, "output": 12}, "c", turns=1),
        ),
        amount=0.0205,
        takte=15.0,
        calibration="uncalibrated",
    )
    right = left.model_copy(
        update={
            "run_id": "run_replies_2",
            "steps": (
                left.steps[0],
                step("draft", "llm", 0.0071, 5.2, {"input": 1180, "output": 280}, "d", turns=2),
                left.steps[2],
            ),
            "amount": 0.0092,
            "takte": 7.8,
        }
    )
    comparison = RunComparison(
        left=left,
        right=right,
        steps=(
            StepDifference(
                step_id="read", amount=0.0, tokens_in=0, tokens_out=0, turns=0, same_result=True
            ),
            StepDifference(
                step_id="draft",
                amount=-0.0113,
                tokens_in=-8420,
                tokens_out=-30,
                turns=-1,
                same_result=False,
            ),
            StepDifference(
                step_id="check", amount=0.0, tokens_in=0, tokens_out=0, turns=0, same_result=True
            ),
        ),
        amount=-0.0113,
    )
    process = ProcessSpend(
        process_id="replies",
        since=at - timedelta(days=30),
        until=at,
        runs=14,
        steps=tuple(s.model_copy(update={"finished": 14}) for s in left.steps),
        amounts={"usd": 0.287},
    )
    candidates = ("model.fast", "model.careful")
    outcome = {
        "model.fast": CaseOutcome(
            case="replies/late",
            run_id="trl_1-0-0",
            state="finished",
            passed=True,
            amount=0.0071,
            tokens_in=1180,
            tokens_out=280,
            wall_seconds=4.2,
            results={"draft": "sha256:" + "d" * 64},
        ),
        "model.careful": CaseOutcome(
            case="replies/late",
            run_id="trl_1-1-0",
            state="finished",
            passed=True,
            amount=0.0184,
            tokens_in=9600,
            tokens_out=310,
            wall_seconds=9.8,
            results={"draft": "sha256:" + "b" * 64},
        ),
    }
    trial = Trial(
        id="trl_1",
        purpose="drafting",
        candidates=candidates,
        occasion="introduced",
        started_at=at,
        cases=(TrialCase(key="replies/late", process_version="replies@3", case="late"),),
        runs={m: {"replies/late": outcome[m].run_id} for m in candidates},
    )
    report = TrialReport(
        purpose="drafting",
        candidates=tuple(
            CandidateReport(
                model=m,
                cases=(outcome[m],),
                passed=1,
                amount=outcome[m].amount,
                currency="usd",
                tokens_in=outcome[m].tokens_in,
                tokens_out=outcome[m].tokens_out,
                wall_seconds=outcome[m].wall_seconds or 0.0,
            )
            for m in candidates
        ),
        differing=("replies/late",),
    )
    offer = Offer(
        purpose="triage",
        occasion="changed",
        model="model.fast",
        candidates=candidates,
        reason="model.fast answered as fast-20261001 and answers as fast-20261101 since then",
        since=at - timedelta(days=2),
    )
    return {
        "run": left.document(),
        "comparison": comparison.document(),
        "process": process.document(),
        "trial": TrialRead(trial=trial, report=report, settled=True).document(),
        "trials": {"trials": [trial.document()], "offers": [offer.document()]},
    }


class _NoServices:
    """Stands in for `RestServices` while the document is produced; nothing is called."""

    roles: tuple[str, ...] = ()
    tenants: tuple[str, ...] = ("default",)
    leading = False
    findings_intake = None


def main() -> int:
    document = openapi_document()
    OPENAPI.parent.mkdir(parents=True, exist_ok=True)
    changed = not OPENAPI.is_file() or OPENAPI.read_text(encoding="utf-8") != document
    OPENAPI.write_text(document, encoding="utf-8")
    print(f"generate: {OPENAPI.relative_to(ROOT)} {'written' if changed else 'unchanged'}")
    fixtures = web_fixtures()
    FIXTURES.parent.mkdir(parents=True, exist_ok=True)
    changed = not FIXTURES.is_file() or FIXTURES.read_text(encoding="utf-8") != fixtures
    FIXTURES.write_text(fixtures, encoding="utf-8")
    print(f"generate: {FIXTURES.relative_to(ROOT)} {'written' if changed else 'unchanged'}")
    from taktus.composition import shipped

    listed = shipped.text(shipped.build(ROOT))
    changed = not shipped.LIST.is_file() or shipped.LIST.read_text(encoding="utf-8") != listed
    shipped.LIST.write_text(listed, encoding="utf-8")
    print(f"generate: {shipped.LIST.relative_to(ROOT)} {'written' if changed else 'unchanged'}")
    print("  shared kernel: a checked binding under src/taktus/shared/ (tests/contract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
