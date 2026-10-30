"""The processes a person may start, and a start as the person, from any channel (ADR-0131,
UC-1.11, ADR-0159, UC-1.13).

- **The processes a reader may start.** Every process with an active version, asked of the
  visibility predicate the levels are read through, with the inputs its version takes. The
  catalogue of UC-1.13 is the same list in plain words, with how to start each entry on each
  channel (`reporting/domain/service/catalogue.py`).
- **A process started as the person.** The active version runs through the one path every
  channel takes (control-plane.md §1): the one start command of
  `command/domain/service/start.py` on the channel that asked — `channel.agent` for a person's
  own agent, `channel.web` for the web app's list, the owner's conversation for the chat — a
  commissioned plan, a run submitted to the queue with a job. The command and the run act as
  the person; a runner executes the run like any other. An input the version requires and the
  call does not give refuses the start, naming each.
- **Every call recorded.** One ledger entry per call, `agent.<tool>`, with the person as actor,
  the outcome, the run where the call names one, and the digest of the tool's name and
  arguments. The arguments are kept nowhere: the ledger stays content-free (ADR-0006). No
  measure is computed from these entries per person (principle 14).

Whether the person holds the right to act is asked of the identity component by the surface
before it calls here. This is wiring, because starting a process crosses the process, command
and run components, and only the composition root may hold them all (`composition/README.md`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from taktus.adapters.driving.rest.wiring import StartRefused
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.command.domain.service.start import start_command
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model import OwnerChannel, ProcessRef, Reader
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.domain.service.catalogue import (
    Catalogue,
    CatalogueFacts,
    CatalogueInput,
    catalogue,
)
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunError
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import Resolution
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import LedgerRefs, ReplyTo

CHANNEL = "channel.agent"
"""The channel a process started by a person's own agent arrives on (ADR-0131 §5)."""


def _reader(who: Resolution) -> Reader:
    return Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)


class AgentSurface:
    def __init__(
        self,
        *,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        commission: CommissionPlanHandler,
        engine: RunEngine,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
        channels: Repository[OwnerChannel] | None = None,
    ) -> None:
        self._channels = channels
        self._processes = processes
        self._versions = versions
        self._commission = commission
        self._engine = engine
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids

    async def processes(self, who: Resolution) -> Sequence[Mapping[str, Any]]:
        reader = _reader(who)
        listed: list[Mapping[str, Any]] = []
        for process, version in await self._active(who.tenant):
            if not visibility.may_see_process(reader, ProcessRef(id=process.id, tenant=who.tenant)):
                continue
            listed.append(
                {
                    "process": process.id,
                    "name": process.name,
                    "description": process.description,
                    "version": version.ref,
                    "inputs": {
                        name: {
                            "description": declared.description,
                            "required": declared.required,
                            "example": declared.example,
                        }
                        for name, declared in version.inputs.items()
                    },
                }
            )
        return listed

    async def catalogue(self, who: Resolution, *, agent_may_start: bool) -> Catalogue:
        """What `who` may ask Taktus for (UC-1.13): every process with an active version they
        may see, with how to start it on each channel."""
        reader = _reader(who)
        facts = [
            CatalogueFacts(
                process=process.id,
                name=process.name,
                description=process.description,
                version=version.ref,
                level=version.autonomy_level,
                inputs=tuple(
                    CatalogueInput(
                        name=name,
                        description=declared.description,
                        required=declared.required,
                        example=declared.example,
                    )
                    for name, declared in version.inputs.items()
                ),
                roles=tuple(r for s in version.ordered() if (r := s.performer) is not None),
            )
            for process, version in await self._active(who.tenant)
            if visibility.may_see_process(reader, ProcessRef(id=process.id, tenant=who.tenant))
        ]
        return catalogue(
            facts, agent_may_start=agent_may_start, chat_word=await self._chat_word(who.tenant)
        )

    async def _chat_word(self, tenant: Tenant) -> str | None:
        """The first word the tenant's owner conversation reads a start by; None where it has
        none, or reads no start."""
        if self._channels is None:
            return None
        async with self._work.transaction(tenant):
            found = await self._channels.get(tenant, tenant)
        words = None if found is None else found.phrasebook.start_words
        return words[0] if words else None

    async def start(
        self,
        who: Resolution,
        process_id: str,
        inputs: Mapping[str, Any],
        *,
        channel: str = CHANNEL,
        address: str = "ledger",
    ) -> Run:
        """The active version started as `who`, by the one start command, on `channel`."""
        version = await self._version(who, process_id)
        missing = [name for name in version.required_inputs if name not in inputs]
        if missing:
            raise StartRefused(f"{version.ref} needs the input(s) {', '.join(missing)}")
        if version.limits is None:
            raise StartRefused(f"{version.ref} names no `limits`; a run needs a budget")
        try:
            budget = Limits.model_validate(dict(version.limits))
        except ValueError as error:
            raise StartRefused(f"{version.ref}: `limits`: {error}") from error
        given = dict(inputs)
        command = start_command(
            id=self._ids.new("cmd"),
            channel=channel,
            identity=who.identity,
            org_path=who.org_path,
            process_version=version.ref,
            inputs=given,
            reply_to=ReplyTo(channel=channel, address=address),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=who.tenant,
                goal=f"run process {version.name} ({version.ref}), started on {channel}",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        try:
            return await self._engine.submit(
                StartRun(
                    plan=plan,
                    work=version.work,
                    budget=budget,
                    process_version=version.ref,
                    actor=who.identity,
                    tenant=who.tenant,
                    inputs=given,
                    actions=version.autonomy.action_levels,
                )
            )
        except RunError as error:
            raise StartRefused(str(error)) from error

    async def called(
        self,
        who: Resolution,
        tool: str,
        outcome: str,
        arguments: Mapping[str, Any],
        run_id: str | None = None,
    ) -> None:
        canonical = json.dumps(
            {"tool": tool, "arguments": arguments}, ensure_ascii=False, sort_keys=True, default=str
        )
        async with self._work.transaction(who.tenant):
            await self._ledger.record(
                who.tenant,
                Fact(
                    kind=f"agent.{tool}",
                    refs=LedgerRefs(tenant=who.tenant, run_id=run_id, actor=who.identity),
                    outcome=outcome,
                    content_digest="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
                ),
            )

    async def _active(self, tenant: Tenant) -> list[tuple[Process, ProcessVersion]]:
        found: list[tuple[Process, ProcessVersion]] = []
        async with self._work.transaction(tenant):
            for process in await self._processes.list(tenant):
                if process.active_version is None:
                    continue
                version = await self._versions.get(tenant, f"{process.id}@{process.active_version}")
                if version is not None:
                    found.append((process, version))
        return found

    async def _version(self, who: Resolution, process_id: str) -> ProcessVersion:
        unknown = StartRefused(f"no process {process_id!r} with an active version that you may see")
        if not visibility.may_see_process(
            _reader(who), ProcessRef(id=process_id, tenant=who.tenant)
        ):
            raise unknown
        async with self._work.transaction(who.tenant):
            process = await self._processes.get(who.tenant, process_id)
            version = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(who.tenant, f"{process.id}@{process.active_version}")
            )
        if version is None:
            raise unknown
        return version
