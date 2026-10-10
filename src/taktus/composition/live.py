"""The streams of changes a replica holds, and how it feeds them (ADR-0055 §2, §6, §7).

One `LiveHub` per process of the `api` role. It holds the streams its readers opened, by
tenant, and feeds them from the tenant's ledger:

- it listens to the ledger signal (`ports/signal.py`); a signal for a tenant with open streams
  wakes that tenant's reading;
- signals that arrive within `batch_seconds` of each other are read as one batch;
- a tenant with open streams that received no signal for `poll_seconds` is read anyway, so that
  a lost signal costs at most that interval and never a change;
- one read per tenant per batch, from the oldest position any of its streams holds, however
  many streams there are; each stream receives the entries after its own position.

What a stream receives is decided when it is sent: the reader's key is asked again, the scope
and the one predicate of `reporting` are applied with the roles as they are then, and a key
that no longer proves an identity ends the stream (ADR-0055 §5). A heartbeat is sent every
`heartbeat_seconds` from the stream's opening, whatever happens unseen, so that its interval
says nothing.

The time from an entry's recorded moment to its hand-over to a stream is observed as the
histogram `change.handover` (seconds).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field

import structlog

from taktus.adapters.driving.rest.wiring import StreamsFull
from taktus.components.decision.domain.model import status_after
from taktus.components.reporting.application.service import LiveChanges, Pending
from taktus.components.reporting.domain.model import (
    Change,
    Reader,
    RunRef,
    Scope,
    Snapshot,
    SnapshotRun,
    SnapshotStep,
    StateAfter,
)
from taktus.components.reporting.ports import TenantState
from taktus.components.run.domain.model import Run, led_to
from taktus.ports.clock import Clock
from taktus.ports.persistence import LedgerStore, Repository, Tenant, UnitOfWork
from taktus.ports.signal import LedgerSignal
from taktus.ports.telemetry import Telemetry
from taktus.shared.v1 import LedgerEntry

log = structlog.get_logger("taktus.live")

HANDOVER = "change.handover"
"""The histogram of the time from an entry's recorded moment to its hand-over to a stream."""

type Authenticate = Callable[[], Awaitable[Reader | None]]
type Event = Snapshot | Change | None
"""What a stream yields: a snapshot, a change, or None for a heartbeat."""


def state_of(kind: str, outcome: str | None) -> StateAfter | None:
    """The states an entry led to, as the run and the decision component publish them."""
    led = led_to(kind, outcome)
    if led is not None:
        return StateAfter(
            run=None if led.run is None else str(led.run),
            step=None if led.step is None else str(led.step),
        )
    status = status_after(kind, outcome)
    return None if status is None else StateAfter(decision_request=str(status))


class Records:
    """The records the stream reads, over the ledger store and the run's repository."""

    def __init__(self, work: UnitOfWork, store: LedgerStore, runs: Repository[Run]) -> None:
        self._work = work
        self._store = store
        self._runs = runs

    async def state(self, tenant: Tenant) -> TenantState:
        async with self._work.transaction(tenant, consistent=True):
            runs = await self._runs.list(tenant)
            seq = await self._store.head(tenant)
            newest = await self._store.after(tenant, seq - 1, limit=1) if seq else []
        return TenantState(
            seq=seq,
            position=newest[0].hash if newest else None,
            runs=[(_ref(r), _shown(r)) for r in sorted(runs, key=lambda r: r.created_at)],
        )

    async def head(self, tenant: Tenant) -> int:
        async with self._work.transaction(tenant):
            return await self._store.head(tenant)

    async def position(self, tenant: Tenant, hash: str) -> int | None:
        async with self._work.transaction(tenant):
            return await self._store.position(tenant, hash)

    async def after(self, tenant: Tenant, seq: int, *, limit: int) -> Sequence[LedgerEntry]:
        async with self._work.transaction(tenant):
            return await self._store.after(tenant, seq, limit=limit)

    async def runs(self, tenant: Tenant, ids: Sequence[str]) -> Mapping[str, RunRef]:
        found: dict[str, RunRef] = {}
        async with self._work.transaction(tenant):
            for run_id in ids:
                run = await self._runs.get(tenant, run_id)
                if run is not None:
                    found[run_id] = _ref(run)
        return found


def _ref(run: Run) -> RunRef:
    return RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)


def _shown(run: Run) -> SnapshotRun:
    states = {s.step_id: s for s in run.step_runs}
    return SnapshotRun(
        id=run.id,
        process_version=run.process_version,
        state=str(run.state),
        rehearsal=run.rehearsal,
        steps=tuple(
            SnapshotStep(
                id=step.id,
                state=str(states[step.id].state) if step.id in states else "planned",
                method=step.method,
            )
            for step in run.steps
        ),
    )


@dataclass(frozen=True)
class LiveOptions:
    max_streams: int = 500
    poll_seconds: float = 2.0
    batch_seconds: float = 0.25
    heartbeat_seconds: float = 15.0
    page: int = 500
    """How many entries one read takes at most; a read continues until it is through."""


