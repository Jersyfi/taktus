"""Documents to rows and back, one mapper per aggregate.

The adapter never imports a component's class (ADR-0003): what it stores is the aggregate's
JSON document — the shape `Value.document()` produces and `model_validate` reads — and the
composition root binds the class. A mapper therefore knows the *document* of one aggregate:
which keys become columns, which stay JSON, which children become rows of their own. The
shared repository suite round-trips the real aggregates through here, so a change to a
document's shape is a red test, not a silent loss.

`put` replaces: the parent row is upserted, the children are deleted and written again, all
inside the caller's transaction. Timestamps travel as ISO 8601 text in a document and as
`timestamptz` in a row; `_at` and `_iso` convert at the boundary.
"""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import Table, and_, delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection

from taktus.adapters.driven.postgres import _schema as s
from taktus.ports.persistence import Mark, NotQueryable, Tenant

type Document = dict[str, Any]
type Rows = list[Row[Any]]


class Mapper(Protocol):
    async def get(
        self, connection: AsyncConnection, tenant: Tenant, id: str
    ) -> Document | None: ...

    async def put(
        self, connection: AsyncConnection, tenant: Tenant, document: Document
    ) -> None: ...

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]: ...


@runtime_checkable
class QueriedMapper(Mapper, Protocol):
    """A mapper that answers the queries of the port's `Queried` from its rows (ADR-0094)."""

    async def newest(
        self, connection: AsyncConnection, tenant: Tenant, limit: int, after: Mark | None
    ) -> list[Document]: ...

    async def count(
        self, connection: AsyncConnection, tenant: Tenant, by: Sequence[str]
    ) -> dict[tuple[Any, ...], int]: ...

    async def having(
        self, connection: AsyncConnection, tenant: Tenant, field: str, value: Any
    ) -> list[Document]: ...


# --- helpers --------------------------------------------------------------------------------------


def _at(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _present(document: Document) -> Document:
    """A document carries no null: an absent optional field is left out."""
    return {key: value for key, value in document.items() if value is not None}


async def _upsert(
    connection: AsyncConnection, table: Table, keys: Sequence[str], row: dict[str, Any]
) -> None:
    statement = insert(table).values(**row)
    await connection.execute(
        statement.on_conflict_do_update(
            index_elements=list(keys),
            set_={name: statement.excluded[name] for name in row if name not in keys},
        )
    )


async def _insert_all(
    connection: AsyncConnection, table: Table, rows: Sequence[dict[str, Any]]
) -> None:
    if rows:
        await connection.execute(insert(table), list(rows))


async def _one(
    connection: AsyncConnection, table: Table, tenant: Tenant, id: str
) -> Row[Any] | None:
    return (
        await connection.execute(select(table).where(table.c.tenant == tenant, table.c.id == id))
    ).first()


async def _all(connection: AsyncConnection, table: Table, tenant: Tenant, *order: Any) -> Any:
    return await connection.execute(select(table).where(table.c.tenant == tenant).order_by(*order))


# --- process --------------------------------------------------------------------------------------


class ProcessMapper:
    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.process, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.process,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "name": document["name"],
                "description": document.get("description"),
                "active_version": document.get("active_version"),
                "activated_by": document.get("activated_by"),
                "activated_at": _at(document.get("activated_at")),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.process, tenant, s.process.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "active_version": row.active_version,
                "activated_by": row.activated_by,
                "activated_at": _iso(row.activated_at),
            }
        )


