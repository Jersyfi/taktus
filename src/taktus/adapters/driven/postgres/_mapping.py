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

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import Table, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection

from taktus.adapters.driven.postgres import _schema as s
from taktus.ports.persistence import Tenant

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
                "autonomy_level": document["autonomy_level"],
                "triggers": document.get("triggers", []),
                "slo": document.get("slo"),
                "work": document.get("work", {}),
                "limits": document.get("limits"),
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
                "autonomy_level": row.autonomy_level,
                "steps": [_step_from(step) for step in steps],
                "triggers": row.triggers,
                "slo": row.slo,
                "work": row.work,
                "limits": row.limits,
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
                "autonomy_level": document["autonomy_level"],
                "budget": document["budget"],
                "steps": document["steps"],
                "work": document.get("work", {}),
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
                    "adapter": sr.get("adapter"),
                    "assignment_id": sr.get("assignment_id"),
                    "estimate": sr.get("estimate"),
                    "consumption": sr.get("consumption"),
                    "reason": sr.get("reason"),
                    "started_at": _at(sr.get("started_at")),
                    "finished_at": _at(sr.get("finished_at")),
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
        step_runs, checkpoints, artifacts = await self._children(connection, tenant, None)
        return [
            self._from(
                row,
                [sr for sr in step_runs if sr.run_id == row.id],
                [c for c in checkpoints if c.run_id == row.id],
                [a for a in artifacts if a.run_id == row.id],
            )
            for row in rows
        ]

    @staticmethod
    async def _children(
        connection: AsyncConnection, tenant: Tenant, run_id: str | None
    ) -> tuple[Rows, Rows, Rows]:
        def scoped(table: Table) -> Any:
            statement = select(table).where(table.c.tenant == tenant)
            return statement if run_id is None else statement.where(table.c.run_id == run_id)

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
                "autonomy_level": row.autonomy_level,
                "budget": row.budget,
                "steps": row.steps,
                "work": row.work,
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
            "adapter": row.adapter,
            "assignment_id": row.assignment_id,
            "estimate": row.estimate,
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
        }
    )


# Keyed by the aggregate's class name in snake case: `Run` → "run", `ProcessVersion` →
# "process_version". The persistence looks a mapper up by the class the composition root binds.
MAPPERS: dict[str, Mapper] = {
    "process": ProcessMapper(),
    "process_version": ProcessVersionMapper(),
    "command": CommandMapper(),
    "plan": PlanMapper(),
    "run": RunMapper(),
}
