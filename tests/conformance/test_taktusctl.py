"""`taktusctl conformance run` is the entry point a third party uses; it must work as installed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .conftest import CREDENTIAL, SCENARIO, StartConnector, StartWorker


def test_taktusctl_conformance_run(start_worker: StartWorker, tmp_path: Path) -> None:
    worker = start_worker()
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None, "taktusctl is not on the path; run under `uv run`"
    report_path = tmp_path / "report.json"
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [
            taktusctl,
            "conformance",
            "run",
            "--contract",
            "worker/v1",
            "--endpoint",
            worker.endpoint,
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
    assert "11 passed, 0 failed, 0 inconclusive, 1 pending" in completed.stdout
    assert "verified: no" in completed.stdout
    report = json.loads(report_path.read_text())
    assert report["summary"]["exit_code"] == 0
    assert worker.credential_value not in completed.stdout
    assert worker.credential_value not in report_path.read_text()


def test_taktusctl_refuses_an_unknown_contract() -> None:
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None
    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "conformance", "run", "--contract", "model/v1", "--endpoint", "http://x"],
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
