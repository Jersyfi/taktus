"""The trace store keeps a step's lines in order, once each, shares a trace with roles, holds
the tenant's retention and erases what it ended — the same against the memory adapter and
against PostgreSQL (ADR-0135)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adapters.persistence.conftest import Backend
from taktus.ports.traces import DEFAULT_RETENTION_DAYS, TraceLine, TraceRetention, Traces

AT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def line(seq: int, *, step: str = "a", assignment: str = "asg_1", at: datetime = AT) -> TraceLine:
    return TraceLine(
        run_id="run_1",
        step_id=step,
        assignment_id=assignment,
        seq=seq,
        ts=at,
        type="step.progress",
        detail={"step_id": "inner", "message": f"line {seq}"},
        recorded_at=at,
    )


def store(backend: Backend) -> Traces:
    assert backend.traces is not None
    return backend.traces


async def test_lines_take_the_next_position_once_each_and_read_after_one(backend: Backend) -> None:
    tenant = await backend.tenant()
    traces = store(backend)
    async with backend.work.transaction(tenant):
        first = await traces.append(tenant, line(1))
        second = await traces.append(tenant, line(2))
        again = await traces.append(tenant, line(1))
        other_step = await traces.append(tenant, line(1, step="b"))
    async with backend.work.transaction(tenant):
        retried = await traces.append(tenant, line(1, assignment="asg_2"))
    assert first is not None and second is not None and other_step is not None
    assert (first.position, second.position, other_step.position) == (1, 2, 1)
    assert again is None, "an event read again is not stored twice"
    assert retried is not None and retried.position == 3
    async with backend.work.transaction(tenant):
        everything = await traces.lines(tenant, "run_1", "a", limit=10)
        after_one = await traces.lines(tenant, "run_1", "a", after=1, limit=1)
    assert [(x.assignment_id, x.seq, x.position) for x in everything] == [
        ("asg_1", 1, 1),
        ("asg_1", 2, 2),
        ("asg_2", 1, 3),
    ]
    assert everything[0].detail == {"step_id": "inner", "message": "line 1"}
    assert [x.position for x in after_one] == [2]


async def test_a_line_recorded_before_the_cut_is_erased_and_a_later_one_kept(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    traces = store(backend)
    async with backend.work.transaction(tenant):
        await traces.append(tenant, line(1, at=AT - timedelta(days=31)))
        await traces.append(tenant, line(2, at=AT - timedelta(days=1)))
    async with backend.work.transaction(tenant):
        erased = await traces.erase(tenant, AT - timedelta(days=30))
    async with backend.work.transaction(tenant):
        kept = await traces.lines(tenant, "run_1", "a", limit=10)
    assert erased == 1
    assert [x.seq for x in kept] == [2]


async def test_a_trace_is_shared_with_roles_and_a_share_withdrawn(backend: Backend) -> None:
    tenant = await backend.tenant()
    traces = store(backend)
    async with backend.work.transaction(tenant):
        assert await traces.share(tenant, "run_1", "a", "reviewer")
        assert not await traces.share(tenant, "run_1", "a", "reviewer")
        assert await traces.share(tenant, "run_1", "a", "accounting")
    async with backend.work.transaction(tenant):
        assert await traces.shared_with(tenant, "run_1", "a") == ["accounting", "reviewer"]
        assert await traces.shared_with(tenant, "run_1", "b") == []
        assert await traces.unshare(tenant, "run_1", "a", "reviewer")
        assert not await traces.unshare(tenant, "run_1", "a", "reviewer")
    async with backend.work.transaction(tenant):
        assert await traces.shared_with(tenant, "run_1", "a") == ["accounting"]


async def test_the_retention_is_the_default_until_the_tenant_sets_one(backend: Backend) -> None:
    tenant = await backend.tenant()
    traces = store(backend)
    async with backend.work.transaction(tenant):
        assert (await traces.retention(tenant)).days == DEFAULT_RETENTION_DAYS
        await traces.set_retention(tenant, TraceRetention(days=7, configured_at=AT))
    async with backend.work.transaction(tenant):
        assert await traces.retention(tenant) == TraceRetention(days=7, configured_at=AT)


async def test_another_tenant_sees_no_line_and_no_share(backend: Backend) -> None:
    tenant, other = await backend.tenant(), await backend.tenant()
    traces = store(backend)
    async with backend.work.transaction(tenant):
        await traces.append(tenant, line(1))
        await traces.share(tenant, "run_1", "a", "reviewer")
    async with backend.work.transaction(other):
        assert await traces.lines(other, "run_1", "a", limit=10) == []
        assert await traces.shared_with(other, "run_1", "a") == []