class ProcessVersionMapper:
    """The version row plus one `step` row per step, in order; `id` is `process_id@version`,
    the key the component defines."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.process_version, tenant, id)
        if row is None:
            return None
        steps = await connection.execute(
            select(s.step)
            .where(s.step.c.tenant == tenant, s.step.c.version_id == id)
            .order_by(s.step.c.position)
        )
        return self._from(row, list(steps))

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        version_id = f"{document['process_id']}@{document['version']}"
        await _upsert(
            connection,
            s.process_version,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": version_id,
                "process_id": document["process_id"],
                "version": document["version"],
                "name": document["name"],
                "autonomy_level": document["autonomy"]["level"],
                "autonomy": document["autonomy"],
                "triggers": document.get("triggers", []),
                "slo": document.get("slo"),
                "expect": document.get("expect"),
                "work": document.get("work", {}),
                "limits": document.get("limits"),
                "open_work": document.get("open_work") or None,
                "deadlines": document.get("deadlines") or None,
                "evaluation": document.get("evaluation"),
                "inputs": document.get("inputs", {}),
                "author": document.get("author"),
                "reason": document.get("reason"),
            },
        )
        await connection.execute(
            delete(s.step).where(s.step.c.tenant == tenant, s.step.c.version_id == version_id)
        )
        await _insert_all(
            connection,
            s.step,
            [
                {
                    "tenant": tenant,
                    "version_id": version_id,
                    "position": position,
                    **_step_row(step),
                }
                for position, step in enumerate(document["steps"])
            ],
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.process_version, tenant, s.process_version.c.id)
        steps = await _all(connection, s.step, tenant, s.step.c.position)
        by_version: dict[str, Rows] = {}
        for step in steps:
            by_version.setdefault(step.version_id, []).append(step)
        return [self._from(row, by_version.get(row.id, [])) for row in rows]

    @staticmethod
    def _from(row: Row[Any], steps: Sequence[Row[Any]]) -> Document:
        return _present(
            {
                "process_id": row.process_id,
                "version": row.version,
                "name": row.name,
                "autonomy": row.autonomy,
                "steps": [_step_from(step) for step in steps],
                "triggers": row.triggers,
                "slo": row.slo,
                "expect": row.expect,
                "work": row.work,
                "limits": row.limits,
                "open_work": row.open_work,
                "deadlines": row.deadlines,
                "evaluation": row.evaluation,
                "inputs": row.inputs,
                "author": row.author,
                "reason": row.reason,
            }
        )


def _step_row(step: Document) -> dict[str, Any]:
    return {
        "id": step["id"],
        "method": step["method"],
        "reason": step["reason"],
        "rejected": step["rejected"],
        "exactness": step.get("exactness"),
        "checks": step.get("checks"),
        "fallback": step.get("fallback"),
        "model": step.get("model"),
        "requires": step.get("requires"),
        "depends_on": step.get("depends_on"),
    }


def _step_from(row: Row[Any]) -> Document:
    return _present(
        {
            "id": row.id,
            "method": row.method,
            "reason": row.reason,
            "rejected": row.rejected,
            "exactness": row.exactness,
            "checks": row.checks,
            "fallback": row.fallback,
            "model": row.model,
            "requires": row.requires,
            "depends_on": row.depends_on,
        }
    )


# --- command and plan -----------------------------------------------------------------------------


class CommandMapper:
    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.command, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.command,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "channel": document["channel"],
                "identity": document["identity"],
                "org_path": document["org_path"],
                "intent": document["intent"],
                "context": document.get("context"),
                "reply_to": document["reply_to"],
                "received_at": _at(document["received_at"]),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.command, tenant, s.command.c.received_at, s.command.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "channel": row.channel,
                "identity": row.identity,
                "org_path": row.org_path,
                "intent": row.intent,
                "context": row.context,
                "reply_to": row.reply_to,
                "received_at": _iso(row.received_at),
            }
        )


class IntakeEventMapper:
    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.intake_event, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.intake_event,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "channel": document["channel"],
                "event": document["event"],
                "sender_account": document["sender_account"],
                "sender_kind": document["sender_kind"],
                "intent": document["intent"],
                "context": document["context"],
                "reply_channel": document["reply_channel"],
                "reply_address": document["reply_address"],
                "reply_thread": document.get("reply_thread"),
                "occurred_at": _at(document["occurred_at"]),
                "received_at": _at(document["received_at"]),
                "status": document["status"],
                "command_id": document.get("command_id"),
                "completed_at": _at(document.get("completed_at")),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(
            connection, s.intake_event, tenant, s.intake_event.c.received_at, s.intake_event.c.id
        )
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "tenant": row.tenant,
                "channel": row.channel,
                "event": row.event,
                "sender_account": row.sender_account,
                "sender_kind": row.sender_kind,
                "intent": row.intent,
                "context": row.context,
                "reply_channel": row.reply_channel,
                "reply_address": row.reply_address,
                "reply_thread": row.reply_thread,
                "occurred_at": _iso(row.occurred_at),
                "received_at": _iso(row.received_at),
                "status": row.status,
                "command_id": row.command_id,
                "completed_at": _iso(row.completed_at),
            }
        )


class PlanMapper:
    """The plan's steps are a copy of the process version's and stay one JSON column."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.plan, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        commissioned = document.get("commissioned")
        await _upsert(
            connection,
            s.plan,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "command_id": document["command_id"],
                "goal": document["goal"],
                "autonomy_level": document["autonomy_level"],
                "due": _at(document.get("due")),
                "steps": document["steps"],
                "results_in": document["results_in"],
                "status": document["status"],
                "commissioned_by": None if commissioned is None else commissioned["by"],
                "commissioned_at": None if commissioned is None else _at(commissioned["at"]),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.plan, tenant, s.plan.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "command_id": row.command_id,
                "goal": row.goal,
                "autonomy_level": row.autonomy_level,
                "due": _iso(row.due),
                "steps": row.steps,
                "results_in": row.results_in,
                "status": row.status,
                "commissioned": None
                if row.commissioned_by is None
                else {"by": row.commissioned_by, "at": _iso(row.commissioned_at)},
            }
        )


# --- run ------------------------------------------------------------------------------------------


