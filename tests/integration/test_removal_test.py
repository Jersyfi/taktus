"""The removal test as a process (`blueprints/self-operation/processes/S-01-removal-test.yaml`),
run for real against the reference worker: the example process is registered, the worker is
withheld, the example is rehearsed with and without it, and the result lands in the ledger as
`removal.tested` and in the adapter's maturity.

What the first run must show, and why: the reference worker is the only worker configured, so
withholding it leaves the example's `compute` step with no adapter. The step falls back to a
person — that is the takeover path of ADR-0013 B — so the verdict is *changed*, not *broke*:
the process continues with a person at that step, at a person's cost. The database is the
known exception and is recorded as such, never as a failure.

Both runs of an exercised process are rehearsals (ADR-0030). With a connector whose write
leaves the system, the process is rehearsed only once that write has been called for real:
before, the verdict rests on resolution and says why; after, the write answers from the
recorded response, nothing is sent, and every entry of the rehearsal runs says it is one. An
integration no process uses is `untested`, never `changed` (issue #36), and every verdict
names the configuration it was taken under.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml
from fakes import FakeClock, FakeConnector, FakeIdentifiers, FakeWorker
from fakes.connector import READ, WRITE

from integration.test_first_slice import taktusctl
from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.cli.wiring import Services
from taktus.components.catalog.application.service import REMOVAL_TESTED, RecordRemovalResultHandler
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.query import ProvenanceQuery, RecordedResponses
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.local import LocalWiring
from taktus.composition.loopback import Loopback, Pools
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, Plan, ReplyTo

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "processes" / "six-times-seven.yaml"
REMOVAL = ROOT / "blueprints" / "self-operation" / "processes" / "S-01-removal-test.yaml"
TENANT = "test"


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    return document


async def run_removal(services: Services, integration: str) -> Run:
    version = await services.register_version.execute(
        RegisterProcessVersion(load(REMOVAL), tenant=TENANT)
    )
    command = Command(
        id=services.ids.new("cmd"),
        channel="channel.cli",
        identity="idn_test",
        org_path=(TENANT,),
        intent=Intent(raw="removal test"),
        reply_to=ReplyTo(channel="channel.cli", address="test"),
        received_at=services.clock.now(),
    )
    plan = await services.commission.execute(
        CommissionPlan(
            command=command,
            tenant=TENANT,
            goal="removal test",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    return await services.engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(dict(version.limits or {})),
            process_version=version.ref,
            actor="idn_test",
            tenant=TENANT,
            inputs={"integration": integration},
        )
    )


async def result_of(services: Services, run: Run, step: str) -> Any:
    digest = run.step_run(step).checkpoint
    assert digest is not None and digest.result_digest is not None
    content = await services.engine._objects.get(digest.result_digest)
    return json.loads(content or b"null")


async def test_withholding_the_only_worker_changes_the_example_and_is_recorded(
    worker_endpoint: str, tmp_path: Path
) -> None:
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        await services.register_version.execute(
            RegisterProcessVersion(load(EXAMPLE), tenant=TENANT)
        )
        run = await run_removal(services, "worker.endpoint")
        assert run.state is RunState.FINISHED, run.reason
        assert all(s.state is StepState.SUCCEEDED for s in run.step_runs)

        described = await result_of(services, run, "describe")
        assert described["output"]["family"] == "worker"
        assert "shell.script" in described["output"]["serves"]
        assert described["output"]["alternatives"]["shell.script"] == []
        assert described["output"]["processes"] == [
            {"process": "six-times-seven@1", "steps": ["compute", "overreach"]}
        ]
        assert described["effect"] == {"kind": "read"}, "nothing leaves the system"

        exercised = await result_of(services, run, "exercise")
        result = exercised["output"]
        assert result["verdict"] == "changed"
        assert result["configuration"]["adapter"] == "worker.endpoint"
        assert "shell.script" in result["configuration"]["serves"]
        (process,) = result["processes"]
        assert process["process"] == "six-times-seven@1" and process["exercised"] == "run"
        assert process["verdict"] == "changed"
        compute = next(s for s in process["steps"] if s["step"] == "compute")
        assert compute["fallback"] == "human" and compute.get("alternative") is None
        assert "falls back to a person" in compute["reason"]
        assert process["baseline"]["state"] == "halted", "the example halts at overreach by design"
        assert process["baseline"]["at_step"] == "overreach"
        assert process["withheld"]["state"] == "escalated"
        assert process["withheld"]["at_step"] == "compute"
        assert "a person takes over" in process["note"]

        recorded = await result_of(services, run, "record")
        assert recorded["output"]["maturity"] == "experimental"
        assert recorded["output"]["missing"] == [
            "the conformance suite has not been recorded as passed"
        ]

        report = await result_of(services, run, "report")
        assert "Removal test of worker.endpoint (worker): changed." in report
        assert 'Taken under: {"adapter": "worker.endpoint"' in report

        async with services.work.transaction(TENANT):
            entries = list(await services.ledger.entries(TENANT))
            verification = await services.ledger.verify(TENANT)
        assert verification.intact
        tested = [e for e in entries if e.kind == REMOVAL_TESTED]
        assert len(tested) == 1
        assert tested[0].adapter == "worker.endpoint" and tested[0].outcome == "changed"
        assert tested[0].refs.run_id == run.id
        assert tested[0].content_digest == recorded["output"]["content_digest"]
        rehearsals = {
            e.refs.run_id for e in entries if e.refs.process_version == "six-times-seven@1"
        }
        assert len(rehearsals) == 2, "the example ran twice: with and without the worker"
        assert all(e.rehearsal is True for e in entries if e.refs.run_id in rehearsals), (
            "every entry of a rehearsal run says it is one"
        )
        assert not [e for e in entries if e.rehearsal and e.refs.run_id == run.id]
        assert not [e for e in entries if e.kind.startswith("egress.")], "nothing left the system"


async def test_the_database_is_recorded_as_the_known_exception(
    worker_endpoint: str, tmp_path: Path
) -> None:
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await run_removal(services, "persistence.database")
        assert run.state is RunState.FINISHED, run.reason
        result = (await result_of(services, run, "exercise"))["output"]
        assert result["verdict"] == "exception" and "ADR-0002" in result["reason"]
        async with services.work.transaction(TENANT):
            entries = list(await services.ledger.entries(TENANT))
        tested = [e for e in entries if e.kind == REMOVAL_TESTED]
        assert [e.outcome for e in tested] == ["exception"]


async def test_an_integration_that_is_not_configured_escalates_at_the_first_step(
    worker_endpoint: str, tmp_path: Path
) -> None:
    async with LocalWiring().services(
        state_dir=tmp_path / "state", worker_endpoint=worker_endpoint
    ) as services:
        run = await run_removal(services, "connector.nowhere")
        assert run.state is RunState.ESCALATED
        assert run.step_run("describe").state is StepState.FAILED
        assert "not_found" in (run.step_run("describe").reason or "")


def test_taktusctl_runs_the_removal_test_from_the_command_line(
    worker_endpoint: str, tmp_path: Path
) -> None:
    """The one command the weekly job runs (tools/removal_test.sh): the example is registered
    first so that there is a process to exercise, then S-01 runs for the worker."""
    env = {
        **os.environ,
        "TAKTUS_WORKER": worker_endpoint,
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
    }
    registered = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "run", "--process", str(EXAMPLE), "--stop-after", "1"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert registered.returncode == 3, registered.stdout + registered.stderr
    completed = subprocess.run(  # noqa: S603
        [
            taktusctl(),
            "run",
            "--process",
            str(REMOVAL),
            "--input",
            "integration=worker.endpoint",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "state finished" in completed.stdout
    assert "verdict              rule       exact     succeeded" in completed.stdout
    ledger = json.loads((tmp_path / "state" / "ledger.json").read_text())["default"]
    tested = [e for e in ledger if e["kind"] == REMOVAL_TESTED]
    assert [e["outcome"] for e in tested] == ["changed"]
    assert tested[0]["adapter"] == "worker.endpoint"
    assert all("reason" not in e for e in ledger), "the ledger stores no text"


def test_the_bundle_and_the_blueprint_describe_the_same_process() -> None:
    bundle = load(REMOVAL)
    blueprint = load(ROOT / "blueprints" / "self-operation" / "blueprint.yaml")
    (described,) = [p for p in blueprint["processes"] if p["id"] == "S-01"]
    assert [s["id"] for s in described["steps"]] == [s["id"] for s in bundle["steps"]]
    assert described["autonomy"]["level"] == bundle["autonomy"]["level"]
    assert described["triggers"] == bundle["triggers"]


# --- a connector whose write leaves the system ------------------------------------------------

RECORDS = "connector.fake"
FAKE_PROCESS: dict[str, Any] = {
    "id": "fake-records",
    "version": "1",
    "name": "Read a record, write one",
    "autonomy": {
        "level": 2,
        "reason": "a test process: a read, and a write that leaves the system",
        "toward_next": "nothing; it exists for the removal test's tests",
    },
    "author": "the tests",
    "reason": "the shape of every real process here: it reads, then it writes outward",
    "limits": {"quota": {"units": 20}},
    "inputs": {"id": {"description": "the record to read", "example": "issue-1"}},
    "steps": [
        {
            "id": "read",
            "method": "rule",
            "reason": "a read through the connector",
            "rejected": [{"method": "llm", "why": "a read needs no judgement"}],
            "exactness": "sourced",
            "fallback": {"when": "no connector serves it", "to": "human"},
            "work": {"rule": "connector", "operation": READ, "input": {"id": {"$input": "id"}}},
        },
        {
            "id": "write",
            "method": "rule",
            "reason": "a write through the connector, which leaves the system",
            "rejected": [{"method": "llm", "why": "a write needs no judgement"}],
            "exactness": "sourced",
            "fallback": {"when": "no connector serves it", "to": "human"},
            "depends_on": ["read"],
            "work": {
                "rule": "connector",
                "operation": WRITE,
                "input": {"title": {"$from": "read", "$select": "output.title"}},
            },
        },
    ],
}


def connector_services(connector: FakeConnector) -> Services:
    """The wiring of `composition/local.py` over memory, with the fake connector configured as
    `connector.fake` beside the loopback and a scripted worker: what the removal test needs
    to exercise a process that writes outward, without a network."""
    clock, ids = FakeClock(), FakeIdentifiers()
    persistence = MemoryPersistence()
    runs = MemoryRepository(persistence, Run)
    objects = MemoryObjectStore()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    provenance = MemoryProvenanceStore(persistence)
    recordings = RecordedResponses(runs, persistence, objects)
    loopback = LoopbackConnector()
    pools = Pools(
        StaticWorkerPool([("worker.endpoint", FakeWorker())]),
        StaticConnectorPool([(RECORDS, connector), (LOOPBACK, loopback)]),
        StaticModelPool(),
    )

    def engine_for(
        workers: StaticWorkerPool, connectors: StaticConnectorPool, models: StaticModelPool
    ) -> RunEngine:
        return RunEngine(
            runs=runs,
            work=persistence,
            objects=objects,
            ledger=ledger,
            provenance=provenance,
            workers=workers,
            clock=clock,
            ids=ids,
            telemetry=NoTelemetry(),
            connectors=connectors,
            models=models,
            recordings=recordings,
        )

    commission = CommissionPlanHandler(
        MemoryRepository(persistence, Command),
        MemoryRepository(persistence, Plan),
        persistence,
        clock,
        ids,
    )
    versions = MemoryRepository(persistence, ProcessVersion)
    loopback.bind(
        Loopback(
            pools=pools,
            versions=versions,
            work=persistence,
            commission=commission,
            engine_for=engine_for,
            record=RecordRemovalResultHandler(
                MemoryRepository(persistence, AdapterMaturity), persistence, ledger, clock
            ),
            recordings=recordings,
            clock=clock,
            ids=ids,
        )
    )
    return Services(
        register_version=RegisterProcessVersionHandler(versions, persistence),
        commission=commission,
        engine=engine_for(pools.workers, pools.connectors, pools.models),
        provenance=ProvenanceQuery(provenance, runs, ledger, persistence),
        runs=runs,
        ledger=ledger,
        work=persistence,
        clock=clock,
        ids=ids,
        storage="memory, for the test",
    )


async def run_for_real(services: Services, bundle: dict[str, Any]) -> Run:
    version = await services.register_version.execute(RegisterProcessVersion(bundle, tenant=TENANT))
    plan = await services.commission.execute(
        CommissionPlan(
            command=Command(
                id=services.ids.new("cmd"),
                channel="channel.cli",
                identity="idn_test",
                org_path=(TENANT,),
                intent=Intent(raw="run it for real"),
                reply_to=ReplyTo(channel="channel.cli", address="test"),
                received_at=services.clock.now(),
            ),
            tenant=TENANT,
            goal="run it for real",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    return await services.engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(dict(version.limits or {})),
            process_version=version.ref,
            actor="idn_test",
            tenant=TENANT,
            inputs={"id": "issue-1"},
        )
    )


async def test_an_outward_write_is_rehearsed_once_it_has_been_called_for_real() -> None:
    connector = FakeConnector()
    connector.reads["issue-1"] = {"id": "issue-1", "title": "Pin the model"}
    services = connector_services(connector)
    await services.register_version.execute(RegisterProcessVersion(FAKE_PROCESS, tenant=TENANT))

    # Never called for real: nothing to rehearse the write with, so it is not run.
    before = await run_removal(services, RECORDS)
    assert before.state is RunState.FINISHED, before.reason
    result = (await result_of(services, before, "exercise"))["output"]
    (process,) = result["processes"]
    assert process["exercised"] == "resolved"
    assert process["note"] == (
        f"not run: no recorded response for {WRITE} through {RECORDS} — it has never been "
        "called for real on this instance"
    )
    assert connector.acted == 0 and not connector.calls, "nothing was sent to decide that"

    # One real run makes the recording.
    real = await run_for_real(services, FAKE_PROCESS)
    assert real.state is RunState.FINISHED, real.reason
    assert connector.acted == 1
    sent_before = len(connector.calls)

    # Now the process is rehearsed twice, and nothing leaves the system.
    after = await run_removal(services, RECORDS)
    assert after.state is RunState.FINISHED, after.reason
    result = (await result_of(services, after, "exercise"))["output"]
    assert result["configuration"] == {
        "adapter": RECORDS,
        "serves": ["fake.records"],
        "operations": [READ, WRITE, "fake.records.fire"],
        "version": "1.2.3",
    }
    (process,) = result["processes"]
    assert process["exercised"] == "run", process.get("note")
    assert process["baseline"]["state"] == "finished"
    assert process["withheld"]["state"] == "escalated"
    assert process["withheld"]["at_step"] == "read"
    assert process["verdict"] == result["verdict"] == "changed"
    assert "a person takes over" in process["note"]
    assert connector.acted == 1, "the rehearsals acted on nothing outside"
    assert [op for op, _, _ in connector.calls[sent_before:]] == [READ], (
        "the baseline's read is real; its write was answered from the recording"
    )

    async with services.work.transaction(TENANT):
        entries = list(await services.ledger.entries(TENANT))
        verification = await services.ledger.verify(TENANT)
    assert verification.intact
    rehearsals = {process["baseline"]["run_id"], process["withheld"]["run_id"]}
    for run_id in rehearsals:
        of_run = [e for e in entries if e.refs.run_id == run_id]
        assert of_run and all(e.rehearsal is True for e in of_run)
    baseline = [e for e in entries if e.refs.run_id == process["baseline"]["run_id"]]
    assert [(e.refs.step_id, e.outcome) for e in baseline if e.kind == "step.finished"] == [
        ("read", "succeeded"),
        ("write", "rehearsed"),
    ]
    egress = [e for e in entries if e.kind.startswith("egress.")]
    assert [e.refs.run_id for e in egress] == [real.id], "only the real run's write left"
    tested = [e for e in entries if e.kind == REMOVAL_TESTED]
    assert [e.outcome for e in tested] == ["changed", "changed"]
    assert not [e for e in tested if e.rehearsal], "the removal test itself is a real run"


async def test_an_integration_no_process_uses_is_untested() -> None:
    """Issue #36: "nobody uses it" is not `changed`. The maturity says what is missing."""
    services = connector_services(FakeConnector())
    run = await run_removal(services, RECORDS)
    assert run.state is RunState.FINISHED, run.reason
    result = (await result_of(services, run, "exercise"))["output"]
    assert result["verdict"] == "untested"
    assert result["reason"] == "no registered process uses this integration"
    assert result["configuration"]["adapter"] == RECORDS
    recorded = (await result_of(services, run, "record"))["output"]
    assert recorded["maturity"] == "experimental"
    assert any("no registered process" in gap for gap in recorded["missing"])
    report = await result_of(services, run, "report")
    assert f"Removal test of {RECORDS} (connector): untested." in report
