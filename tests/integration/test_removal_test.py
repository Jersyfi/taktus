"""The removal test as a process (`blueprints/self-operation/processes/S-01-removal-test.yaml`),
run for real against the reference worker: the example process is registered, the worker is
withheld, the example is rehearsed with and without it, and the result lands in the ledger as
`removal.tested` and in the adapter's maturity.

What the first run must show, and why: the reference worker is the only worker configured, so
withholding it leaves the example's `compute` step with no adapter. The step falls back to a
person — that is the takeover path of ADR-0013 B — so the verdict is *changed*, not *broke*:
the process continues with a person at that step, at a person's cost. The database is the
known exception and is recorded as such, never as a failure.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from integration.test_first_slice import taktusctl
from taktus.adapters.driving.cli.wiring import Services
from taktus.components.catalog.application.service import REMOVAL_TESTED
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import RegisterProcessVersion
from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.local import LocalWiring
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo

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
    assert described["autonomy"] == bundle["autonomy"]
    assert described["triggers"] == bundle["triggers"]