class RunMapper:
    """The run row; one `step_run` row per step; a `checkpoint` row and `artifact` rows under
    the step run that has them. The run's steps and work are the copy it executes and stay
    JSON columns."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.run, tenant, id)
        if row is None:
            return None
        return self._from(row, *await self._children(connection, tenant, id))

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        run_id = document["id"]
        await _upsert(
            connection,
            s.run,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": run_id,
                "plan_id": document["plan_id"],
                "process_version": document["process_version"],
                "identity": document["identity"],
                "autonomy_level": document["autonomy_level"],
                "budget": document["budget"],
                "margin": document.get("margin", 0.0),
                "steps": document["steps"],
                "work": document.get("work", {}),
                "inputs": document.get("inputs", {}),
                "rehearsal": document.get("rehearsal", False),
                "actions": document.get("actions", {}),
                "deadlines": document.get("deadlines") or None,
                "bindings": document.get("bindings") or None,
                "skills": document.get("skills") or None,
                "profile": document.get("profile"),
                "state": document["state"],
                "cause": document.get("cause"),
                "reason": document.get("reason"),
                "created_at": _at(document["created_at"]),
                "updated_at": _at(document["updated_at"]),
            },
        )
        await connection.execute(
            delete(s.step_run).where(s.step_run.c.tenant == tenant, s.step_run.c.run_id == run_id)
        )
        key = {"tenant": tenant, "run_id": run_id}
        step_runs = document.get("step_runs", [])
        await _insert_all(
            connection,
            s.step_run,
            [
                {
                    **key,
                    "step_id": sr["step_id"],
                    "position": sr["index"],
                    "method": sr["method"],
                    "state": sr["state"],
                    "attempt": sr.get("attempt", 1),
                    "retryable": sr.get("retryable"),
                    "adapter": sr.get("adapter"),
                    "assignment_id": sr.get("assignment_id"),
                    "assignment_open": sr.get("assignment_open", False),
                    "assignment_seq": sr.get("assignment_seq", 0),
                    "estimate": sr.get("estimate"),
                    "reservation": sr.get("reservation"),
                    "consumption": sr.get("consumption"),
                    "reason": sr.get("reason"),
                    "started_at": _at(sr.get("started_at")),
                    "finished_at": _at(sr.get("finished_at")),
                    "waiting_since": _at(sr.get("waiting_since")),
                    "waits": sr.get("waits", 0),
                    "confirmed_by": sr.get("confirmed_by"),
                    "block": sr.get("block"),
                    "anchoring": sr.get("anchoring"),
                }
                for sr in step_runs
            ],
        )
        await _insert_all(
            connection,
            s.checkpoint,
            [
                {
                    **key,
                    "step_id": sr["step_id"],
                    "ref": sr["checkpoint"]["ref"],
                    "taken_at": _at(sr["checkpoint"]["taken_at"]),
                    "artifact_ids": sr["checkpoint"].get("artifact_ids", []),
                    "result_digest": sr["checkpoint"].get("result_digest"),
                }
                for sr in step_runs
                if sr.get("checkpoint") is not None
            ],
        )
        await _insert_all(
            connection,
            s.artifact,
            [
                {
                    **key,
                    "step_id": sr["step_id"],
                    "id": artifact["id"],
                    "position": position,
                    "kind": artifact["kind"],
                    "digest": artifact["digest"],
                    "media_type": artifact.get("media_type"),
                    "size_bytes": artifact.get("size_bytes"),
                    "uri": artifact.get("uri"),
                    "title": artifact.get("title"),
                    "created_at": _at(artifact.get("created_at")),
                }
                for sr in step_runs
                for position, artifact in enumerate(sr.get("artifacts", []))
            ],
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.run, tenant, s.run.c.created_at, s.run.c.id)
        return await self._documents(connection, tenant, list(rows), every=True)

    async def newest(
        self, connection: AsyncConnection, tenant: Tenant, limit: int, after: Mark | None
    ) -> builtins.list[Document]:
        run = s.run.c
        statement = select(s.run).where(run.tenant == tenant)
        if after is not None:
            statement = statement.where(
                or_(
                    run.created_at < after.created_at,
                    and_(run.created_at == after.created_at, run.id > after.id),
                )
            )
        statement = statement.order_by(run.created_at.desc(), run.id).limit(limit)
        rows = list(await connection.execute(statement))
        return await self._documents(connection, tenant, rows)

    async def count(
        self, connection: AsyncConnection, tenant: Tenant, by: Sequence[str]
    ) -> dict[tuple[Any, ...], int]:
        columns = [self._column(field) for field in by]
        statement = (
            select(*columns, func.count()).where(s.run.c.tenant == tenant).group_by(*columns)
        )
        return {tuple(row[:-1]): row[-1] for row in await connection.execute(statement)}

    async def having(
        self, connection: AsyncConnection, tenant: Tenant, field: str, value: Any
    ) -> builtins.list[Document]:
        head, _, rest = field.partition(".")
        statement = select(s.run).where(s.run.c.tenant == tenant)
        if not rest:
            statement = statement.where(self._column(field) == value)
        elif head == "step_runs" and rest in _STEP_RUN_FIELDS:
            step_run = s.step_run.c
            statement = statement.where(
                exists().where(
                    step_run.tenant == s.run.c.tenant,
                    step_run.run_id == s.run.c.id,
                    step_run[_STEP_RUN_FIELDS[rest]] == value,
                )
            )
        else:
            raise NotQueryable("run", field)
        rows = list(await connection.execute(statement.order_by(s.run.c.created_at, s.run.c.id)))
        return await self._documents(connection, tenant, rows)

    @staticmethod
    def _column(field: str) -> Any:
        if field not in _RUN_FIELDS:
            raise NotQueryable("run", field)
        return s.run.c[field]

    async def _documents(
        self, connection: AsyncConnection, tenant: Tenant, rows: Rows, *, every: bool = False
    ) -> builtins.list[Document]:
        """The documents of the run rows given, in their order: their children read in one
        query per table and grouped in one pass. With `every`, the rows are all the tenant's,
        and the children are read without naming each run."""
        if not rows:
            return []
        ids = None if every else [row.id for row in rows]
        children = await self._children(connection, tenant, ids)
        # Assembling thousands of documents is work for the processor alone: done in a thread,
        # so that the event loop goes on serving, and renewing leases, meanwhile (#310).
        return await asyncio.to_thread(self._assembled, rows, children)

    def _assembled(self, rows: Rows, children: tuple[Rows, Rows, Rows]) -> builtins.list[Document]:
        grouped: dict[str, tuple[Rows, Rows, Rows]] = {row.id: ([], [], []) for row in rows}
        for position, of_kind in enumerate(children):
            for child in of_kind:
                found = grouped.get(child.run_id)
                if found is not None:
                    found[position].append(child)
        return [self._from(row, *grouped[row.id]) for row in rows]

    @staticmethod
    async def _children(
        connection: AsyncConnection, tenant: Tenant, run_ids: str | Sequence[str] | None
    ) -> tuple[Rows, Rows, Rows]:
        def scoped(table: Table) -> Any:
            statement = select(table).where(table.c.tenant == tenant)
            if run_ids is None:
                return statement
            if isinstance(run_ids, str):
                return statement.where(table.c.run_id == run_ids)
            return statement.where(table.c.run_id.in_(run_ids))

        step_runs = await connection.execute(scoped(s.step_run).order_by(s.step_run.c.position))
        checkpoints = await connection.execute(scoped(s.checkpoint))
        artifacts = await connection.execute(scoped(s.artifact).order_by(s.artifact.c.position))
        return list(step_runs), list(checkpoints), list(artifacts)

    @staticmethod
    def _from(
        row: Row[Any],
        step_runs: Sequence[Row[Any]],
        checkpoints: Sequence[Row[Any]],
        artifacts: Sequence[Row[Any]],
    ) -> Document:
        checkpoint_of = {c.step_id: c for c in checkpoints}
        artifacts_of: dict[str, Rows] = {}
        for artifact in artifacts:
            artifacts_of.setdefault(artifact.step_id, []).append(artifact)
        return _present(
            {
                "id": row.id,
                "plan_id": row.plan_id,
                "process_version": row.process_version,
                "tenant": row.tenant,
                "identity": row.identity,
                "autonomy_level": row.autonomy_level,
                "budget": row.budget,
                "margin": row.margin,
                "steps": row.steps,
                "work": row.work,
                "inputs": row.inputs,
                "rehearsal": row.rehearsal,
                "actions": row.actions,
                "deadlines": row.deadlines,
                "bindings": row.bindings,
                "skills": row.skills,
                "profile": row.profile,
                "state": row.state,
                "cause": row.cause,
                "reason": row.reason,
                "step_runs": [
                    _step_run_from(
                        sr, checkpoint_of.get(sr.step_id), artifacts_of.get(sr.step_id, [])
                    )
                    for sr in step_runs
                ],
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
        )


def _step_run_from(
    row: Row[Any], checkpoint: Row[Any] | None, artifacts: Sequence[Row[Any]]
) -> Document:
    return _present(
        {
            "step_id": row.step_id,
            "index": row.position,
            "method": row.method,
            "state": row.state,
            "attempt": row.attempt,
            "retryable": row.retryable,
            "adapter": row.adapter,
            "assignment_id": row.assignment_id,
            "assignment_open": row.assignment_open,
            "assignment_seq": row.assignment_seq,
            "estimate": row.estimate,
            "reservation": row.reservation,
            "consumption": row.consumption,
            "artifacts": [
                _present(
                    {
                        "id": a.id,
                        "kind": a.kind,
                        "digest": a.digest,
                        "media_type": a.media_type,
                        "size_bytes": a.size_bytes,
                        "uri": a.uri,
                        "title": a.title,
                        "created_at": _iso(a.created_at),
                    }
                )
                for a in artifacts
            ],
            "checkpoint": None
            if checkpoint is None
            else _present(
                {
                    "ref": checkpoint.ref,
                    "step_id": checkpoint.step_id,
                    "taken_at": _iso(checkpoint.taken_at),
                    "artifact_ids": checkpoint.artifact_ids,
                    "result_digest": checkpoint.result_digest,
                }
            ),
            "reason": row.reason,
            "started_at": _iso(row.started_at),
            "finished_at": _iso(row.finished_at),
            "waiting_since": _iso(row.waiting_since),
            "waits": row.waits,
            "confirmed_by": row.confirmed_by,
            "block": row.block,
            "anchoring": row.anchoring,
        }
    )


_RUN_FIELDS = frozenset(
    {"plan_id", "process_version", "identity", "autonomy_level", "rehearsal", "state", "cause"}
)
"""The fields of a run's document a query may name: the run row's own columns of one value."""

_STEP_RUN_FIELDS = {
    "step_id": "step_id",
    "index": "position",
    "method": "method",
    "state": "state",
    "adapter": "adapter",
}
"""The fields of a step run a query may name, by document key, with the column each is in."""


# --- catalog --------------------------------------------------------------------------------------


def _passed_at(conformance: Any) -> datetime | None:
    """When a conformance run passed, or None for one that did not or none."""
    if not isinstance(conformance, dict) or conformance.get("outcome") != "passed":
        return None
    return _at(conformance.get("tested_at"))


class AdapterMaturityMapper:
    """One row per adapter identifier; the conformance run and the removal result stay
    documents. `conformance_passed_at` is written from the conformance run, for a reader of the
    table, and never read back: the document is the record."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.adapter_maturity, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.adapter_maturity,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "family": document["family"],
                "conformance_passed_at": _passed_at(document.get("conformance")),
                "conformance": document.get("conformance"),
                "removal": document.get("removal"),
                "updated_at": _at(document["updated_at"]),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.adapter_maturity, tenant, s.adapter_maturity.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "tenant": row.tenant,
                "family": row.family,
                "conformance": row.conformance,
                "removal": row.removal,
                "updated_at": _iso(row.updated_at),
            }
        )


