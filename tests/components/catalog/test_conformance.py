"""The conformance half of maturity (ADR-0044): what a suite's report comes to, what the record
derives against the configuration that resolves an identifier now, the one writer that records
it, and that no surface takes a report, a verdict or a date."""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClock

from taktus.adapters.driven.connectors.loopback import (
    CONFORMANCE,
    DECLARATION,
    RUN_SUITE,
    LoopbackConnector,
)
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryRepository,
)
from taktus.components.catalog.application.service import (
    CONFORMANCE_TESTED,
    RecordRemovalResult,
    RecordRemovalResultHandler,
    RunConformance,
    RunConformanceHandler,
)
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    Configuration,
    Maturity,
    RemovalResult,
    Verdict,
    judged,
)
from taktus.components.catalog.ports import SuiteRun
from taktus.components.ledger.application.service import ChainedLedger
from taktus.conformance import CheckResult, Report
from taktus.ports.connector import CallContext, Effect

from .test_removal import AT

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src" / "taktus"
TENANT = "t"
NOW = Configuration(adapter="worker.endpoint", serves=("shell.script",), version="0.1.0")


def report(**statuses: str) -> dict[str, Any]:
    """A worker report with the given check statuses, built by the suite's own report."""
    built = Report(endpoint="http://worker.test", contract="worker/v1")
    for check, status in statuses.items():
        built.add(getattr(CheckResult, status)(check.replace("_", "-"), "observed"))
    return built.finish().to_dict()


class FakeSuites:
    """Answers the report it is given, for the configuration it is given."""

    def __init__(self, report: dict[str, Any], configuration: Configuration = NOW) -> None:
        self.report = report
        self.configuration = configuration
        self.asked: list[str] = []

    async def run(self, integration: str) -> SuiteRun:
        self.asked.append(integration)
        return SuiteRun(
            integration=integration,
            family="worker",
            contract="worker/v1",
            taktus_version="0.0.0",
            configuration=self.configuration,
            report=self.report,
        )


class World:
    def __init__(self, suites: FakeSuites) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.records = MemoryRepository(self.persistence, AdapterMaturity)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.objects = MemoryObjectStore()
        self.suites = suites
        self.handler = RunConformanceHandler(
            suites, self.records, self.persistence, self.ledger, self.objects, self.clock
        )

    async def record(self, integration: str = "worker.endpoint") -> AdapterMaturity:
        maturity, _ = await self.handler.execute(
            RunConformance(integration, TENANT, actor="idn_ada", run_id="run_s01")
        )
        return maturity


# --- what a report comes to -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statuses", "outcome", "failed", "inconclusive"),
    [
        ({"W_01": "passed", "W_12": "pending"}, "passed", (), ()),
        (
            {"W_01": "passed", "W_05": "failed", "W_14": "inconclusive"},
            "failed",
            ("W-05",),
            ("W-14",),
        ),
        ({"W_01": "passed", "W_14": "inconclusive"}, "incomplete", (), ("W-14",)),
    ],
)
def test_the_outcome_is_what_the_report_computes(
    statuses: dict[str, str], outcome: str, failed: tuple[str, ...], inconclusive: tuple[str, ...]
) -> None:
    document = report(**statuses)
    assert judged(document) == (outcome, failed, inconclusive)
    assert judged(document)[0] == document["maturity"]["conformance_suite"]


def test_a_report_without_checks_is_not_judged() -> None:
    with pytest.raises(ValueError, match="no checks"):
        judged({"checks": []})


# --- the record, against the configuration now ----------------------------------------------------


async def test_a_pass_counts_only_for_the_configuration_it_names() -> None:
    world = World(FakeSuites(report(W_01="passed", W_12="pending")))
    maturity = await world.record()
    removal = RemovalResult(
        integration="worker.endpoint",
        family="worker",
        verdict=Verdict.CHANGED,
        tested_at=AT,
        run_id="run_removal",
        configuration=NOW,
    )
    both = maturity.model_copy(update={"removal": removal})
    assert both.maturity(NOW) is Maturity.VERIFIED and both.missing(NOW) == ()
    upgraded = NOW.model_copy(update={"version": "0.2.0"})
    assert both.maturity(upgraded) is Maturity.EXPERIMENTAL
    (gap,) = both.missing(upgraded)
    assert gap.startswith("the conformance suite passed for another configuration")
    assert "version 0.1.0 then, 0.2.0 now" in gap
    declared = NOW.model_copy(update={"serves": ("shell.script", "shell.sandboxed")})
    assert "it served shell.script then" in both.missing(declared)[0]
    assert both.maturity(None) is Maturity.EXPERIMENTAL
    assert "no configuration resolves the identifier now" in both.missing(None)[0]


async def test_a_run_that_did_not_pass_is_recorded_and_names_its_checks() -> None:
    world = World(FakeSuites(report(W_01="passed", W_05="failed", W_14="inconclusive")))
    maturity = await world.record()
    assert maturity.conformance is not None and not maturity.conformance.passed
    assert maturity.conformance_passed_at is None
    assert maturity.maturity(NOW) is Maturity.EXPERIMENTAL
    assert maturity.missing(NOW)[0] == (
        "the last conformance run of worker/v1 ended failed (failed: W-05; inconclusive: W-14)"
    )


