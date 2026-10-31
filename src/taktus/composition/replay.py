"""The replay of a recorded run, wired (ADR-0108).

`replay` takes a bundle and a recording of a real run of that process, registers the bundle in
a tenant of its own, and runs it once as a rehearsal through an engine whose every step that
would leave it is answered by the recording (`adapters/driven/replay`). Rules, admission, the
step boundaries — anchors, a step's own `ask`, the level — conditions and the engine's handling
of each step run as in any run, against the stores it is given. Nothing outside is reached:
the engine has no configured worker, connector or model, only the recording.

The replay starts under the recorded run's identifier, with its inputs, the budget it ended
with and its margin, so that what a step derives from them — an idempotency key, a template
naming the run — is what the recorded step derived. Waits do not wait: the clock advances by
what a step would have slept. The verdict is the list of differences between the replayed
run's step states and the recorded ones (`components/run/domain/service/replay.py`); none is
a replay that came where its recording came.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers, SystemRandomness
from taktus.adapters.driven.memory import (
    MemoryBackupLog,
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProjectionStore,
    MemoryProvenanceStore,
    MemoryRepository,
    MemoryTenantStore,
)
from taktus.adapters.driven.postgres import (
    PostgresBackupLog,
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProjectionStore,
    PostgresProvenanceStore,
    PostgresRepository,
    PostgresTenantStore,
)
from taktus.adapters.driven.replay import Recording, ReplayPools, read
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.identity.domain.model import (
    BrowserSession,
    ChannelLink,
    Identity,
    LinkCode,
    RoleRights,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.service.replay import RecordedEnd, RecordedStep, differences
from taktus.composition.decisions import decision_wiring
from taktus.composition.levels import VersionStatements
from taktus.composition.local import Stores
from taktus.ports.model import PriceTable
from taktus.ports.persistence import Repository, Stored
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, Plan, ReplyTo

ACTOR = "idn_replay"
"""Who the replay acts for: no person. The recording names nobody."""
CHANNEL = "channel.replay"


class ReplayClock:
    """The wall clock, advanced by every sleep instead of waiting it out: a wait polls as
    often as it would, and takes no time."""

    def __init__(self) -> None:
        self._clock = SystemClock()
        self._ahead = timedelta()

    def now(self) -> datetime:
        return self._clock.now() + self._ahead

    async def sleep(self, seconds: float) -> None:
        self._ahead += timedelta(seconds=seconds)


@dataclass(frozen=True)
class Replayed:
    """One replay: the recording it came from, the run it made, and how that run differs."""

    recording: Recording
    run: Run
    differences: tuple[str, ...]

    @property
    def held(self) -> bool:
        return not self.differences


def recorded_steps(recording: Recording) -> tuple[RecordedStep, ...]:
    return tuple(
        RecordedStep(step_id=s.id, state=StepState(s.state), met_a_person=s.met_a_person)
        for s in recording.steps
    )


def recorded_end(recording: Recording) -> RecordedEnd:
    return RecordedEnd(
        state=RunState(recording.state),
        cause=None if recording.cause is None else Cause(recording.cause),
    )


def bundle_of(path: Path) -> dict[str, Any]:
    """A bundle file as its document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} holds no bundle")
    return document


@asynccontextmanager
async def stores(database: str | None) -> AsyncIterator[Stores]:
    """The stores a replay runs against: the database the URL names, or memory."""
    if database is None:
        memory = MemoryPersistence()

        def in_memory[T: Stored](kind: type[T]) -> Repository[T]:
            return MemoryRepository(memory, kind)

        yield Stores(
            work=memory,
            of=in_memory,
            ledger_store=MemoryLedgerStore(memory),
            provenance_store=MemoryProvenanceStore(memory),
            tenants=MemoryTenantStore(memory),
            projection_store=MemoryProjectionStore(memory),
            backups=MemoryBackupLog(memory),
            storage="memory",
        )
        return
    postgres = PostgresPersistence(database)
    try:

        def in_postgres[T: Stored](kind: type[T]) -> Repository[T]:
            return PostgresRepository(postgres, kind)

        yield Stores(
            work=postgres,
            of=in_postgres,
            ledger_store=PostgresLedgerStore(postgres),
            provenance_store=PostgresProvenanceStore(postgres),
            tenants=PostgresTenantStore(postgres),
            projection_store=PostgresProjectionStore(postgres),
            backups=PostgresBackupLog(postgres),
            storage="database",
        )
    finally:
        await postgres.close()