# --- trigger state --------------------------------------------------------------------------------


class TriggerStateMapper:
    """One row per schedule trigger of a process: when the scheduler first saw it, the last
    slot it fired for, and the runs that firing started (ADR-0035)."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.trigger_state, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.trigger_state,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "process_id": document["process_id"],
                "schedule": document["schedule"],
                "armed_at": _at(document["armed_at"]),
                "fired_slot": _at(document.get("fired_slot")),
                "fired_at": _at(document.get("fired_at")),
                "runs": list(document.get("runs", [])),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.trigger_state, tenant, s.trigger_state.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "process_id": row.process_id,
                "schedule": row.schedule,
                "armed_at": _iso(row.armed_at),
                "fired_slot": _iso(row.fired_slot),
                "fired_at": _iso(row.fired_at),
                "runs": row.runs,
            }
        )


# --- identity -------------------------------------------------------------------------------------


class IdentityMapper:
    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.identity_table, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.identity_table,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "org_path": list(document["org_path"]),
                "roles": list(document.get("roles", [])),
                "key_digest": document.get("key_digest"),
                "agent_key_digest": document.get("agent_key_digest"),
                "created_at": _at(document["created_at"]),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.identity_table, tenant, s.identity_table.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "tenant": row.tenant,
                "id": row.id,
                "org_path": row.org_path,
                "roles": row.roles or None,
                "key_digest": row.key_digest,
                "agent_key_digest": row.agent_key_digest,
                "created_at": _iso(row.created_at),
            }
        )


class ChannelLinkMapper:
    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.channel_link, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.channel_link,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "channel": document["channel"],
                "account": document["account"],
                "identity": document["identity"],
                "origin": document["origin"],
                "linked_at": _at(document["linked_at"]),
                "revoked_at": _at(document.get("revoked_at")),
                "revoked_by": document.get("revoked_by"),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.channel_link, tenant, s.channel_link.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "tenant": row.tenant,
                "id": row.id,
                "channel": row.channel,
                "account": row.account,
                "identity": row.identity,
                "origin": row.origin,
                "linked_at": _iso(row.linked_at),
                "revoked_at": _iso(row.revoked_at),
                "revoked_by": row.revoked_by,
            }
        )


class LinkCodeMapper:
    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.link_code, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.link_code,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "identity": document["identity"],
                "channel": document["channel"],
                "created_at": _at(document["created_at"]),
                "expires_at": _at(document["expires_at"]),
                "used_at": _at(document.get("used_at")),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.link_code, tenant, s.link_code.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "tenant": row.tenant,
                "id": row.id,
                "identity": row.identity,
                "channel": row.channel,
                "created_at": _iso(row.created_at),
                "expires_at": _iso(row.expires_at),
                "used_at": _iso(row.used_at),
            }
        )


class BrowserSessionMapper:
    """A sign-in of the web app, kept by the digest of its token (ADR-0119)."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.browser_session, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.browser_session,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "identity": document["identity"],
                "key_digest": document["key_digest"],
                "created_at": _at(document["created_at"]),
                "expires_at": _at(document["expires_at"]),
                "ended_at": _at(document.get("ended_at")),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.browser_session, tenant, s.browser_session.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "tenant": row.tenant,
                "id": row.id,
                "identity": row.identity,
                "key_digest": row.key_digest,
                "created_at": _iso(row.created_at),
                "expires_at": _iso(row.expires_at),
                "ended_at": _iso(row.ended_at),
            }
        )