# --- the one writer -------------------------------------------------------------------------------


async def test_one_transaction_writes_the_ledger_entry_and_the_record() -> None:
    world = World(FakeSuites(report(W_01="passed", W_12="pending")))
    maturity, entry = await world.handler.execute(
        RunConformance("worker.endpoint", TENANT, actor="idn_ada", run_id="run_s01")
    )
    assert world.suites.asked == ["worker.endpoint"]
    result = maturity.conformance
    assert result is not None and result.passed
    assert result.contract == "worker/v1" and result.taktus_version == "0.0.0"
    assert result.configuration == NOW and result.tested_at >= AT
    assert result.actor == "idn_ada" and result.run_id == "run_s01"
    assert entry.kind == CONFORMANCE_TESTED and entry.outcome == "passed"
    assert entry.adapter == "worker.endpoint"
    assert entry.refs.actor == "idn_ada" and entry.refs.run_id == "run_s01"
    assert entry.content_digest == result.digest
    evidence = json.loads(await world.objects.get(result.digest) or b"{}")
    assert evidence["configuration"] == NOW.document()
    assert evidence["report"] == world.suites.report, "the digest covers report and configuration"
    async with world.persistence.transaction(TENANT):
        stored = await world.records.get(TENANT, "worker.endpoint")
        assert (await world.ledger.verify(TENANT)).intact
    assert stored == maturity


async def test_each_half_keeps_the_other() -> None:
    world = World(FakeSuites(report(W_01="passed", W_12="pending")))
    await world.record()
    removal = RecordRemovalResultHandler(
        world.records, world.persistence, world.ledger, world.clock
    )
    removed, _ = await removal.execute(
        RecordRemovalResult(
            RemovalResult(
                integration="worker.endpoint",
                family="worker",
                verdict=Verdict.CHANGED,
                tested_at=AT,
                run_id="run_removal",
                configuration=NOW,
            ),
            TENANT,
        )
    )
    assert removed.conformance is not None and removed.maturity(NOW) is Maturity.VERIFIED
    again = await world.record()
    assert again.removal is not None and again.maturity(NOW) is Maturity.VERIFIED


def test_the_conformance_half_has_exactly_one_writer() -> None:
    """Issue #93: no command, HTTP endpoint or connector operation takes a report, a verdict or
    a date to set the conformance half. The record is built in one place, the handler that ran
    the suite; every other place that writes a maturity record copies the half it found."""
    builders: list[str] = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if name in ("ConformanceResult", "ConformanceResult.model_validate"):
                builders.append(f"{path.relative_to(SOURCE)}:{name}")
            for keyword in node.keywords:
                if keyword.arg == "conformance" and name == "AdapterMaturity":
                    value = ast.unparse(keyword.value)
                    if value not in ("result", "None if current is None else current.conformance"):
                        builders.append(f"{path.relative_to(SOURCE)}: conformance={value}")
    assert builders == [
        "components/catalog/application/service/run_conformance.py:ConformanceResult"
    ]
    # The command the handler takes names the adapter, the actor and the run; nothing else.
    fields = {field.name for field in dataclasses.fields(RunConformance)}
    assert fields == {"integration", "tenant", "actor", "run_id"}
    # The command line: the record command takes no report, verdict, date or endpoint.
    from taktus.adapters.driving.cli.conformance_command import record

    parameters = set(record.__annotations__) - {"ctx", "return"}
    assert parameters == {"integration", "worker", "state_dir", "identity", "tenant"}
    # The HTTP surface has no route that writes a maturity.
    surface = (ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8")
    assert "conformance" not in surface and "maturity" not in surface


async def test_the_loopback_operation_hands_on_the_identifier_alone() -> None:
    class Orchestrator:
        def __init__(self) -> None:
            self.asked: list[tuple[str, str, str, str]] = []

        async def conformance(
            self, tenant: str, integration: str, *, run_id: str, identity: str
        ) -> dict[str, Any]:
            self.asked.append((tenant, integration, run_id, identity))
            return {"outcome": "passed", "ledger_seq": 7, "content_digest": "sha256:" + "a" * 64}

    orchestrator = Orchestrator()
    connector = LoopbackConnector(orchestrator)  # type: ignore[arg-type]
    operation = DECLARATION.operation(RUN_SUITE)
    assert operation is not None and operation.capability == CONFORMANCE
    assert operation.effect is Effect.WRITE and not operation.repeatable
    context = CallContext.model_validate(
        {
            "tenant": TENANT,
            "identity": "idn_s01",
            "run_id": "run_s01",
            "step_id": "suite",
            "attempt": 1,
            "idempotency_key": "taktus:run_s01:suite:1",
            "credentials": [],
        }
    )
    given = {
        "integration": "worker.endpoint",
        "report": {"checks": []},
        "outcome": "passed",
        "tested_at": "2026-10-09T00:00:00Z",
    }
    result = await connector.call(RUN_SUITE, context, given)
    assert orchestrator.asked == [(TENANT, "worker.endpoint", "run_s01", "idn_s01")]
    assert result.effect.kind is Effect.WRITE and result.effect.replayed is False
    assert result.effect.records is not None
    assert result.effect.records[0].kind == "conformance.tested"
