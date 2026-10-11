"""`taktusctl maturation` end to end (issue #229, ADR-0086): every step's measures read back
from a run history the test wrote, a person's correction recorded as the identity the command
names, and maturation asked for proposals under a budget the command names.

The history is written by the run engine into the development store the command line reads:
a step on a scripted language model, run once per case, and one run whose step escalated
without a result. The command line is wired as an instance is, with the price table
`TAKTUS_PRICE_TABLE` names. That a candidate is trained, tried and proposed is
`tests/composition/test_maturation_wiring.py`'s and `tests/workers/
test_maturation_on_the_bench.py`'s.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from components.run.test_maturation import (
    BUDGET,
    CLASSIFY,
    PRICES,
    PROCESS,
    WORK,
    Classifying,
    separable,
)
from fakes import FakeIdentifiers, FakeMaturities, FakeWorker
from fakes.identity import added_by_command_line

from taktus.adapters.driven.clock import SystemClock
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
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
STARTER = "idn_starter"
CORRECTOR = "idn_corrector"


async def history(state_dir: Path, count: int) -> tuple[list[Run], Run]:
    """`count` runs of the step on the language model, and one run whose worker step escalated
    because no worker offers what it requires: it has no result."""
    persistence = MemoryPersistence(state_dir)
    clock = SystemClock()
    model = Classifying()
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
        options=EngineOptions(uncalibrated_margin=0.0, prices=PRICES),
        maturities=FakeMaturities(),
        models=StaticModelPool([("model.fake", ["triage"], model, "fake-model@1")]),
    )

    def plan(step: Step) -> Plan:
        return Plan(
            id="pln_triage",
            command_id="cmd_triage",
            goal="sort a request",
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=STARTER, at=clock.now()),
        )

    cases: list[Run] = []
    for features, kind in separable(count):
        model.answers[f"a={features['a']} b={features['b']} note=n"] = kind
        run = await engine.start(
            StartRun(
                plan=plan(CLASSIFY),
                work={"classify": WORK},
                budget=BUDGET,
                process_version=PROCESS,
                actor=STARTER,
                tenant=TENANT,
                inputs={**features, "note": "n"},
            )
        )
        assert run.state is RunState.FINISHED, run.reason
        cases.append(run)
    review = Step(
        id="review",
        method=Method.WORKER,
        reason="a review needs a worker",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="no worker offers it", to=Method.HUMAN),
        requires=("code.review",),
    )
    escalated = await engine.start(
        StartRun(
            plan=plan(review),
            work={"review": {"task": {"goal": "g", "acceptance": ["a"], "inputs": {}}}},
            budget=BUDGET,
            process_version="review@1",
            actor=STARTER,
            tenant=TENANT,
        )
    )
    assert escalated.state is RunState.ESCALATED
    return cases, escalated


def maturation(
    state_dir: Path, *args: str, environment: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "maturation", *args],
        capture_output=True,
        text=True,
        env={**instance(state_dir), **(environment or {})},
        check=False,
    )


def instance(state_dir: Path, **more: str) -> dict[str, str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_")}
    return {**inherited, **PLAIN, "TAKTUS_STATE_DIR": str(state_dir), **more}


def test_the_measures_are_read_back_and_a_correction_counts_without_naming_anyone(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps(PRICES.document()), encoding="utf-8")
    priced = {"TAKTUS_PRICE_TABLE": str(prices)}
    cases, escalated = asyncio.run(history(state, 6))
    added_by_command_line(taktusctl(), CORRECTOR, instance(state))

    corrected = maturation(
        state,
        "correct",
        cases[0].id,
        "classify",
        "--value",
        "k2",
        "--identity",
        CORRECTOR,
        environment=priced,
    )
    assert corrected.returncode == 0, corrected.stderr
    assert f"corrected  {cases[0].id} classify  value sha256:" in corrected.stdout

    shown = maturation(state, "measures", "--json", environment=priced)
    assert shown.returncode == 0, shown.stderr
    measures = {m["step_id"]: m for m in json.loads(shown.stdout)}
    m = measures["classify"]
    assert m["process_version"] == PROCESS and m["method"] == "llm" and m["cases"] == 6
    assert m["currency"] == "eur" and m["cost_per_case"] > 0
    assert m["seconds_per_case"] >= 0
    assert m["corrected"] == 1 and abs(m["correction_rate"] - 1 / 6) < 1e-6
    assert m["distinct_results"] == 3
    assert "review" not in measures, "a step without a result is no case"
    text = maturation(state, "measures", environment=priced)
    assert text.returncode == 0 and f"{PROCESS} classify  llm  6 case(s)" in text.stdout
    assert "corrected 1 (16.7%)" in text.stdout
    # No measure names a person: neither who started the runs nor who corrected one.
    for printed in (shown.stdout, text.stdout):
        assert CORRECTOR not in printed and STARTER not in printed

    # A step without a result is refused, with the reason; so is an identity nobody knows.
    refused = maturation(
        state,
        "correct",
        escalated.id,
        "review",
        "--value",
        "fine",
        "--identity",
        CORRECTOR,
    )
    assert refused.returncode == 1
    assert f"refused: step 'review' of run {escalated.id!r} has no result" in refused.stderr
    unknown = maturation(
        state, "correct", cases[1].id, "classify", "--value", "k1", "--identity", "idn_nobody"
    )
    assert unknown.returncode == 2 and "has no identity 'idn_nobody'" in unknown.stderr

    # Without a price table, every cost is named unpriced.
    unpriced = maturation(state, "measures")
    assert unpriced.returncode == 1
    assert "cost unpriced: no price table is configured" in unpriced.stdout


def test_proposals_are_asked_for_under_a_budget_and_every_outcome_is_printed(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps(PRICES.document()), encoding="utf-8")
    asyncio.run(history(state, 6))
    added_by_command_line(taktusctl(), STARTER, instance(state))
    asked = maturation(
        state,
        "propose",
        "--compute-seconds",
        "600",
        "--identity",
        STARTER,
        "--as-change",
        environment={"TAKTUS_PRICE_TABLE": str(prices)},
    )
    assert asked.returncode == 0, asked.stderr
    assert f"{PROCESS} classify  not proposed: 6 labelled case(s), fewer than 500" in asked.stdout
    assert "always outside the frame" in asked.stdout
    (outcome,) = json.loads(
        maturation(
            state,
            "propose",
            "--compute-seconds",
            "600",
            "--identity",
            STARTER,
            "--json",
            environment={"TAKTUS_PRICE_TABLE": str(prices)},
        ).stdout
    )
    assert outcome["proposed"] is False and outcome["applied"] is False
    nobody = maturation(state, "propose", "--compute-seconds", "600")
    assert nobody.returncode == 2 and "nothing executes without an identity" in nobody.stderr