class RoleRightsMapper:
    """The rights one role of a tenant holds, keyed by the role (ADR-0131 §3)."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.role_rights, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.role_rights,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "rights": list(document.get("rights", [])),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.role_rights, tenant, s.role_rights.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return {"tenant": row.tenant, "id": row.id, "rights": list(row.rights)}


# --- anchors and decisions ------------------------------------------------------------------------


class AnchorConfigurationMapper:
    """One row per tenant; the anchors and the risk classes stay documents."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.anchor_configuration, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.anchor_configuration,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "anchors": document["anchors"],
                "risk_classes": document.get("risk_classes", {}),
                "configured_at": _at(document.get("configured_at")),
                "configured_by": document.get("configured_by"),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.anchor_configuration, tenant, s.anchor_configuration.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "tenant": row.tenant,
                "anchors": row.anchors,
                "risk_classes": row.risk_classes,
                "configured_at": _iso(row.configured_at),
                "configured_by": row.configured_by,
            }
        )


class DecisionRequestMapper:
    """One row per request: the request in its contract's shape as a document, and beside it
    the columns the decider's list is read by."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.decision_request, tenant, id)
        return None if row is None else self._from(row)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        request = document["request"]
        await _upsert(
            connection,
            s.decision_request,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "decider": document["decider"],
                "anchor": document.get("anchor"),
                "status": request["status"],
                "run_id": request["raised_by"]["run"],
                "raised_at": _at(document["raised_at"]),
                "request": request,
                "answered_by": document.get("answered_by"),
                "answered_at": _at(document.get("answered_at")),
                "reflection": document.get("reflection"),
                "decided_by": document.get("decided_by"),
                "decided_at": _at(document.get("decided_at")),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.decision_request, tenant, s.decision_request.c.id)
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: Row[Any]) -> Document:
        return _present(
            {
                "id": row.id,
                "tenant": row.tenant,
                "decider": row.decider,
                "anchor": row.anchor,
                "raised_at": _iso(row.raised_at),
                "request": row.request,
                "answered_by": row.answered_by,
                "answered_at": _iso(row.answered_at),
                "reflection": row.reflection,
                "decided_by": row.decided_by,
                "decided_at": _iso(row.decided_at),
            }
        )


class RegisterEntryMapper:
    """One row per entry of the decision register, linked to its run, step and request."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.register_entry, tenant, id)
        return None if row is None else dict(row.entry)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.register_entry,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "request_id": document["request_id"],
                "run_id": document["run_id"],
                "step_id": document["step_id"],
                "entry": document,
                "decided_at": _at(document["decided_at"]),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.register_entry, tenant, s.register_entry.c.decided_at)
        return [dict(row.entry) for row in rows]


