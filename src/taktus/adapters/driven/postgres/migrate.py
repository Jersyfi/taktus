"""Running the migrations from code, and asking whether a database's schema suits this build.

`make migrate` runs the same migrations through the `alembic` command line; this module is for
the tests, which bring a container to the current schema, and for the composition root, which
refuses to start against a schema this build cannot run against — a run against a half-migrated
schema would fail in the middle, and that is a reason known at the start.

Readiness accepts a range (ADR-0093 §2, #330). Two declarations meet:

- **The build declares the oldest schema it runs against**, `OLDEST_SCHEMA`; None means its own
  head. A database at a revision of this build's history between the two is ready; an older
  one needs `make migrate`.
- **The schema declares the oldest build that runs against it**: the database function
  `taktus_oldest_code()`, created by migration 0083, returns the head revision of the oldest
  build the schema still serves. A migration that only expands leaves it; a migration that
  contracts — drops, renames or narrows what an older build reads — moves it to its own
  revision (`tests/adapters/persistence/test_migrations_expand.py` holds every migration to
  that).

A database at a revision this build does not know is newer than the build. It is ready when the
schema names an oldest build that this build is, or descends from: the previous release keeps
serving while the next one's migration has run, and after a person rolled back to it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from taktus.adapters.driven.postgres.url import for_sqlalchemy

MIGRATIONS = Path(__file__).resolve().parents[5] / "migrations"

OLDEST_SCHEMA: str | None = None
"""The oldest schema revision this build runs against; None: its head. A release whose code
still runs against the schema before its last migrations may name that revision here."""

OLDEST_CODE = "taktus_oldest_code"
"""The database function that names the oldest build the schema serves (migration 0083)."""


def configuration(url: str) -> Config:
    ini = MIGRATIONS / "alembic.ini"
    if not ini.is_file():
        raise FileNotFoundError(
            f"the migrations are not at {MIGRATIONS}; run from a checkout of the repository"
        )
    config = Config(str(ini))
    config.attributes["url"] = url
    return config


def history() -> ScriptDirectory:
    """This build's migrations."""
    return ScriptDirectory.from_config(configuration("postgresql://unused"))


def head_revision() -> str | None:
    return history().get_current_head()


def lineage(revision: str, script: ScriptDirectory | None = None) -> list[str]:
    """`revision` and every revision before it in this build's history, newest first."""
    script = script or history()
    found: list[str] = []
    current: str | None = revision
    while current is not None:
        found.append(current)
        script_of = script.get_revision(current)
        down = None if script_of is None else script_of.down_revision
        if down is not None and not isinstance(down, str):  # one line: the history never merges
            raise ValueError(f"revision {current} merges {down}; the history has one line")
        current = down
    return found


async def upgrade(url: str) -> bool:
    """Bring the database to the current schema. Alembic is synchronous; it runs in a thread.
    False when the database is newer than this build: there is nothing to migrate, and whether
    this build may serve it is `check_schema`'s question."""

    def migrate() -> bool:
        engine = create_engine(for_sqlalchemy(url))
        try:
            with engine.connect() as connection:
                heads = MigrationContext.configure(connection).get_current_heads()
        finally:
            engine.dispose()
        head = head_revision()
        if heads and head is not None and heads[0] not in lineage(head):
            return False
        command.upgrade(configuration(url), "head")
        return True

    return await asyncio.to_thread(migrate)


async def current_revision(engine: AsyncEngine) -> str | None:
    def read(connection: Connection) -> str | None:
        heads = MigrationContext.configure(connection).get_current_heads()
        return heads[0] if heads else None

    async with engine.connect() as connection:
        return await connection.run_sync(read)


async def oldest_code(engine: AsyncEngine) -> str | None:
    """The oldest build the schema says it serves; None when the schema says nothing."""

    def read(connection: Connection) -> str | None:
        declared = connection.exec_driver_sql(
            f"SELECT to_regprocedure('{OLDEST_CODE}()') IS NOT NULL"
        ).scalar()
        if not declared:
            return None
        value = connection.exec_driver_sql(f"SELECT {OLDEST_CODE}()").scalar()
        return None if value is None else str(value)

    async with engine.connect() as connection:
        return await connection.run_sync(read)


class SchemaOutOfDate(Exception):
    """The schema is not one this build runs against; the message says why and what to do."""

    def __init__(self, current: str | None, head: str | None, message: str | None = None) -> None:
        self.current = current
        self.head = head
        super().__init__(
            message
            or f"the database is at schema revision {current or 'none'}, this version needs "
            f"{head}: run `make migrate`"
        )


async def check_schema(engine: AsyncEngine, *, oldest_schema: str | None = None) -> None:
    """Pass when this build runs against the database's schema; otherwise `SchemaOutOfDate`
    with the reason. `oldest_schema` stands in for `OLDEST_SCHEMA`, for a test."""
    script = history()
    head = script.get_current_head()
    current = await current_revision(engine)
    if current is None or head is None:
        raise SchemaOutOfDate(current, head)
    ours = lineage(head, script)
    oldest = oldest_schema or OLDEST_SCHEMA or head
    if current in ours:
        if ours.index(current) <= ours.index(oldest):
            return
        raise SchemaOutOfDate(current, head)
    # Not in this build's history, which is one line: a newer build migrated the database.
    served_from = await oldest_code(engine)
    if served_from is not None and served_from in ours:
        return
    said = (
        "its schema names no oldest version it serves"
        if served_from is None
        else f"it serves versions from schema revision {served_from} on"
    )
    raise SchemaOutOfDate(
        current,
        head,
        f"the database is at schema revision {current}, newer than this version's {head}, and "
        f"{said}: run a newer version of Taktus, or roll back by the runbook "
        "(deploy/k8s/README.md, section 12)",
    )
