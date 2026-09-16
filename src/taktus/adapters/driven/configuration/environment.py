from __future__ import annotations

import os
from collections.abc import Mapping

from taktus.ports.configuration import Secret

PREFIX = "TAKTUS_"


def variable(key: str) -> str:
    """`database.url` → `TAKTUS_DATABASE_URL`."""
    return PREFIX + key.replace(".", "_").upper()


class EnvironmentConfiguration:
    """Every key is one environment variable with the prefix `TAKTUS_`. An empty variable
    counts as not configured, so that `.env.example` — names only — can be used as is."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = os.environ if environment is None else environment

    def get(self, key: str) -> str | None:
        value = self._environment.get(variable(key), "").strip()
        return value or None

    def secret(self, key: str) -> Secret | None:
        value = self.get(key)
        return None if value is None else Secret(value)