# --- the owner-facing channel ------------------------------------------------------------------


class OwnerChannelMapper:
    """One row per tenant; the configuration stays a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.owner_channel, tenant, id)
        return None if row is None else dict(row.channel)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.owner_channel,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "channel": document,
                "configured_at": _at(document["configured_at"]),
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.owner_channel, tenant, s.owner_channel.c.id)
        return [dict(row.channel) for row in rows]


class ReportMapper:
    """One row per report to the owner: the report as a document, and beside it the columns a
    list of what is open is read by."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.report, tenant, id)
        return None if row is None else dict(row.report)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.report,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "kind": document["kind"],
                "state": document.get("state", "open"),
                "due": date.fromisoformat(document["due"]),
                "raised_at": _at(document["raised_at"]),
                "report": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.report, tenant, s.report.c.raised_at, s.report.c.id)
        return [dict(row.report) for row in rows]


class ProposalMapper:
    """One row per proposal (ADR-0091 §1): the proposal as a document, and beside it the columns a
    list of a process's proposals is read by. A proposal is never a process version."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.proposal, tenant, id)
        return None if row is None else dict(row.proposal)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.proposal,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "process_id": document["process_id"],
                "state": document.get("state", "proposed"),
                "created_at": _at(document["created_at"]),
                "proposal": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.proposal, tenant, s.proposal.c.created_at, s.proposal.c.id)
        return [dict(row.proposal) for row in rows]


class EvaluationMapper:
    """One row per evaluation of a process on its cases (ADR-0134 §3): the evaluation as a
    document, and beside it the columns a list of a process's evaluations is read by."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.evaluation, tenant, id)
        return None if row is None else dict(row.evaluation)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.evaluation,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "process_id": document["process_id"],
                "state": document.get("state", "running"),
                "started_at": _at(document["started_at"]),
                "evaluation": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(
            connection, s.evaluation, tenant, s.evaluation.c.started_at, s.evaluation.c.id
        )
        return [dict(row.evaluation) for row in rows]


class CorrectedCaseMapper:
    """One row per case proposed from a correction (ADR-0134 §7), as a document. A row is never
    deleted: its state moves on."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.corrected_case, tenant, id)
        return None if row is None else dict(row.corrected_case)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.corrected_case,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "process_id": document["process_id"],
                "state": document.get("state", "proposed"),
                "proposed_at": _at(document["proposed_at"]),
                "corrected_case": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(
            connection,
            s.corrected_case,
            tenant,
            s.corrected_case.c.proposed_at,
            s.corrected_case.c.id,
        )
        return [dict(row.corrected_case) for row in rows]


class PendingActMapper:
    """One row per commissioning or rollback asked for in the owner's conversation and read
    back, as a document (ADR-0091 §6). A row is never deleted: its state moves on."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.pending_act, tenant, id)
        return None if row is None else dict(row.act)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.pending_act,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "state": document.get("state", "awaiting"),
                "asked_at": _at(document["asked_at"]),
                "act": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.pending_act, tenant, s.pending_act.c.asked_at)
        return [dict(row.act) for row in rows]


