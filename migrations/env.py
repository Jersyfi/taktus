"""Alembic environment: where the migrations get their connection.

The URL comes from one of two places and from nowhere else: `config.attributes["url"]`, set by
code that runs the migrations in-process (`taktus.adapters.driven.postgres.migrate`), or the
configuration port over the environment — `TAKTUS_DATABASE_URL_FILE`, a file that holds the
URL, or `TAKTUS_DATABASE_URL` inline — read by the `alembic` command line through
`make migrate`. No URL is ever written into a file of this repository.

`target_metadata` is the adapter's Core metadata, so that `alembic check` and the drift test
under `tests/adapters/persistence` can compare the migrated database with it.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.postgres._schema import metadata
from taktus.adapters.driven.postgres.url import for_sqlalchemy
from taktus.ports.configuration import ConfigurationError

config = context.config
target_metadata = metadata


def database_url() -> str:
    given = config.attributes.get("url")
    if not given:
        try:
            secret = EnvironmentConfiguration().secret("database.url")
        except ConfigurationError as error:
            raise SystemExit(str(error)) from None
        given = None if secret is None else secret.reveal()
    if not given:
        raise SystemExit(
            "no database configured: set TAKTUS_DATABASE_URL_FILE or TAKTUS_DATABASE_URL (see "
            ".env.example), or run the migrations from code with the url in config.attributes"
        )
    return for_sqlalchemy(given)


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), connect_args={"options": "-c timezone=UTC"})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
