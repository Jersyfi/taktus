"""The configuration port over the environment, and the secret that never shows itself."""

from __future__ import annotations

import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.configuration.environment import variable
from taktus.adapters.driven.postgres.url import described, for_sqlalchemy
from taktus.ports.configuration import Secret


def test_a_key_is_one_prefixed_variable() -> None:
    assert variable("database.url") == "TAKTUS_DATABASE_URL"
    assert variable("worker") == "TAKTUS_WORKER"


def test_values_come_from_the_environment_and_empty_means_unset() -> None:
    configuration = EnvironmentConfiguration(
        {"TAKTUS_DATABASE_URL": "postgresql://u:p@h/d", "TAKTUS_WORKER": "  ", "OTHER": "x"}
    )
    assert configuration.get("worker") is None, "an empty variable is not configured"
    assert configuration.get("tenant") is None
    assert configuration.get("database.url") == "postgresql://u:p@h/d"
    secret = configuration.secret("database.url")
    assert secret == Secret("postgresql://u:p@h/d")
    assert configuration.secret("tenant") is None


def test_a_secret_never_shows_its_value() -> None:
    secret = Secret("hunter2")
    assert "hunter2" not in repr(secret)
    assert "hunter2" not in str(secret)
    assert "hunter2" not in f"{secret}"
    assert secret.reveal() == "hunter2"
    assert secret != Secret("other") and secret == Secret("hunter2")
    with pytest.raises(AttributeError):
        secret.value = "x"  # type: ignore[attr-defined]


def test_the_database_url_is_named_without_its_password() -> None:
    assert described("postgresql://taktus:s3cret@db.internal:5432/taktus") == (
        "postgresql://db.internal:5432/taktus"
    )
    assert described("postgresql://taktus@127.0.0.1:5432/taktus?sslmode=require") == (
        "postgresql://127.0.0.1:5432/taktus"
    )
    assert for_sqlalchemy("postgres://u@h/d") == "postgresql+psycopg://u@h/d"
    assert for_sqlalchemy("postgresql+psycopg://u@h/d") == "postgresql+psycopg://u@h/d"
    with pytest.raises(ValueError, match="postgresql://"):
        for_sqlalchemy("mysql://u@h/d")
