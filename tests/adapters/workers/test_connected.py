"""A worker connected outbound, behind the worker port (ADR-0156 §2 and §3, issue #625).

The reference worker is started with `--connect` against the control plane's host of the
binding, served by uvicorn over the memory relay, and opens no port. The worker port reaches it
through the relay as it reaches one at an endpoint: its capabilities, an assignment, the whole
stream of events. A worker that presents no connect key, or another one, is refused, and no
request is taken for it.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from taktus.adapters.driven.memory import MemoryRelay
from taktus.adapters.driven.workers.connected import connected_worker
from taktus.adapters.driving.rest import relay as host_routes
from taktus.adapters.driving.rest.relay import ConnectedHost
from taktus.ports.configuration import Secret
from taktus.ports.relay import Relay
from taktus.ports.worker import (
    Assignment,
    AssignmentFinished,
    Callback,
    ComputeLimit,
    Context,
    Frame,
    Limits,
    RelayRequest,
    Task,
)

WORKER = Path(__file__).resolve().parents[3] / "workers/script/worker.py"
NAME = "site"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextlib.asynccontextmanager
async def hosting(relay: Relay, keys: dict[str, str], port: int) -> AsyncIterator[str]:
    """The host of the binding on `port`, as one instance's `api` role serves it; its base for
    the worker `NAME`."""
    app = FastAPI()
    app.include_router(
        host_routes.router(
            ConnectedHost(
                relay=relay, keys={n: Secret(k) for n, k in keys.items()}, wait_seconds=1.0
            )
        )
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            task.result()
        await asyncio.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}/workers/{NAME}/relay"
    finally:
        server.should_exit = True
        server.force_exit = True
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, 10)


@contextlib.contextmanager
def connected(
    base: str, tmp_path: Path, key: str | None, *options: str, env: dict[str, str] | None = None
) -> Iterator[Path]:
    """The reference worker connected to `base`, presenting `key`; yields its log."""
    log = tmp_path / f"worker-{os.urandom(3).hex()}.log"
    env = {k: v for k, v in {**os.environ, **(env or {})}.items() if k != "TAKTUS_CONNECT_KEY_FILE"}
    if key is not None:
        key_file = tmp_path / f"connect-{os.urandom(3).hex()}.key"
        key_file.write_text(key)
        env["TAKTUS_CONNECT_KEY_FILE"] = str(key_file)
    args = [
        sys.executable,
        str(WORKER),
        "--connect",
        base,
        "--state-dir",
        str(tmp_path / "state"),
        "--step-seconds",
        "0.1",
        *options,
    ]
    with log.open("wb") as handle:
        process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, env=env)  # noqa: S603
    try:
        yield log
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def assignment(n: int = 1, *, tools: tuple[str, ...] = ("shell.script",)) -> Assignment:
    return Assignment(
        assignment_id=f"asg_conn{n:04d}",
        task=Task(goal="g", acceptance=("a",)),
        context=Context(),
        frame=Frame(autonomy_level=2, allowed_tools=tools, max_steps=10),
        limits=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
        callback=Callback(events="sse"),
    )


async def test_the_worker_port_reaches_a_worker_connected_outbound(tmp_path: Path) -> None:
    relay = MemoryRelay()
    async with hosting(relay, {NAME: "k-right"}, free_port()) as base:
        with connected(base, tmp_path, "k-right") as log:
            async with connected_worker(relay, f"worker.{NAME}", timeout=10.0) as worker:
                declared = await worker.capabilities()
                assert declared.contract == "worker/v1" and declared.supports.steering
                state = await worker.assign(assignment())
                assert state.assignment_id == "asg_conn0001"
                events = [e async for e in worker.events("asg_conn0001")]
            assert isinstance(events[-1], AssignmentFinished)
            assert events[-1].outcome == "succeeded"
            assert [e.seq for e in events] == list(range(1, len(events) + 1))
            assert "k-right" not in log.read_text(), "the key is never written anywhere"
    assert await relay.counts([]) == []


async def test_a_worker_without_the_key_is_refused_and_nothing_is_relayed(
    tmp_path: Path,
) -> None:
    relay = MemoryRelay()
    async with hosting(relay, {NAME: "k-right"}, free_port()) as base:
        await relay.put(
            f"worker.{NAME}",
            RelayRequest(request_id="rly_wait0001", method="GET", path="/v1/health"),
        )
        async with httpx.AsyncClient() as http:
            none = await http.post(f"{base}/next")
            wrong = await http.post(f"{base}/next", headers={"Authorization": "Bearer k-wrong"})
            answered = await http.post(
                f"{base}/answers/rly_wait0001",
                headers={"Authorization": "Bearer k-wrong", "Relay-Status": "200"},
                content=b"{}",
            )
            other = await http.post(
                base.replace(f"/{NAME}/", "/elsewhere/") + "/next",
                headers={"Authorization": "Bearer k-right"},
            )
        assert (none.status_code, wrong.status_code, answered.status_code) == (401, 401, 401)
        assert other.status_code == 404, "a worker not configured as connected"
        with connected(base, tmp_path, "k-wrong"):
            await asyncio.sleep(1.0)
        assert await relay.answer("rly_wait0001") is None
        taken = await relay.take(f"worker.{NAME}")
        assert taken is not None, "the request was never taken for a worker without the key"


async def test_a_request_nobody_answers_times_out_and_is_removed() -> None:
    relay = MemoryRelay()
    async with connected_worker(relay, f"worker.{NAME}", timeout=0.3) as worker:
        with pytest.raises(Exception, match="over the outbound binding"):
            await worker.capabilities()
    assert await relay.take(f"worker.{NAME}") is None, "done: nothing is left in the relay"
