"""`taktusctl findings` end to end (UC-6.12 §2, ADR-0112): an instance that does not send its
findings records them and shows them to its operator, who can send one by hand; and a report a
person writes by hand is checked, shown exactly as it would be sent, and sent only once they
confirm it."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fakes import FakeIdentifiers, FakeMaturities, FakeWorker

from taktus.adapters.driven.clock import SystemClock
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service.ready import missing_sections
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .test_first_slice import PLAIN, taktusctl

TENANT = "default"
PERSON = "idn_operator"


async def a_run_that_lacks_a_worker(state_dir: Path, inputs: dict[str, str] | None = None) -> Run:
    """A run in the development store whose step needs a worker no configured one offers."""
    persistence = MemoryPersistence(state_dir)
    clock = SystemClock()
    engine = RunEngine(
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(state_dir / "objects"),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        provenance=MemoryProvenanceStore(persistence),
        workers=StaticWorkerPool([("worker.shell", FakeWorker())]),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        options=EngineOptions(uncalibrated_margin=0.0),
        maturities=FakeMaturities(),
    )
    step = Step(
        id="review",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("code.review",),
    )
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=(step,),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=PERSON, at=datetime.now(UTC)),
    )
    return await engine.start(
        StartRun(
            plan=plan,
            work={"review": {"task": {"goal": "g", "acceptance": ["a"], "inputs": {}}}},
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="intake@1",
            actor=PERSON,
            tenant=TENANT,
            inputs=inputs or {},
        )
    )


FORM = Path(__file__).resolve().parents[2] / ".github" / "finding-form.md"
"""One repository's form, configured by its operator (ADR-0092)."""


def findings(
    state_dir: Path,
    *args: str,
    form: Path | None = None,
    answer: str | None = None,
    connector: str | None = None,
    level: str = "review",
    intake: str | None = None,
) -> subprocess.CompletedProcess[str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_")}
    shape = {} if form is None else {"TAKTUS_FINDINGS_FORM": str(form)}
    enabled = (
        {}
        if connector is None
        else {"TAKTUS_FINDINGS_CONNECTOR": connector, "TAKTUS_FINDINGS_LEVEL": level}
    )
    if intake is not None:
        enabled = {"TAKTUS_FINDINGS_INTAKE": intake, "TAKTUS_FINDINGS_LEVEL": level}
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "findings", *args],
        capture_output=True,
        text=True,
        input=answer,
        env={**inherited, **PLAIN, "TAKTUS_STATE_DIR": str(state_dir), **shape, **enabled},
        check=False,
    )


def test_the_operator_sees_each_finding_ready_to_send_by_hand(tmp_path: Path) -> None:
    state = tmp_path / "state"
    nothing = findings(state)
    assert nothing.returncode == 0 and "no product findings" in nothing.stdout

    run = asyncio.run(a_run_that_lacks_a_worker(state))
    assert run.state is RunState.ESCALATED
    shown = findings(state)
    assert shown.returncode == 0, shown.stderr
    title, _, body = shown.stdout.partition("\n\n")
    assert title == "Product finding: no worker offers code.review"
    assert "###" not in body, "without a form: the product's plain shape"
    assert run.id in body and PERSON not in shown.stdout

    shaped = findings(state, form=FORM)
    assert shaped.returncode == 0, shaped.stderr
    _, _, body = shaped.stdout.partition("\n\n")
    assert missing_sections(body) == [], "the body has the configured form's sections"
    assert run.id in body and PERSON not in shaped.stdout

    (document,) = json.loads(findings(state, "--json").stdout)
    assert document["lack"] == {"cause": "no_worker", "lacking": "code.review"}
    sent_as = document["occurrences"][0]
    assert sent_as["run_id"] != run.id and sent_as["run_id"] in document["text"]
    assert sent_as["source"] in document["text"] and run.id not in document["text"]
    assert document["on_instance"][0]["run_id"] == run.id and document["withheld"] == []
    assert "\n--- on this instance only, not sent ---\n" in shown.stdout
    assert f"Run `{sent_as['run_id']}` is run `{run.id}`" in shown.stdout