@dataclass(eq=False)
class _Stream:
    reader: Reader
    scope: Scope
    authenticate: Authenticate
    seq: int
    """The sequence number of the last entry handed to this stream."""
    queue: asyncio.Queue[list[Pending] | None] = field(default_factory=asyncio.Queue)
    """Batches of changes to send; None ends the stream."""


class LiveHub:
    def __init__(
        self,
        changes: LiveChanges,
        signal: LedgerSignal | None,
        telemetry: Telemetry,
        clock: Clock,
        options: LiveOptions | None = None,
    ) -> None:
        self._changes = changes
        self._signal = signal
        self._telemetry = telemetry
        self._clock = clock
        self._options = options or LiveOptions()
        self._streams: dict[Tenant, set[_Stream]] = {}
        self._wakes: dict[Tenant, asyncio.Event] = {}
        self._readers: dict[Tenant, asyncio.Task[None]] = {}
        self._closed = False

    @property
    def open_streams(self) -> int:
        return sum(len(s) for s in self._streams.values())

    async def listen(self) -> None:
        """Wake the tenants the signal names, until cancelled. Without a signal, the interval
        read alone feeds the streams."""
        if self._signal is None:
            return
        async for tenant in self._signal.tenants():
            wake = self._wakes.get(tenant)
            if wake is not None:
                wake.set()

    async def open(
        self, reader: Reader, scope: Scope, position: str | None, authenticate: Authenticate
    ) -> AsyncIterator[Event]:
        """A new stream: its snapshot or what it missed first, then every change as it happens.
        `StreamsFull` when this replica holds its maximum already."""
        if self._closed or self.open_streams >= self._options.max_streams:
            raise StreamsFull(self._options.max_streams)
        opening = await self._changes.open(reader, scope, position)
        stream = _Stream(reader, scope, authenticate, opening.seq)
        tenant = reader.tenant
        self._streams.setdefault(tenant, set()).add(stream)
        self._wakes.setdefault(tenant, asyncio.Event()).set()
        if tenant not in self._readers or self._readers[tenant].done():
            self._readers[tenant] = asyncio.create_task(self._follow(tenant), name=f"live:{tenant}")
        return self._events(stream, opening.snapshot)

    def close(self) -> None:
        """End every stream: the replica stops, and its readers reconnect to another."""
        self._closed = True
        for streams in self._streams.values():
            for stream in streams:
                stream.queue.put_nowait(None)
        for task in self._readers.values():
            task.cancel()

    async def _events(self, stream: _Stream, snapshot: Snapshot | None) -> AsyncIterator[Event]:
        loop = asyncio.get_running_loop()
        interval = self._options.heartbeat_seconds
        beat = loop.time() + interval
        try:
            if snapshot is not None:
                yield snapshot
            while True:
                try:
                    async with asyncio.timeout(max(beat - loop.time(), 0)):
                        item = await stream.queue.get()
                except TimeoutError:
                    if await stream.authenticate() is None:
                        return
                    beat += interval
                    yield None
                    continue
                if item is None:
                    return
                reader = await stream.authenticate()
                if reader is None:
                    return
                for change in self._changes.visible(reader, stream.scope, item):
                    delay = (self._clock.now() - change.recorded_at).total_seconds()
                    self._telemetry.observe(HANDOVER, max(delay, 0.0), unit="s")
                    yield change
        finally:
            self._drop(stream)

    def _drop(self, stream: _Stream) -> None:
        streams = self._streams.get(stream.reader.tenant)
        if streams is not None:
            streams.discard(stream)

    async def _follow(self, tenant: Tenant) -> None:
        """Read the tenant's ledger for its streams while it has any."""
        wake = self._wakes[tenant]
        options = self._options
        while self._streams.get(tenant):
            try:
                async with asyncio.timeout(options.poll_seconds):
                    await wake.wait()
                # Signals that follow within the batch window are read with this one.
                await asyncio.sleep(options.batch_seconds)
            except TimeoutError:
                pass
            wake.clear()
            try:
                await self._read(tenant)
            except Exception as error:  # the next wake or interval reads again
                log.warning("live: reading the ledger failed", error=type(error).__name__)
        self._readers.pop(tenant, None)

    async def _read(self, tenant: Tenant) -> None:
        streams = list(self._streams.get(tenant, ()))
        if not streams:
            return
        # A stream opened during this read is not among them: the next read serves it.
        after = min(s.seq for s in streams)
        while True:
            read = await self._changes.read(tenant, after, limit=self._options.page)
            if read.through == after:
                return
            for stream in streams:
                handed = [p for p in read.pending if p.seq > stream.seq]
                if handed:
                    stream.queue.put_nowait(handed)
                stream.seq = max(stream.seq, read.through)
            after = read.through


async def run_listener(hub: LiveHub, stop: asyncio.Event) -> None:
    """The listener, for the life of the process: ends the streams when the process stops."""
    listening = asyncio.create_task(hub.listen(), name="live-signal")
    try:
        await stop.wait()
    finally:
        hub.close()
        listening.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listening