class IncidentMapper:
    """One row per incident (ADR-0107): the incident as a document, and beside it the columns a
    list of the open ones is read by. A row is never deleted: its state moves on."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.incident, tenant, id)
        return None if row is None else dict(row.incident)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.incident,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "kind": document["kind"],
                "process_id": document["process_id"],
                "state": document.get("state", "open"),
                "raised_at": _at(document["raised_at"]),
                "incident": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.incident, tenant, s.incident.c.raised_at, s.incident.c.id)
        return [dict(row.incident) for row in rows]


class WatchConfigurationMapper:
    """One row per tenant that configured its watch; the configuration stays a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.watch_configuration, tenant, id)
        return None if row is None else dict(row.configuration)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.watch_configuration,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "configured_at": _at(document["configured_at"]),
                "configuration": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.watch_configuration, tenant, s.watch_configuration.c.id)
        return [dict(row.configuration) for row in rows]


class StagePlanMapper:
    """One row per tenant that declared its stages; the plan stays a document (ADR-0137)."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.stage_plan, tenant, id)
        return None if row is None else dict(row.plan)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.stage_plan,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "configured_at": _at(document["configured_at"]),
                "plan": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.stage_plan, tenant, s.stage_plan.c.id)
        return [dict(row.plan) for row in rows]


class DeadlineMapper:
    """One row per deadline (ADR-0133): the deadline as a document, and beside it the columns the
    scheduler reads the open ones by. A row is never deleted: its state moves on."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.deadline, tenant, id)
        return None if row is None else dict(row.deadline)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.deadline,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "run_id": document["run_id"],
                "state": document.get("state", "open"),
                "due_at": _at(document["due_at"]),
                "deadline": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.deadline, tenant, s.deadline.c.due_at, s.deadline.c.id)
        return [dict(row.deadline) for row in rows]


class AdapterStopMapper:
    """One row per stop of an adapter (ADR-0138): the stop as a document, and beside it the
    columns the held ones are read by. A row is never deleted: its state moves on."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.adapter_stop, tenant, id)
        return None if row is None else dict(row.stop)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.adapter_stop,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "adapter": document["adapter"],
                "state": document.get("state", "holding"),
                "requested_at": _at(document["requested_at"]),
                "stop": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(
            connection, s.adapter_stop, tenant, s.adapter_stop.c.requested_at, s.adapter_stop.c.id
        )
        return [dict(row.stop) for row in rows]


class WorkingTimeMapper:
    """One row per tenant that set its working time; the working time stays a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.working_time, tenant, id)
        return None if row is None else dict(row.working_time)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.working_time,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "configured_at": _at(document["configured_at"]),
                "working_time": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.working_time, tenant, s.working_time.c.id)
        return [dict(row.working_time) for row in rows]


class CorridorMapper:
    """One row per version of a corridor (ADR-0109 §3). A version is inserted once and never
    changed: the application role may not update a row, and a second insert under the same
    identifier fails."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.corridor, tenant, id)
        return None if row is None else dict(row.corridor)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await connection.execute(
            insert(s.corridor).values(
                tenant=tenant,
                id=document["id"],
                signal=document["signal"],
                version=document["version"],
                changed_at=_at(document["changed_at"]),
                corridor=document,
            )
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.corridor, tenant, s.corridor.c.signal, s.corridor.c.version)
        return [dict(row.corridor) for row in rows]


class CorrectionLimitsMapper:
    """One row per tenant that set its correction limits; the limits stay a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.correction_limits, tenant, id)
        return None if row is None else dict(row.limits)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.correction_limits,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "configured_at": _at(document["configured_at"]),
                "limits": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.correction_limits, tenant, s.correction_limits.c.id)
        return [dict(row.limits) for row in rows]


class ResidencyRuleMapper:
    """One row per tenant that set its residency rule; the rule stays a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.residency_rule, tenant, id)
        return None if row is None else dict(row.rule)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.residency_rule,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "configured_at": _at(document["configured_at"]),
                "rule": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.residency_rule, tenant, s.residency_rule.c.id)
        return [dict(row.rule) for row in rows]


class SourceDeclarationMapper:
    """One row per tenant that declared its sources; the declaration stays a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.source_declaration, tenant, id)
        return None if row is None else dict(row.declaration)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.source_declaration,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "configured_at": _at(document["configured_at"]),
                "declaration": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.source_declaration, tenant, s.source_declaration.c.id)
        return [dict(row.declaration) for row in rows]


class MessageRulesMapper:
    """One row per tenant that configured its message rules; the rules stay a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.message_rules, tenant, id)
        return None if row is None else dict(row.rules)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.message_rules,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "configured_at": _at(document["configured_at"]),
                "rules": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.message_rules, tenant, s.message_rules.c.id)
        return [dict(row.rules) for row in rows]


class CaseAnswerMapper:
    """One row per case of a process a person answered in; the answer stays a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.case_answer, tenant, id)
        return None if row is None else dict(row.answer)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.case_answer,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "process": document["process"],
                "answered_at": _at(document["answered_at"]),
                "answer": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.case_answer, tenant, s.case_answer.c.id)
        return [dict(row.answer) for row in rows]