def test_a_report_by_hand_is_checked_then_shown_and_sent_only_once_confirmed(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    asyncio.run(a_run_that_lacks_a_worker(state, inputs={"customer": "Erika Mustermann"}))
    leaky = tmp_path / "leaky.md"
    leaky.write_text("The export for Erika Mustermann fails.\n", encoding="utf-8")
    refused = findings(state, "report", "--title", "Export fails", "--text", str(leaky))
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert "Nothing was sent" in refused.stdout and "tenant value `erika mustermann`" in (
        refused.stdout
    )
    assert "This is exactly what would be sent" not in refused.stdout

    clean = tmp_path / "clean.md"
    clean.write_text("The export step fails after a retry.\n", encoding="utf-8")
    by_hand = findings(state, "report", "--title", "Export fails", "--text", str(clean))
    assert by_hand.returncode == 0, by_hand.stderr
    assert "This is exactly what would be sent:\n\nExport fails\n\n" in by_hand.stdout
    assert "The export step fails after a retry." in by_hand.stdout
    assert "Send the text above by hand." in by_hand.stdout and "Send it?" not in by_hand.stdout

    # Enabled: nothing is sent before the person confirms. The connector's address answers no
    # one, so a send that was attempted would fail.
    nowhere = "http://127.0.0.1:9/mcp"
    declined = findings(
        state,
        "report",
        "--title",
        "Export fails",
        "--text",
        str(clean),
        answer="n\n",
        connector=nowhere,
    )
    assert declined.returncode == 0, declined.stderr
    assert "Send it?" in declined.stdout and "Nothing was sent." in declined.stdout
    confirmed = findings(
        state,
        "report",
        "--title",
        "Export fails",
        "--text",
        str(clean),
        answer="y\n",
        connector=nowhere,
    )
    assert confirmed.returncode == 2, "confirmed, it is sent: here to an address nobody answers"


def test_at_automatic_a_report_by_hand_is_still_shown_and_confirmed(tmp_path: Path) -> None:
    """ADR-0118: `automatic` sends what the rule raised, never a report by hand unasked."""
    state = tmp_path / "state"
    asyncio.run(a_run_that_lacks_a_worker(state))
    clean = tmp_path / "clean.md"
    clean.write_text("The export step fails after a retry.\n", encoding="utf-8")
    declined = findings(
        state,
        "report",
        "--title",
        "Export fails",
        "--text",
        str(clean),
        answer="n\n",
        intake="http://127.0.0.1:9/findings/intake",
        level="automatic",
    )
    assert declined.returncode == 0, declined.stderr
    assert "This is exactly what would be sent" in declined.stdout
    assert "Send it?" in declined.stdout and "Nothing was sent." in declined.stdout


def test_review_shows_each_candidate_and_remembers_local_for_us(tmp_path: Path) -> None:
    """ADR-0118: at `review` each candidate is shown with the text that would leave; "local"
    is remembered for that lack, and it is not offered again."""
    state = tmp_path / "state"
    asyncio.run(a_run_that_lacks_a_worker(state))
    intake = "http://127.0.0.1:9/findings/intake"
    shown = findings(state)
    assert "A product candidate: it may leave" in shown.stdout
    off = findings(state, "review")
    assert off.returncode == 2 and "TAKTUS_FINDINGS_LEVEL" in off.stderr

    not_now = findings(state, "review", answer="not\n", intake=intake)
    assert not_now.returncode == 0, not_now.stderr
    assert "This is exactly what would leave" in not_now.stdout
    assert "Product finding: no worker offers code.review" in not_now.stdout
    assert "offered again at the next review" in not_now.stdout
    local = findings(state, "review", answer="local\n", intake=intake)
    assert "Remembered as local for us" in local.stdout, local.stdout + local.stderr
    again = findings(state, "review", intake=intake)
    assert again.returncode == 0 and "nothing to review" in again.stdout
    assert "Local for us: a person said so in review" in findings(state).stdout