async def replay(bundle: Mapping[str, Any] | Path, directory: Path, store: Stores) -> Replayed:
    """Replay the recording in `directory` with the bundle, in a tenant made for it, and say
    how the run it makes differs from the recorded one."""
    recording = read(directory)
    document = dict(bundle) if isinstance(bundle, Mapping) else bundle_of(bundle)
    if document.get("id") != recording.process:
        raise ValueError(
            f"the recording in {directory} is of {recording.process}, not of {document.get('id')}"
        )
    clock = ReplayClock()
    ids = SystemIdentifiers()
    ledger = ChainedLedger(store.ledger_store, clock, store.projection_store)
    registry = TenantRegistry(
        store=store.tenants, work=store.work, ledger=ledger, clock=clock, ids=ids
    )
    # A tenant of its own: the run takes the recorded run's identifier, which is unique only
    # within a tenant (ADR-0104).
    tenant = (await registry.create(f"replay of {recording.run_id}", by=ACTOR)).id
    identities = IdentityDirectory(
        tenants=registry,
        identities=store.of(Identity),
        links=store.of(ChannelLink),
        codes=store.of(LinkCode),
        sessions=store.of(BrowserSession),
        rights=store.of(RoleRights),
        work=store.work,
        ledger=ledger,
        clock=clock,
        randomness=SystemRandomness(),
    )
    decisions = decision_wiring(store.of, store.work, ledger, clock, identities)
    version = await RegisterProcessVersionHandler(
        store.of(ProcessVersion), store.work, store.of(Process), ledger=ledger, clock=clock
    ).execute(RegisterProcessVersion(document, tenant=tenant, by=ACTOR))
    prices = None if recording.prices is None else PriceTable.model_validate(recording.prices)
    options = EngineOptions(prices=prices, margin=recording.margin)
    if recording.uncalibrated_margin is not None:
        options = replace(options, uncalibrated_margin=recording.uncalibrated_margin)
    runs = store.of(Run)
    engine = RunEngine(
        runs=runs,
        work=store.work,
        objects=MemoryObjectStore(),
        ledger=ledger,
        provenance=store.provenance_store,
        workers=StaticWorkerPool([]),
        clock=clock,
        ids=ids,
        telemetry=NoTelemetry(),
        options=options,
        anchors=decisions.anchors,
        decisions=decisions.requests,
        replay=ReplayPools(recording, directory),
        statements=VersionStatements(store.work, store.of(ProcessVersion)),
    )
    command = Command(
        id=ids.new("cmd"),
        channel=CHANNEL,
        identity=ACTOR,
        org_path=(tenant,),
        intent=Intent(raw=f"replay {recording.run_id} of {version.ref}", recognised="process.run"),
        context={"inputs": dict(recording.inputs), "replay": recording.run_id},
        reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
        received_at=clock.now(),
    )
    plan = await CommissionPlanHandler(
        store.of(Command), store.of(Plan), store.work, clock, ids
    ).execute(
        CommissionPlan(
            command=command,
            tenant=tenant,
            goal=f"replay {recording.run_id}: run {version.name} ({version.ref})",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    run = await engine.start(
        StartRun(
            org_unit=command.org_unit,
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(recording.budget),
            process_version=version.ref,
            actor=ACTOR,
            tenant=tenant,
            inputs=dict(recording.inputs),
            margin=recording.margin,
            rehearsal=True,
            run_id=recording.run_id,
            actions=version.autonomy.action_levels,
        )
    )
    found = differences(recorded_steps(recording), recorded_end(recording), run)
    return Replayed(recording=recording, run=run, differences=found)
