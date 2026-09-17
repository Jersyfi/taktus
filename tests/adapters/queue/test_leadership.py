"""The leadership port: one leader per role, the second waits, and a leader that dies is
replaced (ADR-0002: the scheduler is a single instance elected by an advisory lock)."""

from __future__ import annotations

import os

from .conftest import Backend


def role() -> str:
    return "scheduler-" + os.urandom(4).hex()


async def test_exactly_one_instance_leads_and_the_second_waits(backend: Backend) -> None:
    name = role()
    first = await backend.leadership.try_lead(name)
    assert first is not None and await first.held()
    assert await backend.leadership.try_lead(name) is None, "the second does not lead"
    other = await backend.leadership.try_lead(role())
    assert other is not None, "another role is free"
    await other.release()
    await first.release()
    assert not await first.held()
    second = await backend.leadership.try_lead(name)
    assert second is not None and await second.held(), "released, the next takes over"
    await second.release()


async def test_a_leader_that_dies_is_replaced(backend: Backend) -> None:
    name = role()
    first = await backend.leadership.try_lead(name)
    assert first is not None
    await backend.sever(first)
    assert not await first.held(), "a lead does not outlive its holder"
    second = await backend.leadership.try_lead(name)
    assert second is not None and await second.held()
    await second.release()
