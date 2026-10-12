"""A worker that is silent is not a worker that is gone (live run of #74, 2026-10-12).

The coding agent ran the tests for minutes and sent nothing; the client counted every idle
timeout as a broken stream and gave up after three, while the worker still worked. Now a silence
costs no attempt while the worker answers for the assignment and it runs; attempts are counted
between two events; and the whole stream stays bounded by `stream_timeout`.
"""

from __future__ import annotations

import json

import httpx
import pytest

from taktus.adapters.driven.workers.http import HttpWorker
from taktus.ports.worker import WorkerError

ASSIGNMENT = "asg_01J8R3K5Q2N7VX9M4T6B0DPHWE"


def event(seq: int, kind: str = "step.progress") -> str:
    body: dict[str, object] = {
        "assignment_id": ASSIGNMENT,
        "seq": seq,
        "ts": "2026-10-12T10:00:00Z",
        "type": kind,
    }
    if kind == "step.progress":
        body |= {"step_id": "s1", "message": f"working {seq}"}
    else:
        body |= {"outcome": "succeeded", "summary": "done"}
    return f"id: {seq}\ndata: {json.dumps(body)}\n\n"


def state(status: str) -> httpx.Response:
    body: dict[str, object] = {"assignment_id": ASSIGNMENT, "status": status, "last_seq": 1}
    if status == "finished":
        body["outcome"] = "failed"
    return httpx.Response(200, json=body)


def worker(handler: object, **options: float) -> HttpWorker:
    client = HttpWorker("http://worker.invalid", reconnects=3, **options)  # type: ignore[arg-type]
    client._http = httpx.AsyncClient(  # the transport is the test's
        base_url="http://worker.invalid",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )
    return client


async def test_a_silent_worker_that_still_works_is_read_to_the_end() -> None:
    """Five silences, more than the three attempts, then the rest of the work."""
    streams = iter([event(1)] + [None] * 5 + [event(2) + event(3, "assignment.finished")])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events"):
            chunk = next(streams)
            if chunk is None:
                raise httpx.ReadTimeout("idle", request=request)
            return httpx.Response(200, text=chunk, headers={"Content-Type": "text/event-stream"})
        return state("running")

    client = worker(handler)
    seen = [e.seq async for e in client.events(ASSIGNMENT)]
    assert seen == [1, 2, 3]


async def test_a_worker_that_is_gone_still_ends_the_stream_after_its_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("idle", request=request)

    client = worker(handler)
    with pytest.raises(WorkerError, match="did not come back"):
        [e async for e in client.events(ASSIGNMENT)]


async def test_a_finished_assignment_s_silence_counts_as_an_attempt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events"):
            raise httpx.ReadTimeout("idle", request=request)
        return state("finished")

    client = worker(handler)
    with pytest.raises(WorkerError, match="did not come back"):
        [e async for e in client.events(ASSIGNMENT)]


async def test_a_stream_that_never_finishes_ends_at_its_bound() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events"):
            raise httpx.ReadTimeout("idle", request=request)
        return state("running")

    client = worker(handler, stream_timeout=0.2)
    with pytest.raises(WorkerError, match="did not finish within"):
        [e async for e in client.events(ASSIGNMENT)]
