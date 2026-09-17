"""The configuration port over the environment, and the secret that never shows itself."""

from __future__ import annotations

from pathlib import Path

import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.configuration.environment import file_variable, variable
from taktus.adapters.driven.postgres.url import described, for_sqlalchemy
from taktus.ports.configuration import ConfigurationError, Secret


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


def test_a_secret_is_read_from_the_file_the_environment_points_at(tmp_path: Path) -> None:
    secret_file = tmp_path / "database_url"
    secret_file.write_text("postgresql://u:p@h/d\n", encoding="utf-8")
    configuration = EnvironmentConfiguration({"TAKTUS_DATABASE_URL_FILE": str(secret_file)})
    assert configuration.secret("database.url") == Secret("postgresql://u:p@h/d"), (
        "the trailing newline is not part of the value"
    )
    assert configuration.source("database.url") == f"file {secret_file}"
    assert configuration.get("database.url") is None, "the value never enters the environment"
    assert file_variable("database.url") == "TAKTUS_DATABASE_URL_FILE"


def test_the_source_of_an_inline_secret_is_named() -> None:
    configuration = EnvironmentConfiguration({"TAKTUS_DATABASE_URL": "postgresql://u@h/d"})
    assert configuration.source("database.url") == "environment"
    assert configuration.source("worker") is None
    assert configuration.name("database.url") == "TAKTUS_DATABASE_URL"


def test_a_secret_from_both_places_is_refused_naming_the_variables(tmp_path: Path) -> None:
    secret_file = tmp_path / "s"
    secret_file.write_text("value-in-file", encoding="utf-8")
    configuration = EnvironmentConfiguration(
        {"TAKTUS_DATABASE_URL": "value-inline", "TAKTUS_DATABASE_URL_FILE": str(secret_file)}
    )
    with pytest.raises(ConfigurationError) as raised:
        configuration.secret("database.url")
    message = str(raised.value)
    assert "TAKTUS_DATABASE_URL_FILE" in message and "TAKTUS_DATABASE_URL" in message
    assert "value-inline" not in message and "value-in-file" not in message


def test_a_secret_file_that_cannot_be_read_names_the_variable_not_a_value(
    tmp_path: Path,
) -> None:
    configuration = EnvironmentConfiguration({"TAKTUS_DATABASE_URL_FILE": str(tmp_path / "no")})
    with pytest.raises(ConfigurationError, match="TAKTUS_DATABASE_URL_FILE: the file cannot"):
        configuration.secret("database.url")
    empty = tmp_path / "empty"
    empty.write_text("\n", encoding="utf-8")
    configuration = EnvironmentConfiguration({"TAKTUS_DATABASE_URL_FILE": str(empty)})
    with pytest.raises(ConfigurationError, match="is empty"):
        configuration.secret("database.url")
