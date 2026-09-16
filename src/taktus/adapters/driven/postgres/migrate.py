"""Running the migrations from code, and asking a database which revision it is at.

`make migrate` runs the same migrations through the `alembic` command line; this module is for
the tests, which bring a container to the current schema, and for the composition root, which
refuses to start against a database that is not at the current revision — a run against a
half-migrated schema would fail in the middle, and that is a reason known at the start.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS = Path(__file__).resolve().parents[5] / "migrations"


def configuration(url: str) -> Config:
    ini = MIGRATIONS / "alembic.ini"
    if not ini.is_file():
        raise FileNotFoundError(
            f"the migrations are not at {MIGRATIONS}; run from a checkout of the repository"
        )
    config = Config(str(ini))
    config.attributes["url"] = url
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(configuration("postgresql://unused")).get_current_head()


async def upgrade(url: str) -> None:
    """Bring the database to the current schema. Alembic is synchronous; it runs in a thread."""
    await asyncio.to_thread(command.upgrade, configuration(url), "head")


async def current_revision(engine: AsyncEngine) -> str | None:
    def read(connection: Connection) -> str | None:
        heads = MigrationContext.configure(connection).get_current_heads()
        return heads[0] if heads else None

    async with engine.connect() as connection:
        return await connection.run_sync(read)


class SchemaOutOfDate(Exception):
    def __init__(self, current: str | None, head: str | None) -> None:
        super().__init__(
            f"the database is at schema revision {current or 'none'}, this version needs "
            f"{head}: run `make migrate`"
        )


async def check_schema(engine: AsyncEngine) -> None:
    current = await current_revision(engine)
    head = head_revision()
    if current != head:
        raise SchemaOutOfDate(current, head)
