"""Where a run's control sits: the run component's port `ExternalControl` (UC-5.2, ADR-0272).

`TaskControl.withdrawn` reads the run's process version. A coupled one — Taktus decides — is
never withdrawn. For a decoupled one it reads the task's state from the external tool that holds
control, through the connector that serves the capability of `control.task.operation`, as a read,
with the run's inputs where the task names them; a state the version lists under `withdrawn`
stops the run at the boundary it is at. A tool that cannot be read now withdraws nothing: the
run is not stopped on a guess, and the failed read is logged.

This is wiring, because the version is the process component's, the run the run component's,
and the tool is reached through a connector.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import structlog

from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.domain.model import Run
from taktus.components.run.domain.model.work import select
from taktus.components.run.ports import ConnectorPool
from taktus.ports.connector import CallContext, Effect
from taktus.ports.persistence import Repository, UnitOfWork
from taktus.ports.worker import CredentialReference

log = structlog.get_logger("taktusd")


class TaskControl:
    def __init__(
        self,
        *,
        versions: Repository[ProcessVersion],
        connectors: ConnectorPool,
        work: UnitOfWork,
    ) -> None:
        self._versions = versions
        self._connectors = connectors
        self._work = work
        self._boundaries: dict[str, int] = {}

    async def withdrawn(self, run: Run) -> str | None:
        async with self._work.transaction(run.tenant):
            version = await self._versions.get(run.tenant, run.process_version)
        task = None if version is None else version.control.task
        if task is None:
            return None
        resolved = await self._connectors.resolve(task.capability)
        name = task.operation
        operation = None if resolved is None else resolved.declaration.operation(name)
        if resolved is None or operation is None or operation.effect is not Effect.READ:
            log.warning(
                "the task's state of a decoupled run is not read: no connector reads it",
                run=run.id,
                operation=task.operation,
            )
            return None
        boundary = self._boundaries.get(run.id, 0) + 1
        self._boundaries[run.id] = boundary
        mark = hashlib.sha256(f"{run.tenant}:{run.id}:{boundary}".encode()).hexdigest()[:40]
        context = CallContext(
            tenant=run.tenant,
            identity=run.identity,
            run_id=run.id,
            step_id="control",
            attempt=1,
            idempotency_key=f"taktus:control:{mark}",
            credentials=tuple(
                CredentialReference(name=need.name, injected_as="env")
                for need in resolved.declaration.credentials
                if need.purpose == "actions"
            ),
        )
        try:
            answered = await resolved.connector.call(name, context, _given(task.input, run))
            state = select(answered.output, task.select)
        except Exception as error:  # an unread state withdraws nothing
            log.warning(
                "the task's state of a decoupled run could not be read",
                run=run.id,
                error=f"{type(error).__name__}: {error}",
            )
            return None
        if str(state) not in task.withdrawn:
            return None
        return (
            f"the external tool that holds control withdrew the task: {task.select} is "
            f"{state!s}, read through {task.operation}; the run goes no further (UC-5.2)"
        )


def _given(declared: Mapping[str, Any], run: Run) -> dict[str, Any]:
    """The read's input: fixed values as declared, `{$input: <name>}` as the run's input."""
    given: dict[str, Any] = {}
    for key, value in declared.items():
        if isinstance(value, Mapping) and "$input" in value:
            given[key] = run.inputs.get(str(value["$input"]))
        else:
            given[key] = value
    return given
