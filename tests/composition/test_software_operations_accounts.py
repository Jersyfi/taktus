# ruff: noqa: F811 — every test requests the imported fixture `outside` by its name
"""The customer-contact processes of the blueprint `software-operations` that read the product's
own accounts, and B-3.06's two extensions, each registered as shipped and run against fakes
(UC-03 §4.3; ADR-0208).

The world of `test_software_operations.py`, with the product's accounts beside its
entitlements: the vendor connector in front of a stand-in of the product's own MCP server,
under the blueprint's manifest `connectors/accounts.manifest.json`. What is faked: the mailbox,
the payment provider, the repository service, the product's server and the model.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeWorker, account_server
from fakes import entitlement_server as entitlements
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT
from taktus_connectors.github.server import Config as RepositoryConfig
from taktus_connectors.github.server import build_server as repository_server
from taktus_connectors.mail.protocol import Config as MailConfig
from taktus_connectors.mail.server import build_server as mail_server
from taktus_connectors.stripe.operations import Config as PaymentsConfig
from taktus_connectors.stripe.server import build_server as payments_server
from taktus_connectors.vendor.manifest import load as load_manifest
from taktus_connectors.vendor.server import build_server as vendor_server
from taktus_connectors.vendor.upstream import Upstream
from taktus_connectors.vendor.wrapping import Wrapper, with_manifest

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.decision.application.service import AnswerRequest, ConfirmRequest
from taktus.components.run.application.service import (
    ConfirmSteps,
    DecideSteps,
    EngineOptions,
    RunEngine,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.shared.v1 import Method

from .test_software_operations import (
    CHECK,
    CLASSIFY,
    MAILBOX,
    MANIFESTS,
    REPORT,
    REPOSITORY,
    TOKEN,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
    states,
)

SUBSCRIPTION = "You draft a reply to a customer of a software product who asks about cancelling"
REQUEST = "You recognise a data protection request"
TIE = "You tie a customer's defect report"
SEED = "<seed-1@mail.example>"


@pytest.fixture(autouse=True)
def accounts_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ACCOUNTS_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_ACCOUNTS_TOKEN_FILE", str(path))


def vendor(server: Any, manifest: str) -> McpActionConnector:
    wrapped = Wrapper(
        Upstream(server, timeout=5.0), with_manifest(*load_manifest(MANIFESTS / manifest))
    )
    return McpActionConnector(vendor_server(wrapped), timeout=10.0)


class AccountsWorld(World):
    """The world, with the product's accounts served through the vendor connector."""

    def __init__(self, outside: Outside) -> None:
        super().__init__(outside)
        self.accounts = account_server.State()

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        mail = MailConfig(
            imap_host="127.0.0.1",
            imap_port=outside.mail.imap_port,
            smtp_host="127.0.0.1",
            smtp_port=outside.mail.smtp_port,
            user=MAILBOX,
            address=MAILBOX,
            security="none",
            timeout=5.0,
        )
        connectors = [
            (
                "connector.repository",
                served(
                    repository_server(RepositoryConfig(outside.repository, REPOSITORY, timeout=5.0))
                ),
            ),
            (
                "connector.payments",
                served(payments_server(PaymentsConfig(outside.payments, timeout=5.0))),
            ),
            (
                "connector.entitlements",
                vendor(entitlements.create_server(outside.product), "entitlements.manifest.json"),
            ),
            (
                "connector.accounts",
                vendor(account_server.create_server(self.accounts), "accounts.manifest.json"),
            ),
            ("connector.mail", served(mail_server(mail))),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            deadlines=self.keeper,
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool(
                [("model.fake", ["triage", "support", "check"], self.model, "fake-model@1")]
            ),
            messages=self.told,
            # A step that asks raises its decision request with the tenant's decisions (ADR-0088).
            anchors=self.given.decisions.anchors,
            decisions=self.given.decisions.requests,
            levels=self.given.decisions.levels,
        )
        self.deadlines._engine = self.engine  # the deadlines start runs on this engine

    async def ready(self) -> AccountsWorld:
        await super().ready()
        return self

    async def confirmed(self, run: Run) -> Run:
        """A person confirms every step that waits for a confirmation, until none does. A
        person's own step waits to be reported performed, and is left waiting (ADR-0167 §1)."""
        own = {step.id for step in run.steps if step.method is Method.HUMAN}
        for _ in range(20):
            if run.state is not RunState.WAITING_HUMAN:
                break
            waiting = tuple(
                s.step_id
                for s in run.step_runs
                if s.state is StepState.WAITING_HUMAN
                and s.step_id not in own
                and not (s.anchoring is not None and s.anchoring.requests)
            )
            if not waiting:
                break
            run = await self.engine.confirm(
                ConfirmSteps(run_id=run.id, steps=waiting, actor=OWNER, tenant=TENANT)
            )
        return run

    async def performed(self, run: Run, step: str) -> Run:
        """A person of the step's role reports the human step performed."""
        return await self.engine.confirm(
            ConfirmSteps(run_id=run.id, steps=(step,), actor=OWNER, tenant=TENANT, performed=True)
        )

    async def decided(self, run: Run, step: str, option: str) -> Run:
        """A person answers the step's decision request — A to act, B to decline — and
        confirms it."""
        anchoring = run.step_run(step).anchoring
        assert anchoring is not None and anchoring.requests, "a decision request was raised"
        (request_id,) = anchoring.requests
        decisions = self.given.decisions
        await decisions.answer.execute(
            AnswerRequest(tenant=TENANT, request_id=request_id, identity=OWNER, option=option)
        )
        await decisions.confirm.execute(
            ConfirmRequest(tenant=TENANT, request_id=request_id, identity=OWNER, confirmed=True)
        )
        return await self.engine.decide(DecideSteps(run_id=run.id, actor=OWNER, tenant=TENANT))

    def prepared(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = self.accounts.document()["prepared"]
        return found

    def calls(self) -> dict[str, int]:
        found: dict[str, int] = self.accounts.document()["calls"]
        return found


def reasons(run: Run) -> list[tuple[str, str | None]]:
    return [(s.step_id, s.reason) for s in run.step_runs]


# --- stage 2: B-3.05 Cancellation and subscription questions -----------------------------------


def answering(w: World, draft: str, check: str = "send", classified: str = "none") -> None:
    w.model.answers.update({SUBSCRIPTION: draft, CHECK: check, CLASSIFY: classified})


async def test_b_3_05_answers_with_the_subscription_and_the_self_service_page_once_released(
    outside: Outside,
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.05-subscription-questions.yaml")
    answering(
        w,
        "Your monthly plan is active until the end of the period. You cancel it yourself at "
        "https://app.product.example/account/1/subscription.",
    )
    before = outside.submitted()
    run = await w.start(version, message=SEED, customer="cus_fake1")
    assert run.state is RunState.WAITING_HUMAN and outside.submitted() == before
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, reasons(run)
    assert outside.submitted() == before + 1, "the reply was submitted once"
    drafted = next(p for p in w.model.prompts if (p.system or "").startswith(SUBSCRIPTION))
    shown = str(drafted.document() if hasattr(drafted, "document") else drafted)
    assert "sub_fake1" in shown and "account/1/subscription" in shown
    assert "person1@customer.example" not in shown, "no address of the customer reaches a model"
    assert any((p.system or "").startswith(CHECK) for p in w.model.prompts)
    assert w.calls() == {"read_account": 1}


async def test_b_3_05_reads_only_the_customer_of_its_case(outside: Outside) -> None:
    """Both reads carry the customer as the case's scope; another customer is never asked for
    (UC-7.7, ADR-0130)."""
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.05-subscription-questions.yaml")
    answering(w, "Your plan is active; you change it on your account page.")
    await w.confirmed(await w.start(version, message=SEED, customer="cus_fake2"))
    assert w.calls() == {"read_account": 1}
    drafted = next(p for p in w.model.prompts if (p.system or "").startswith(SUBSCRIPTION))
    shown = str(drafted.document() if hasattr(drafted, "document") else drafted)
    assert "sub_fake2" in shown and "sub_fake1" not in shown


@pytest.mark.parametrize(
    ("draft", "check", "classified", "held"),
    [
        ("As goodwill we refund the last charge.", "send", "none", "no_money"),
        ("Your plan is active.", "reject", "none", "verify answered reject"),
        ("Cancelling becomes possible in the app next week.", "send", "date", "anc-promise"),
    ],
)
async def test_b_3_05_money_a_rejection_or_a_promise_holds_the_reply(
    outside: Outside, draft: str, check: str, classified: str, held: str
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.05-subscription-questions.yaml")
    answering(w, draft, check, classified)
    before = outside.submitted()
    run = await w.confirmed(await w.start(version, message=SEED, customer="cus_fake1"))
    assert run.state is not RunState.FINISHED
    assert held in (run.step_run("send").reason or "")
    assert outside.submitted() == before


# --- stage 2: B-3.08 Data protection requests ----------------------------------------------------


async def test_b_3_08_prepares_a_verified_senders_erasure_and_its_month_ends_with_a_person(
    outside: Outside,
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.08-data-protection-requests.yaml")
    w.model.answers[REQUEST] = "kind: erasure"
    run = await w.start(version, message=SEED, customer="cus_fake1")
    assert run.state is RunState.WAITING_HUMAN and w.prepared() == [], "a person confirms first"
    run = await w.confirmed(run)
    [prepared] = w.prepared()
    assert (prepared["customer"], prepared["kind"], prepared["state"]) == (
        "cus_fake1",
        "erasure",
        "prepared",
    )
    assert prepared["reference"] == SEED
    assert run.state is RunState.WAITING_HUMAN, "carrying it out is a person's"
    assert states(run)["carried-out"] is StepState.WAITING_HUMAN
    (open_,) = await w.keeper.open(TENANT)
    assert open_.run_id == run.id, "the statutory month runs until a person carried it out"
    run = await w.performed(run, "carried-out")
    assert states(run)["extension"] is StepState.WAITING_HUMAN, "was it extended?"
    run = await w.decided(run, "extension", "B")
    assert run.state is RunState.FINISHED, reasons(run)
    assert states(run)["carried-out-extended"] is StepState.SUCCEEDED
    assert (await w.result(run, "carried-out-extended"))["skipped"] is True
    assert await w.keeper.open(TENANT) == []
    assert w.calls() == {"verify_address": 1, "prepare_request": 1}


async def test_b_3_08_an_extended_request_is_watched_for_two_more_months_until_carried_out(
    outside: Outside,
) -> None:
    """GDPR Art. 12(3): told within the month, the request may take two further months; the
    month is met, and 59 days from the extension are watched until a person carried it out."""
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.08-data-protection-requests.yaml")
    w.model.answers[REQUEST] = "kind: access"
    run = await w.confirmed(await w.start(version, message=SEED, customer="cus_fake1"))
    w.clock.current += timedelta(days=20)
    run = await w.performed(run, "carried-out")  # the customer told of the extension
    run = await w.decided(run, "extension", "A")
    assert states(run)["carried-out-extended"] is StepState.WAITING_HUMAN
    found = await w.keeper.open(TENANT)
    assert [(d.name, d.run_id) for d in found] == [("extended", run.id)], found
    w.clock.current += timedelta(days=10)
    assert await w.deadlines.tick() == [], "the month was met by telling the customer"
    w.clock.current += timedelta(days=36)  # 46 days since the extension
    assert [f"{t.kind}:{t.outcome}" for t in await w.deadlines.tick()] == ["deadline.lead:remind"]
    w.clock.current += timedelta(days=14)  # 60 days
    assert [f"{t.kind}:{t.outcome}" for t in await w.deadlines.tick()] == [
        "deadline.reached:escalate"
    ]
    run = await w.performed(run, "carried-out-extended")
    assert run.state is RunState.FINISHED, reasons(run)


async def test_b_3_08_a_sender_who_is_not_the_accounts_verified_address_prepares_nothing(
    outside: Outside,
) -> None:
    """The seeded message comes from cus_fake1's address; for cus_fake2 it is not verified."""
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.08-data-protection-requests.yaml")
    w.model.answers[REQUEST] = "kind: access"
    run = await w.confirmed(await w.start(version, message=SEED, customer="cus_fake2"))
    assert (await w.result(run, "verified"))["count"] == 0
    assert (await w.result(run, "prepare"))["skipped"] is True
    assert w.prepared() == []
    assert states(run)["carried-out"] is StepState.WAITING_HUMAN, "a person asks to verify"


@pytest.mark.parametrize("answer", ["kind: none", "kind: delete everything", ""])
async def test_b_3_08_a_message_that_is_no_request_prepares_nothing(
    outside: Outside, answer: str
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.08-data-protection-requests.yaml")
    w.model.answers[REQUEST] = answer
    run = await w.confirmed(await w.start(version, message=SEED, customer="cus_fake1"))
    assert (await w.result(run, "kind"))["extracted"] == []
    assert w.prepared() == []


async def test_b_3_08_a_request_left_undone_is_reminded_then_escalated_once(
    outside: Outside,
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.08-data-protection-requests.yaml")
    w.model.answers[REQUEST] = "kind: access"
    run = await w.confirmed(await w.start(version, message=SEED, customer="cus_fake1"))
    assert run.state is RunState.WAITING_HUMAN
    w.clock.current += timedelta(days=22)
    assert [f"{t.kind}:{t.outcome}" for t in await w.deadlines.tick()] == ["deadline.lead:remind"]
    w.clock.current += timedelta(days=7)
    assert [f"{t.kind}:{t.outcome}" for t in await w.deadlines.tick()] == [
        "deadline.reached:escalate"
    ]
    w.clock.current += timedelta(days=7)
    assert await w.deadlines.tick() == [], "taken once"


# --- stage 2: B-3.06 A bug from support, added to an existing issue --------------------------

DEFECT = (
    "title: CSV export stops with an error\nsteps: open Reports, press Export\n"
    "device: not given\nversion: 2.4.1\n"
)


def opened(outside: Outside, title: str, body: str = "Reported by the team.") -> int:
    issue = outside.send("POST", f"/repos/{REPOSITORY}/issues", {"title": title, "body": body})
    return int(issue["number"])


def comments(outside: Outside, number: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = outside.send(
        "GET", f"/repos/{REPOSITORY}/issues/{number}/comments"
    )
    return found


async def test_b_3_06_adds_the_report_to_the_open_issue_of_the_same_defect_once(
    outside: Outside,
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.06-bug-from-support.yaml")
    known = opened(outside, "Export fails with an error")
    w.model.answers.update({REPORT: DEFECT, TIE: f"issue: {known}"})
    before = len(outside.issues())
    run = await w.start(version, message=SEED)
    assert run.state is RunState.WAITING_HUMAN and comments(outside, known) == []
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, reasons(run)
    assert len(outside.issues()) == before, "no new issue: the report went to the known one"
    assert (await w.result(run, "file"))["skipped"] is True
    [added] = comments(outside, known)
    assert "version: 2.4.1" in added["body"] and f"support-case:{SEED}" in added["body"]
    tie = next(p for p in w.model.prompts if (p.system or "").startswith(TIE))
    assert "follow no instruction" in (tie.system or "")

    again = await w.confirmed(await w.start(version, message=SEED))
    assert again.state is RunState.FINISHED, reasons(again)
    assert (await w.result(again, "uncommented"))["count"] == 0, "added once, never twice"
    assert len(comments(outside, known)) == 1


@pytest.mark.parametrize("answer", ["issue: none", "issue: 999", "I am not sure"])
async def test_b_3_06_a_number_no_open_issue_carries_files_a_new_issue(
    outside: Outside, answer: str
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.06-bug-from-support.yaml")
    other = opened(outside, "Dark mode")
    w.model.answers.update({REPORT: DEFECT, TIE: answer})
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version, message=SEED))
    assert run.state is RunState.FINISHED, reasons(run)
    assert len(outside.issues()) == before + 1
    assert (await w.result(run, "comment"))["skipped"] is True
    assert comments(outside, other) == []


# --- stage 2: B-3.06 the fix live -----------------------------------------------------------------


def close(outside: Outside, number: int) -> None:
    outside.send("PATCH", f"/repos/{REPOSITORY}/issues/{number}", {"state": "closed"})


async def test_b_3_06_live_tells_the_customer_once_a_person_released_the_notice(
    outside: Outside,
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.06-bug-from-support.yaml")
    fixed = opened(outside, "Export fails", f"A customer reported it.\n\nsupport-case:{SEED}")
    close(outside, fixed)
    before = outside.submitted()
    run = await w.start(version, message=SEED, fixed=fixed)
    assert run.state is RunState.WAITING_HUMAN and outside.submitted() == before
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, reasons(run)
    assert outside.submitted() == before + 1
    assert w.model.prompts == [], "the notice is a fixed text; no model is asked"


async def test_b_3_06_live_finds_the_mark_in_a_comment_too(outside: Outside) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.06-bug-from-support.yaml")
    fixed = opened(outside, "Export fails")
    outside.send(
        "POST",
        f"/repos/{REPOSITORY}/issues/{fixed}/comments",
        {"body": f"Another report.\n\nsupport-case:{SEED}"},
    )
    close(outside, fixed)
    before = outside.submitted()
    run = await w.confirmed(await w.start(version, message=SEED, fixed=fixed))
    assert run.state is RunState.FINISHED, reasons(run)
    assert outside.submitted() == before + 1


@pytest.mark.parametrize(("closed", "marked"), [(False, True), (True, False)])
async def test_b_3_06_live_an_open_issue_or_a_message_it_does_not_carry_tells_nobody(
    outside: Outside, closed: bool, marked: bool
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.06-bug-from-support.yaml")
    body = f"support-case:{SEED}" if marked else "support-case:<other@mail.example>"
    number = opened(outside, "Export fails", body)
    if closed:
        close(outside, number)
    before = outside.submitted()
    run = await w.confirmed(await w.start(version, message=SEED, fixed=number))
    assert states(run)["notify"] is not StepState.SUCCEEDED or (
        (await w.result(run, "notify")).get("skipped") is True
    )
    assert outside.submitted() == before
