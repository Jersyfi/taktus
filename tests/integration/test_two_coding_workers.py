"""Two coding workers in one pool: removing either changes the process and breaks nothing (#154).

Until the second coding worker existed, withholding the coding worker left a coding step to a
person: the verdict was *changed*, but only because a person takes the step over (DEC-0111).
Here both coding workers are in the worker pool, each a separate process behind the worker
contract and each against its own fake agent (`workers/claudecode/`, `workers/codex/`). The
removal test S-01 withholds each in turn. The coding step is served by the other, which the
finding names as its `alternative`, and the process rehearsed without the withheld worker
finishes: its step ran on the other worker for real, with the other's fake agent writing the
files. The verdict is *changed* through an adapter, not through a person.

An instance configured with both (#209, ADR-0078) is the last test: the configuration names
the two workers in `TAKTUS_WORKERS`, in one order, and S-01 run for each of them on that
instance gives *changed* with the other as the alternative. The worker configured second stands
behind the first, so the removal test's baseline puts the withheld worker first.

What is not proven here: either worker against its real agent (#68, #208).
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeConnector

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import REMOVAL_TESTED
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.run.domain.model import RunState
from taktus.composition.local import LocalWiring

from .conftest import ROOT, free_port
from .test_dev_orchestration import wait_ready
from .test_removal_test import TENANT, connector_services, result_of, run_removal

FIRST = "worker.coding"
SECOND = "worker.coding-second"
WORKERS = {
    FIRST: ROOT / "workers" / "claudecode",
    SECOND: ROOT / "workers" / "codex",
}
CREDENTIAL = "CODING_AGENT_API_KEY"

# A coding step as P-03's `implement` is one: the capabilities it requires, its credential by
# the name both workers read, and a person as its fallback. No host, so that the rehearsals run
# the step for real (ADR-0030).
CODING: dict[str, Any] = {
    "id": "small-change",
    "version": "1",
    "name": "A small change to a workspace",
    "autonomy": {
        "level": 2,
        "reason": "a test process: every result is looked at",
        "toward_next": "nothing; it exists for the removal test",
    },
    "author": "the test",
    "reason": "the shape of a coding step, served by either coding worker",
    "limits": {"currency": {"usd": 5.0}},
    "steps": [
        {
            "id": "implement",
            "method": "worker",
            "reason": "changing code is multi-step work with tools, which a worker offers",
            "rejected": [{"method": "llm", "why": "a completion cannot run commands"}],
            "exactness": "tolerant",
            "fallback": {"when": "the coding worker is unavailable", "to": "human"},
            "requires": ["code.read", "code.edit", "code.test", "shell.sandboxed"],
            "work": {
                "task": {"goal": "write hello", "acceptance": ["hello.txt exists"]},
                "max_steps": 40,
                "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
            },
        }
    ],
}


@pytest.fixture
def coding_workers(tmp_path: Path) -> Iterator[dict[str, str]]:
    """Both coding workers against their fake agents, by endpoint, each with a credential of
    its own under the name both read."""
    started: list[subprocess.Popen[bytes]] = []
    endpoints: dict[str, str] = {}
    try:
        for adapter, directory in WORKERS.items():
            port = free_port()
            log = tmp_path / f"{directory.name}.log"
            with log.open("wb") as handle:
                process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                    [
                        sys.executable,
                        str(directory / "worker.py"),
                        "--port",
                        str(port),
                        "--auth",
                        "api-key",
                        "--agent",
                        f"{sys.executable} {directory / 'fake_agent.py'}",
                        "--state-dir",
                        str(tmp_path / f"{directory.name}-state"),
                        "--estimate-steps",
                        "8",
                        "--estimate-currency",
                        "0.5",
                    ],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, CREDENTIAL: "fake-" + secrets.token_hex(8)},
                )
            started.append(process)
            endpoints[adapter] = f"http://127.0.0.1:{port}"
            wait_ready(process, f"{endpoints[adapter]}/v1/health", log, directory.name)
        yield endpoints
    finally:
        for process in started:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


async def test_withholding_either_coding_worker_changes_the_step_to_the_other(
    coding_workers: dict[str, str],
) -> None:
    """The pool's order says which worker serves the step, and the removal test withholds the
    one that serves it. Each worker is first once, so that each is withheld while it serves."""
    for withheld, other in ((FIRST, SECOND), (SECOND, FIRST)):
        order = (withheld, other)
        pool = StaticWorkerPool([(a, HttpWorker(coding_workers[a])) for a in order])
        services = connector_services(FakeConnector(), workers=pool)
        await services.register_version.execute(RegisterProcessVersion(CODING, tenant=TENANT))
        run = await run_removal(services, withheld)
        assert run.state is RunState.FINISHED, (withheld, run.reason)

        described = (await result_of(services, run, "describe"))["output"]
        assert described["family"] == "worker"
        assert described["processes"] == [{"process": "small-change@1", "steps": ["implement"]}]
        for capability in CODING["steps"][0]["requires"]:
            assert described["alternatives"][capability] == [other], (withheld, capability)

        result = (await result_of(services, run, "exercise"))["output"]
        assert result["verdict"] == "changed", (withheld, result)
        (process,) = result["processes"]
        (finding,) = process["steps"]
        assert finding["step"] == "implement"
        assert finding["alternative"] == other, finding
        assert finding["verdict"] == "changed"
        assert process["exercised"] == "run", process.get("note")
        assert process["baseline"]["state"] == "finished", process["baseline"]
        assert process["withheld"]["state"] == "finished", (
            f"without {withheld} the step ran on {other}: {process['withheld']}"
        )

        recorded = (await result_of(services, run, "record"))["output"]
        assert recorded["integration"] == withheld
        assert not [gap for gap in recorded["missing"] if "removal" in gap], recorded

        async with services.work.transaction(TENANT):
            entries = list(await services.ledger.entries(TENANT))
        tested = [(e.adapter, e.outcome) for e in entries if e.kind == REMOVAL_TESTED]
        assert tested == [(withheld, "changed")]


async def test_an_instance_configured_with_both_says_changed_for_each(
    coding_workers: dict[str, str], tmp_path: Path
) -> None:
    """Issue #209: the instance's configuration names both coding workers, each with its own
    identifier and endpoint, in one order. S-01 run for each of them on that instance gives
    *changed* with the other named as the alternative, and the maturity record of each holds
    the removal half as passed."""
    configuration = EnvironmentConfiguration(
        {
            "TAKTUS_WORKERS": "coding,coding-second",
            "TAKTUS_WORKER_CODING_ENDPOINT": coding_workers[FIRST],
            "TAKTUS_WORKER_CODING_SECOND_ENDPOINT": coding_workers[SECOND],
        }
    )
    async with LocalWiring(configuration).services(
        state_dir=tmp_path / "state", worker_endpoint="http://127.0.0.1:1"
    ) as services:
        await services.register_version.execute(RegisterProcessVersion(CODING, tenant=TENANT))
        for withheld, other in ((FIRST, SECOND), (SECOND, FIRST)):
            run = await run_removal(services, withheld)
            assert run.state is RunState.FINISHED, (withheld, run.reason)
            result = (await result_of(services, run, "exercise"))["output"]
            assert result["verdict"] == "changed", (withheld, result)
            assert result["configuration"]["adapter"] == withheld
            (process,) = result["processes"]
            (finding,) = process["steps"]
            assert finding["alternative"] == other, (withheld, finding)
            assert process["exercised"] == "run", process.get("note")
            assert process["baseline"]["state"] == "finished", process["baseline"]
            assert process["withheld"]["state"] == "finished", process["withheld"]
            recorded = (await result_of(services, run, "record"))["output"]
            assert recorded["integration"] == withheld
            assert not [gap for gap in recorded["missing"] if "removal" in gap], recorded

        async with services.work.transaction(TENANT):
            entries = list(await services.ledger.entries(TENANT))
        tested = sorted((e.adapter, e.outcome) for e in entries if e.kind == REMOVAL_TESTED)
        assert tested == [(FIRST, "changed"), (SECOND, "changed")]
