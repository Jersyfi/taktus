"""The relay port of the outbound binding (ADR-0156 §1), against memory and PostgreSQL.

A request is taken once, by one host; its answer is begun once and counted however often it is
posted; its body arrives in order and ends; a request nobody reads any more is gone, and a host
still appending learns so. A tenant's unit of work never sees a request in flight.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from taktus.adapters.driven.memory import MemoryRelay
from taktus.adapters.driven.postgres import PostgresPersistence, PostgresRelay
from taktus.ports.relay import Relay
from taktus.ports.worker import RelayRequest

WORKER = "worker.site"
OTHER = "worker.other"
RUN = ""
"""The database is shared by the tests of a session: every request identifier is one test's own."""


@pytest.fixture(autouse=True)
def fresh() -> None:
    global RUN, WORKER, OTHER
    RUN = os.urandom(4).hex()
    WORKER, OTHER = f"worker.site-{RUN}", f"worker.other-{RUN}"


def rid(n: int) -> str:
    return f"rly_{RUN}{n:04d}"


def request(n: int) -> RelayRequest:
    return RelayRequest(request_id=rid(n), method="GET", path="/v1/capabilities")


@pytest.fixture(params=("memory", "postgres"))
async def relay(request: pytest.FixtureRequest) -> AsyncIterator[Relay]:
    if request.param == "memory":
        yield MemoryRelay()
        return
    persistence = PostgresPersistence(request.getfixturevalue("postgres_url"), pool_size=4)
    try:
        yield PostgresRelay(persistence)
    finally:
        await persistence.close()


async def test_a_request_is_taken_once_in_order_and_only_for_its_worker(relay: Relay) -> None:
    await relay.put(WORKER, request(1))
    await relay.put(WORKER, request(2))
    await relay.put(OTHER, request(3))
    taken = await asyncio.gather(*(relay.take(WORKER) for _ in range(4)))
    ids = sorted(r.request_id for r in taken if r is not None)
    assert ids == [rid(1), rid(2)], "two polls never take the same one"
    assert await relay.take(WORKER) is None
    other = await relay.take(OTHER)
    assert other is not None and other.request_id == rid(3)


async def test_an_answer_is_begun_once_counted_each_time_and_read_in_order(relay: Relay) -> None:
    await relay.put(WORKER, request(1))
    assert await relay.begin(WORKER, rid(1), 200, None) == "unknown", "not taken yet"
    assert await relay.take(WORKER) is not None
    assert await relay.answer(rid(1)) is None
    assert await relay.begin(OTHER, rid(1), 200, None) == "unknown"
    assert await relay.begin(WORKER, rid(1), 200, "text/event-stream") == "begun"
    assert await relay.begin(WORKER, rid(1), 500, None) == "answered"
    head = await relay.answer(rid(1))
    assert head is not None and (head.status, head.content_type) == (200, "text/event-stream")
    assert await relay.append(rid(1), 1, b"one")
    assert await relay.append(rid(1), 2, b"two")
    first = await relay.chunks(rid(1), 0)
    assert [c for _, c in first.chunks] == [b"one", b"two"] and not first.ended
    await relay.end(rid(1))
    rest = await relay.chunks(rid(1), 1)
    assert [c for _, c in rest.chunks] == [b"two"] and rest.ended
    (count,) = await relay.counts([rid(1), rid(9999)])
    assert (count.answers, count.status) == (2, 200), "every answer posted is counted"


async def test_a_request_done_is_gone_and_its_host_stops_appending(relay: Relay) -> None:
    await relay.put(WORKER, request(1))
    await relay.take(WORKER)
    await relay.begin(WORKER, rid(1), 200, None)
    await relay.done(rid(1))
    assert not await relay.append(rid(1), 1, b"late")
    assert (await relay.chunks(rid(1), 0)).gone
    assert await relay.begin(WORKER, rid(1), 200, None) == "unknown"


async def test_an_old_request_is_purged(relay: Relay) -> None:
    await relay.put(WORKER, request(1))
    assert await relay.purge(datetime.now(UTC) - timedelta(hours=1)) == 0
    assert await relay.purge(datetime.now(UTC) + timedelta(seconds=5)) >= 1
    assert await relay.take(WORKER) is None


async def test_a_tenant_s_transaction_sees_no_request_in_flight(postgres_url: str) -> None:
    persistence = PostgresPersistence(postgres_url, pool_size=2)
    try:
        await PostgresRelay(persistence).put(WORKER, request(1))
        async with persistence.engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE taktus_app"))
            await connection.execute(text("SELECT set_config('taktus.tenant', 't', true)"))
            seen = await connection.scalar(text("SELECT count(*) FROM worker_relay"))
        assert seen == 0, "row security admits only the relay's own transactions"
    finally:
        await persistence.close()
