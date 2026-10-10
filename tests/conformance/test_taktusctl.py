"""`taktusctl conformance run` is the entry point a third party uses; it must work as installed.
`taktusctl conformance record` is the one a person uses to have the instance run the suite
against the adapter its configuration resolves, and record it (ADR-0044)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from fakes.identity import added_by_command_line

from .conftest import CREDENTIAL, HOST, SCENARIO, TASK, StartConnector, StartWorker


def test_taktusctl_conformance_run(start_worker: StartWorker, tmp_path: Path) -> None:
    worker = start_worker()
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None, "taktusctl is not on the path; run under `uv run`"
    report_path = tmp_path / "report.json"
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(TASK), encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [
            taktusctl,
            "conformance",
            "run",
            "--contract",
            "worker/v1",
            "--endpoint",
            worker.endpoint,
            "--task",
            str(task_path),
            "--hosts",
            HOST,
            "--json",
            str(report_path),
            "--worker-log",
            str(worker.log),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, CREDENTIAL: worker.credential_value},
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "17 passed, 0 failed, 0 inconclusive, 1 pending" in completed.stdout
    assert "verified: no" in completed.stdout
    report = json.loads(report_path.read_text())
    assert report["summary"]["exit_code"] == 0
    assert worker.credential_value not in completed.stdout
    assert worker.credential_value not in report_path.read_text()


def test_taktusctl_refuses_an_unknown_contract() -> None:
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "conformance", "run", "--contract", "events/v1", "--endpoint", "http://x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "unknown contract" in completed.stderr


def test_taktusctl_conformance_run_for_a_connector(
    start_connector: StartConnector, tmp_path: Path
) -> None:
    connector = start_connector()
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None
    report_path = tmp_path / "report.json"
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [
            taktusctl,
            "conformance",
            "run",
            "--contract",
            "connector/v1",
            "--endpoint",
            connector.endpoint,
            "--scenario",
            str(SCENARIO),
            "--json",
            str(report_path),
            "--adapter-log",
            str(connector.log),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **connector.credential_values},
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "9 passed, 0 failed, 0 inconclusive, 1 pending" in completed.stdout
    assert "verified: no" in completed.stdout
    report = json.loads(report_path.read_text())
    assert report["contract"] == "connector/v1"
    assert report["summary"]["exit_code"] == 0
    for value in connector.credential_values.values():
        assert value not in completed.stdout
        assert value not in report_path.read_text()


def test_taktusctl_needs_a_scenario_for_a_connector() -> None:
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "conformance", "run", "--contract", "connector/v1", "--endpoint", "http://x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "--scenario" in completed.stderr


def test_taktusctl_conformance_record(start_worker: StartWorker, tmp_path: Path) -> None:
    """A person has the instance run the worker suite against the worker it is configured
    with; the pass lands in the adapter's maturity and the ledger, with the person as actor.
    An identifier nothing is configured under runs nothing and records nothing."""
    worker = start_worker()
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(TASK), encoding="utf-8")
    state = tmp_path / "state"
    env = {
        **os.environ,
        "NO_COLOR": "1",
        "TERM": "dumb",
        "TAKTUS_STATE_DIR": str(state),
        "TAKTUS_WORKER": worker.endpoint,
        "TAKTUS_CONFORMANCE_WORKER_TASK": str(task_path),
        "TAKTUS_CONFORMANCE_WORKER_HOSTS": HOST,
        "TAKTUS_CONFORMANCE_WORKER_CREDENTIAL": CREDENTIAL,
        "TAKTUS_CREDENTIAL_" + CREDENTIAL: worker.credential_value,
        "TAKTUS_CONFORMANCE_WORKER_LOG": str(worker.log),
    }
    added_by_command_line(taktusctl, "idn_test", env)
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "conformance", "record", "worker.endpoint", "--identity", "idn_test"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "conformance worker/v1 of worker.endpoint: passed" in completed.stdout
    assert "conformance.tested" in completed.stdout
    assert worker.credential_value not in completed.stdout + completed.stderr
    records = json.loads((state / "adaptermaturity.json").read_text())["default"]
    (record,) = records
    assert record["conformance"]["outcome"] == "passed"
    assert record["conformance"]["actor"] == "idn_test"
    assert record["conformance"]["configuration"]["adapter"] == "worker.endpoint"
    unknown = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "conformance", "record", "connector.nowhere", "--identity", "idn_test"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert unknown.returncode == 2, unknown.stdout + unknown.stderr
    assert "no configured adapter 'connector.nowhere'" in unknown.stderr
