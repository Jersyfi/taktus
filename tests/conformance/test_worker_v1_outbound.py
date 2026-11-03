"""A worker that only connects outbound passes the whole suite over the binding (ADR-0139 §2).

The reference worker is started with `--connect` and a port it is told nothing else about. It
must open no port: nothing answers there while the suite, serving the binding itself, runs every
check over it. A worker that answers each relayed request twice fails W-21, and only W-21.
"""

from __future__ import annotations

import socket

import httpx

from taktus.conformance import Status

from .conftest import StartWorker


def _refused(endpoint: str) -> bool:
    try:
        httpx.get(f"{endpoint}/v1/health", timeout=1.0)
    except httpx.ConnectError:
        return True
    return False


async def test_a_worker_that_only_connects_outbound_passes_over_the_binding(
    start_worker: StartWorker,
) -> None:
    worker = start_worker(outbound=True)
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}, report.render()
    w21 = next(c for c in report.checks if c.id == "W-21")
    assert "answered exactly once" in w21.observed
    assert any("over the outbound binding" in note for note in report.notes), report.notes
    # Behind no inbound port: the port the worker was given answers nothing, and it said so.
    assert _refused(worker.endpoint)
    assert "no port opened" in worker.log.read_text()
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()


async def test_a_worker_that_answers_twice_fails_w21_only(start_worker: StartWorker) -> None:
    worker = start_worker(outbound=True, fault="W-21")
    report = await worker.run_suite()
    assert {c.id for c in report.failed} == {"W-21"}, report.render()
    w21 = next(c for c in report.checks if c.id == "W-21")
    assert "answered more than once" in w21.observed


async def test_without_a_connected_worker_the_suite_says_so() -> None:
    from taktus.conformance import SuiteOptions, run_suite

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    report = await run_suite(
        SuiteOptions(endpoint="", listen=f"127.0.0.1:{port}", connect_timeout=0.5)
    )
    assert {c.id for c in report.failed} == {"W-01"}, report.render()
    assert "no worker connected" in next(c for c in report.checks if c.id == "W-01").observed
    w21 = next(c for c in report.checks if c.id == "W-21")
    assert w21.status is Status.INCONCLUSIVE
