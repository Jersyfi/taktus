"""The database URL as the operator writes it, and as the driver wants it.

An operator writes `postgresql://user@host:5432/name` (or `postgres://…`). SQLAlchemy needs the
driver named: `postgresql+psycopg://…`. This is the one place that adds it, so that neither the
configuration nor the documentation has to know the driver's name.
"""

from __future__ import annotations

DRIVER = "postgresql+psycopg://"


def for_sqlalchemy(url: str) -> str:
    for plain in ("postgresql://", "postgres://"):
        if url.startswith(plain):
            return DRIVER + url[len(plain) :]
    if url.startswith(DRIVER):
        return url
    raise ValueError("the database URL must start with postgresql://")


def described(url: str) -> str:
    """The URL without anything that could be a secret: scheme, host, port and database name.
    What the command line and a log may say about where the state lives."""
    rest = url.split("://", 1)[-1]
    location, _, name = rest.partition("/")
    host = location.rsplit("@", 1)[-1]
    return f"postgresql://{host}/{name.split('?', 1)[0]}"
