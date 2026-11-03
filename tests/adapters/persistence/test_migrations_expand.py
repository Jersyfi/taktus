"""Every migration keeps the previous build working, and readiness accepts a range (ADR-0093).

Two halves of one promise (#330):

- **The rule of §1, migration by migration.** From the migration that introduced the schema's
  own declaration (0083) on, each migration is applied alone to a database at the revision
  before it, and the schema before and after are compared. A migration may add tables,
  columns, constraints on new columns, indexes and functions. Dropping a table or a column,
  changing a column's type, making a column NOT NULL, or adding or changing a constraint on a
  column that existed before narrows what the previous build relies on: such a migration
  must move `taktus_oldest_code()` to its own revision, so that an older build stops calling
  the schema its own.
- **The range of §2.** A build is ready against its head; against an older revision of its
  history it asks for `make migrate`; against a revision it does not know it is ready only
  while the schema names an oldest build this one is or descends from. A build that migrates
  on start leaves a newer schema as it is.

Each test takes a database of its own: it moves `alembic_version` and the declaration, which
every other test of the session relies on.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from alembic import command
from sqlalchemy.engine import make_url

from taktus.adapters.driven.postgres import PostgresPersistence
from taktus.adapters.driven.postgres.migrate import (
    OLDEST_CODE,
    SchemaOutOfDate,
    check_schema,
    configuration,
    head_revision,
    history,
    lineage,
    oldest_code,
    upgrade,
)

FIRST_DECLARING = "0083"
"""The first migration held to the rule by this test: the one that made the schema say which
build it serves. The migrations before it were reviewed by hand (ADR-0093, Consequences)."""


@contextmanager
def administration(server: str) -> Iterator[psycopg.Connection[Any]]:
    plain = make_url(server).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as connection:
        yield connection


@pytest.fixture
def blank(postgres_server: str) -> Iterator[str]:
    """An empty database of this test's own, dropped when it ends."""
    name = f"migrations_{os.urandom(5).hex()}"
    with administration(postgres_server) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    try:
        yield make_url(postgres_server).set(database=name).render_as_string(hide_password=False)
    finally:
        with administration(postgres_server) as connection:
            connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.fixture
async def migrated(blank: str) -> AsyncIterator[tuple[str, PostgresPersistence]]:
    command.upgrade(configuration(blank), "head")
    persistence = PostgresPersistence(blank, pool_size=1)
    try:
        yield blank, persistence
    finally:
        await persistence.close()


def run(url: str, statement: str) -> list[tuple[Any, ...]]:
    with administration(url) as connection:
        cursor = connection.execute(statement)  # type: ignore[arg-type]  # constants of this file
        return cursor.fetchall() if cursor.description else []


def schema(url: str) -> dict[str, Any]:
    """The shape a previous build relies on: columns with type and nullability, constraints
    with their columns and definition."""
    columns = {
        (table, column): (data_type, udt, length, nullable)
        for table, column, data_type, udt, length, nullable in run(
            url,
            "SELECT table_name, column_name, data_type, udt_name, character_maximum_length, "
            "is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name <> 'alembic_version'",
        )
    }
    constraints = {
        (table, name): (kind, tuple(sorted(keys or ())), definition)
        for table, name, kind, keys, definition in run(
            url,
            "SELECT c.conrelid::regclass::text, c.conname, c.contype::text, "
            "ARRAY(SELECT a.attname::text FROM pg_attribute a WHERE a.attrelid = c.conrelid "
            "AND a.attnum = ANY(c.conkey)), pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c WHERE c.connamespace = 'public'::regnamespace "
            "AND c.conrelid <> 0",
        )
    }
    return {"columns": columns, "constraints": constraints}


