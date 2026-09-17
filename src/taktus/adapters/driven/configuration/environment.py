"""The configuration port over the process environment: `TAKTUS_*` variables.

Every key is one variable with the prefix `TAKTUS_`. An empty variable counts as not
configured, so that `.env.example` — names only — can be used as is.

**A secret is read from a file, not from the environment, wherever a value is secret.** The
variable `TAKTUS_<KEY>_FILE` holds the path; the file holds the value. Environment variables
leak through process listings, crash dumps and the environment of every child process — and
child processes are exactly what this system starts. A secret given inline as `TAKTUS_<KEY>` is
still accepted, because the development database has no password and a test has no file, but
the startup log says where each value came from, and both at once is refused rather than
resolved: an operator who set both has not decided which is the value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from taktus.ports.configuration import ConfigurationError, Secret

PREFIX = "TAKTUS_"
FILE_SUFFIX = "_FILE"


def variable(key: str) -> str:
    """`database.url` → `TAKTUS_DATABASE_URL`."""
    return PREFIX + key.replace(".", "_").upper()


def file_variable(key: str) -> str:
    """`database.url` → `TAKTUS_DATABASE_URL_FILE`: the variable that holds the path to the
    file that holds the value."""
    return variable(key) + FILE_SUFFIX


class EnvironmentConfiguration:
    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = os.environ if environment is None else environment

    def name(self, key: str) -> str:
        return variable(key)

    def get(self, key: str) -> str | None:
        return self._read(variable(key))

    def secret(self, key: str) -> Secret | None:
        inline = self._read(variable(key))
        path = self._read(file_variable(key))
        if inline is not None and path is not None:
            raise ConfigurationError(
                file_variable(key),
                f"is set together with {variable(key)}; a secret comes from one place — keep "
                "the file and unset the variable",
            )
        if path is not None:
            return Secret(self._read_file(key, path))
        return None if inline is None else Secret(inline)

    def source(self, key: str) -> str | None:
        if self._read(file_variable(key)) is not None:
            return f"file {self._read(file_variable(key))}"
        if self._read(variable(key)) is not None:
            return "environment"
        return None

    def _read(self, name: str) -> str | None:
        value = self._environment.get(name, "").strip()
        return value or None

    def _read_file(self, key: str, path: str) -> str:
        try:
            value = Path(path).read_text(encoding="utf-8")
        except OSError as error:
            # The error's own text names the path and the cause and never the content.
            raise ConfigurationError(
                file_variable(key), f"the file cannot be read: {error.strerror or error}"
            ) from None
        # A trailing newline is how most tools write a secret file; it is never part of a value.
        value = value.rstrip("\r\n")
        if not value:
            raise ConfigurationError(file_variable(key), f"the file {path} is empty")
        return value