class SkillVersionMapper:
    """One row per skill version (ADR-0162 §1), as a document, with the columns it is listed by.
    A row is never deleted: its stage moves on."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.skill_version, tenant, id)
        return None if row is None else dict(row.skill)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.skill_version,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "name": document["name"],
                "stage": document.get("stage", "draft"),
                "registered_at": _at(document["registered_at"]),
                "skill": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.skill_version, tenant, s.skill_version.c.id)
        return [dict(row.skill) for row in rows]


class SkillOwnershipMapper:
    """Whose own use a skill version was drawn from: one row, its owner a column of its own."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.skill_ownership, tenant, id)
        return None if row is None else {"id": row.id, "tenant": row.tenant, "owner": row.owner}

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.skill_ownership,
            ("tenant", "id"),
            {"tenant": tenant, "id": document["id"], "owner": document["owner"]},
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.skill_ownership, tenant, s.skill_ownership.c.id)
        return [{"id": row.id, "tenant": row.tenant, "owner": row.owner} for row in rows]


class SkillPolicyMapper:
    """A tenant's skill policy, one row, as a document (ADR-0162 §4)."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.skill_policy, tenant, id)
        return None if row is None else dict(row.policy)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.skill_policy,
            ("tenant", "id"),
            {"tenant": tenant, "id": document.get("id", "skills"), "policy": document},
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(connection, s.skill_policy, tenant, s.skill_policy.c.id)
        return [dict(row.policy) for row in rows]


class AgentCoreMapper:
    """One row per version of a shared agent's core (ADR-0163 §1), as a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.agent_core, tenant, id)
        return None if row is None else dict(row.core)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.agent_core,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "agent": document["agent"],
                "state": document.get("state", "held"),
                "proposed_at": _at(document["proposed_at"]),
                "core": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(
            connection, s.agent_core, tenant, s.agent_core.c.proposed_at, s.agent_core.c.id
        )
        return [dict(row.core) for row in rows]


class RoleProfileMapper:
    """One row per version of a role's profile of a shared agent (ADR-0163 §2), as a document."""

    async def get(self, connection: AsyncConnection, tenant: Tenant, id: str) -> Document | None:
        row = await _one(connection, s.role_profile, tenant, id)
        return None if row is None else dict(row.profile)

    async def put(self, connection: AsyncConnection, tenant: Tenant, document: Document) -> None:
        await _upsert(
            connection,
            s.role_profile,
            ("tenant", "id"),
            {
                "tenant": tenant,
                "id": document["id"],
                "agent": document["agent"],
                "role": document["role"],
                "set_at": _at(document["set_at"]),
                "profile": document,
            },
        )

    async def list(self, connection: AsyncConnection, tenant: Tenant) -> list[Document]:
        rows = await _all(
            connection, s.role_profile, tenant, s.role_profile.c.set_at, s.role_profile.c.id
        )
        return [dict(row.profile) for row in rows]


# Keyed by the aggregate's class name in snake case: `Run` → "run", `ProcessVersion` →
# "process_version". The persistence looks a mapper up by the class the composition root binds.
MAPPERS: dict[str, Mapper] = {
    "process": ProcessMapper(),
    "process_version": ProcessVersionMapper(),
    "command": CommandMapper(),
    "intake_event": IntakeEventMapper(),
    "plan": PlanMapper(),
    "run": RunMapper(),
    "adapter_maturity": AdapterMaturityMapper(),
    "trigger_state": TriggerStateMapper(),
    "identity": IdentityMapper(),
    "channel_link": ChannelLinkMapper(),
    "link_code": LinkCodeMapper(),
    "browser_session": BrowserSessionMapper(),
    "role_rights": RoleRightsMapper(),
    "anchor_configuration": AnchorConfigurationMapper(),
    "request": DecisionRequestMapper(),
    "register_entry": RegisterEntryMapper(),
    "owner_channel": OwnerChannelMapper(),
    "report": ReportMapper(),
    "proposal": ProposalMapper(),
    "pending_act": PendingActMapper(),
    "evaluation": EvaluationMapper(),
    "corrected_case": CorrectedCaseMapper(),
    "incident": IncidentMapper(),
    "watch_configuration": WatchConfigurationMapper(),
    "corridor": CorridorMapper(),
    "stage_plan": StagePlanMapper(),
    "deadline": DeadlineMapper(),
    "adapter_stop": AdapterStopMapper(),
    "working_time": WorkingTimeMapper(),
    "correction_limits": CorrectionLimitsMapper(),
    "residency_rule": ResidencyRuleMapper(),
    "source_declaration": SourceDeclarationMapper(),
    "message_rules": MessageRulesMapper(),
    "case_answer": CaseAnswerMapper(),
    "skill_version": SkillVersionMapper(),
    "skill_ownership": SkillOwnershipMapper(),
    "skill_policy": SkillPolicyMapper(),
    "agent_core": AgentCoreMapper(),
    "role_profile": RoleProfileMapper(),
}