def narrowings(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What the step from `before` to `after` takes from a build that knew `before`."""
    found: list[str] = []
    tables_before = {table for table, _ in before["columns"]}
    for (table, column), shape in before["columns"].items():
        now = after["columns"].get((table, column))
        if now is None:
            found.append(f"{table}.{column} is dropped or renamed")
        elif now[:3] != shape[:3]:
            found.append(f"{table}.{column} changes its type from {shape[:3]} to {now[:3]}")
        elif shape[3] == "YES" and now[3] == "NO":
            found.append(f"{table}.{column} becomes NOT NULL")
    for (table, name), (_, keys, definition) in after["constraints"].items():
        old = before["constraints"].get((table, name))
        if old is not None and old[2] != definition:
            found.append(f"constraint {name} on {table} changes to {definition}")
        elif old is None and table in tables_before:
            existing = [k for k in keys if (table, k) in before["columns"]]
            if existing:
                found.append(f"constraint {name} on {table} binds existing {existing}")
    return found


def test_every_migration_from_the_declaration_on_expands_or_moves_the_oldest_build(
    blank: str,
) -> None:
    head = head_revision()
    assert head is not None
    ours = list(reversed(lineage(head)))
    held = ours[ours.index(FIRST_DECLARING) :]
    previous = history().get_revision(FIRST_DECLARING).down_revision
    assert isinstance(previous, str)
    command.upgrade(configuration(blank), previous)
    before = schema(blank)
    for revision in held:
        command.upgrade(configuration(blank), revision)
        after = schema(blank)
        taken = narrowings(before, after)
        [(declared,)] = run(blank, f"SELECT {OLDEST_CODE}()")
        if taken:
            assert declared == revision, (
                f"migration {revision} narrows what the build before it relies on — "
                f"{'; '.join(taken)} — and must name itself as the oldest build it serves, "
                f"and say so in its docstring (ADR-0093 §1)"
            )
        before = after


def test_the_rule_sees_a_drop_a_narrowed_column_and_a_constraint_on_an_old_column() -> None:
    """The comparison itself, on shapes written here: a gate that cannot see is no gate."""
    before = {
        "columns": {
            ("run", "id"): ("text", "text", None, "NO"),
            ("run", "note"): (
                "text",
                "text",
                None,
                "YES",
            ),
        },
        "constraints": {},
    }
    dropped = {"columns": {("run", "id"): ("text", "text", None, "NO")}, "constraints": {}}
    assert narrowings(before, dropped) == ["run.note is dropped or renamed"]
    tightened = {
        "columns": {**before["columns"], ("run", "note"): ("text", "text", None, "NO")},
        "constraints": {},
    }
    assert narrowings(before, tightened) == ["run.note becomes NOT NULL"]
    checked = {
        "columns": {**before["columns"], ("run", "added"): ("text", "text", None, "YES")},
        "constraints": {
            ("run", "note_short"): ("c", ("note",), "CHECK (length(note) < 9)"),
            ("run", "added_short"): ("c", ("added",), "CHECK (length(added) < 9)"),
        },
    }
    assert narrowings(before, checked) == [
        "constraint note_short on run binds existing ['note']"
    ], "a constraint on a new column narrows nothing an older build wrote"


async def test_a_build_is_ready_inside_its_range_and_says_why_outside_it(
    migrated: tuple[str, PostgresPersistence],
) -> None:
    url, persistence = migrated
    head = head_revision()
    assert head is not None
    previous = lineage(head)[1]
    await check_schema(persistence.engine)

    run(url, f"UPDATE alembic_version SET version_num = '{previous}'")  # noqa: S608 — a revision
    with pytest.raises(SchemaOutOfDate, match="run `make migrate`"):
        await check_schema(persistence.engine)
    await check_schema(persistence.engine, oldest_schema=previous)

    # A newer build migrated the database and still serves this one: the previous release
    # beside the next (ADR-0093 §2).
    run(url, "UPDATE alembic_version SET version_num = '9999_newer'")
    assert await oldest_code(persistence.engine) is not None
    await check_schema(persistence.engine)

    # It contracted past this build: not ready, and the reason names the way back.
    run(url, f"CREATE OR REPLACE FUNCTION {OLDEST_CODE}() RETURNS text LANGUAGE sql "
        "IMMUTABLE AS $$ SELECT '9998_contracted'::text $$")  # fmt: skip
    with pytest.raises(SchemaOutOfDate, match="serves versions from schema revision 9998"):
        await check_schema(persistence.engine)

    # A schema that declares nothing is never taken for one that serves this build.
    run(url, f"DROP FUNCTION {OLDEST_CODE}()")
    with pytest.raises(SchemaOutOfDate, match="names no oldest version"):
        await check_schema(persistence.engine)


async def test_migrating_on_start_leaves_a_newer_schema_as_it_is(
    migrated: tuple[str, PostgresPersistence],
) -> None:
    url, persistence = migrated
    assert await upgrade(url) is True, "at its own head there is nothing to do, and it says so"
    run(url, "UPDATE alembic_version SET version_num = '9999_newer'")
    assert await upgrade(url) is False
    [(version,)] = run(url, "SELECT version_num FROM alembic_version")
    assert version == "9999_newer"
    await check_schema(persistence.engine)
