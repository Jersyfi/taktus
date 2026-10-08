"""The reference connector as Taktus's own app (ADR-0033, DEC-0058), against the fake service.

The app mints a token that lives an hour from its private key, for the one repository, and acts
with it under its own name. What is shown here: a token is minted from the key, used, held while
it is good and replaced before it expires; the app serves the one credential name it is bound
to and is no fallback for any other; a key the service does not accept, an app that is not
installed and a suspended installation each fail the call with the reason; and neither the key,
nor a token, nor a signed statement appears in a result, an error or the log.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taktus.adapters.driven.connectors.github import __main__ as connector_main
from taktus.adapters.driven.connectors.github.app import (
    APP_ID_VARIABLE,
    APP_KEY_VARIABLE,
    REFRESH_MARGIN,
    AppConfig,
)
from taktus.adapters.driven.connectors.github.server import Config, Connector

from .conftest import WRITE_CREDENTIAL, Service, private_key_pem

type Json = dict[str, Any]

REPOSITORY = "acme/product"


@pytest.fixture
def as_app(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    """No token in the environment: whatever the connector acts with, the app minted it."""
    monkeypatch.delenv(WRITE_CREDENTIAL, raising=False)
    service.reset()


def app_connector(service: Service, *, key_file: Path | None = None) -> Connector:
    app = AppConfig(service.app_id, key_file or service.app_key_file)
    return Connector(Config(target=service.url, repository=REPOSITORY, timeout=5.0, app=app))


def context(step: str, key: str, *credentials: Json) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_taktus_app",
        "run_id": "run_app",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key,
        "credentials": list(credentials) or [{"name": WRITE_CREDENTIAL, "injected_as": "env"}],
    }


async def call(connector: Connector, operation: str, ctx: Json, input: Json) -> tuple[bool, Json]:
    result = await connector.call(operation, ctx, input)
    assert isinstance(result.structured_content, dict)
    return bool(result.is_error), result.structured_content


def issued(service: Service) -> list[str]:
    return list(service.app()["issued"])


@pytest.mark.usefixtures("as_app")
async def test_the_connector_acts_under_the_apps_own_name(service: Service) -> None:
    """What the app writes is the app's, not a person's: the author the service records is an
    automation. The token was asked for this repository alone."""
    connector = app_connector(service)
    error, created = await call(
        connector, "repository.issues.create", context("create", "run_app:c:1"), {"title": "t"}
    )
    assert not error, created
    assert created["effect"]["kind"] == "write"
    number = created["output"]["number"]
    error, read = await call(
        connector, "repository.issues.read", context("read", "run_app:r:1"), {"number": number}
    )
    assert not error, read
    assert read["output"]["author"]["kind"] == "automation"
    pull_request = {"head": "taktus/issue-1", "base": "main", "title": "t", "body": "b"}
    error, opened = await call(
        connector, "repository.pullrequests.open", context("open", "run_app:o:1"), pull_request
    )
    assert not error, opened
    assert opened["output"]["author"]["kind"] == "automation"
    assert service.app()["requested"][-1] == {"repositories": ["product"]}


@pytest.mark.usefixtures("as_app")
async def test_a_token_is_held_while_good_and_replaced_before_it_expires(
    service: Service,
) -> None:
    connector = app_connector(service)
    assert connector.app is not None
    before = len(issued(service))
    error, first = await call(
        connector, "repository.issues.read", context("r", "run_app:r:1"), {"number": 1}
    )
    assert not error, first
    # Minting took two requests — the installation, the exchange — and the read one more; the
    # call counts all three as its consumption.
    assert first["consumption"] == {"quota_units": 3}
    assert len(issued(service)) == before + 1

    error, second = await call(
        connector, "repository.issues.read", context("r", "run_app:r:2"), {"number": 1}
    )
    assert not error
    assert second["consumption"] == {"quota_units": 1}
    assert len(issued(service)) == before + 1, "a good token is used again, not minted anew"

    # The clock moves to just inside the margin before the token's expiry: the token is still
    # valid at the service, and it is replaced anyway, before the call uses it.
    started = connector.app.clock()
    connector.app.clock = lambda: started + 3600 - REFRESH_MARGIN + 1
    error, third = await call(
        connector, "repository.issues.read", context("r", "run_app:r:3"), {"number": 1}
    )
    assert not error, third
    assert third["consumption"] == {"quota_units": 2}, "the installation is known; one exchange"
    assert len(issued(service)) == before + 2


@pytest.mark.usefixtures("as_app")
async def test_the_app_serves_its_one_name_and_is_no_fallback(service: Service) -> None:
    """C-03 in the app mode: a call that references no credential, or another name with no
    value, is refused without a request, exactly as in the token mode."""
    connector = app_connector(service)
    before = len(service.app()["statements"])
    ctx = {**context("r", "run_app:r:1"), "credentials": []}
    error, none = await call(connector, "repository.issues.read", ctx, {"number": 1})
    assert error
    assert (none["cause"], none["effect"]) == ("unauthenticated", "none")
    assert "consumption" not in none

    other = {"name": "REPOSITORY_TOKEN_NOBODY", "injected_as": "env"}
    error, missing = await call(
        connector, "repository.issues.read", context("r", "run_app:r:2", other), {"number": 1}
    )
    assert error
    assert missing["cause"] == "unauthenticated"
    assert len(service.app()["statements"]) == before, "nothing was signed for either"


@pytest.mark.usefixtures("as_app")
async def test_a_removed_installation_fails_the_step_with_the_reason(service: Service) -> None:
    held = app_connector(service)
    error, _ = await call(
        held, "repository.issues.read", context("r", "run_app:r:1"), {"number": 1}
    )
    assert not error

    service.control("/_fake/app", {"installed": False})
    # A connector that holds a token learns of the removal when the token is refused …
    error, refused = await call(
        held, "repository.issues.read", context("r", "run_app:r:2"), {"number": 1}
    )
    assert error
    assert (refused["cause"], refused["effect"], refused["retryable"]) == (
        "unauthenticated",
        "none",
        False,
    )
    assert "installation token was not accepted" in refused["detail"]
    # … and the next call, which mints anew, says which.
    error, again = await call(
        held, "repository.issues.read", context("r", "run_app:r:3"), {"number": 1}
    )
    assert error
    assert again["cause"] == "unauthenticated"
    assert "not installed on acme/product" in again["detail"]
    assert again["consumption"] == {"quota_units": 1}, "the lookup that found no installation"

    service.control("/_fake/app", {"installed": True})
    error, _ = await call(
        held, "repository.issues.read", context("r", "run_app:r:4"), {"number": 1}
    )
    assert not error, "installed again, the app acts again"


@pytest.mark.usefixtures("as_app")
async def test_a_suspended_installation_fails_the_step_with_the_reason(service: Service) -> None:
    service.control("/_fake/app", {"suspended": True})
    error, refused = await call(
        app_connector(service), "repository.issues.read", context("r", "run_app:r:1"), {"number": 1}
    )
    assert error
    assert (refused["cause"], refused["effect"], refused["retryable"]) == (
        "unauthenticated",
        "none",
        False,
    )
    assert "suspended" in refused["detail"]
    assert service.state().get(REPOSITORY) is None, "nothing was read or written"


@pytest.mark.usefixtures("as_app")
async def test_a_key_the_service_does_not_accept_fails_the_step_with_the_reason(
    service: Service, tmp_path: Path
) -> None:
    other = tmp_path / "other-key.pem"
    other.write_text(private_key_pem(), encoding="utf-8")
    error, refused = await call(
        app_connector(service, key_file=other),
        "repository.issues.read",
        context("r", "run_app:r:1"),
        {"number": 1},
    )
    assert error
    assert refused["cause"] == "unauthenticated"
    assert "did not accept the app's signed statement" in refused["detail"]

    missing = tmp_path / "absent.pem"
    error, unreadable = await call(
        app_connector(service, key_file=missing),
        "repository.issues.read",
        context("r", "run_app:r:2"),
        {"number": 1},
    )
    assert error
    assert unreadable["cause"] == "unauthenticated"
    assert APP_KEY_VARIABLE in unreadable["detail"]
    assert str(missing) not in unreadable["detail"], "the path is the operator's, not the result's"
    assert "consumption" not in unreadable

    garbage = tmp_path / "garbage.pem"
    garbage.write_text("not a key\n", encoding="utf-8")
    error, unusable = await call(
        app_connector(service, key_file=garbage),
        "repository.issues.read",
        context("r", "run_app:r:3"),
        {"number": 1},
    )
    assert error
    assert "does not hold a usable RSA private key" in unusable["detail"]


@pytest.mark.usefixtures("as_app")
async def test_no_key_token_or_statement_reaches_a_result_an_error_or_the_log(
    service: Service, capsys: pytest.CaptureFixture[str]
) -> None:
    connector = app_connector(service)
    texts: list[str] = []
    for operation, input in (
        ("repository.issues.read", {"number": 1}),
        ("repository.issues.create", {"title": "t", "body": "b"}),
        ("repository.issues.read", {"number": 999}),
    ):
        result = await connector.call(operation, context("s", "run_app:s:1"), input)
        texts.append(json.dumps(result.structured_content))
        texts.extend(getattr(c, "text", "") for c in result.content)
    service.control("/_fake/app", {"installed": False})
    for step in ("a", "b"):  # the refused token, then the refused minting
        result = await connector.call(
            "repository.issues.read", context(step, f"run_app:{step}:1"), {"number": 1}
        )
        assert result.is_error
        texts.append(json.dumps(result.structured_content))
    texts.append(capsys.readouterr().err)

    seen = service.app()
    secrets_ = [*seen["issued"], *seen["statements"]]
    key_lines = [line for line in service.app_key.splitlines() if "-----" not in line and line]
    assert seen["issued"] and seen["statements"] and key_lines
    for text in texts:
        for value in secrets_:
            assert value not in text
        for line in key_lines:
            assert line not in text


def test_the_mode_is_chosen_by_both_variables_or_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert AppConfig.from_environment({}) is None
    config = AppConfig.from_environment({APP_ID_VARIABLE: "1", APP_KEY_VARIABLE: "/k.pem"})
    assert config == AppConfig("1", Path("/k.pem"))
    for one in ({APP_ID_VARIABLE: "1"}, {APP_KEY_VARIABLE: "/k.pem"}):
        with pytest.raises(ValueError, match="needs"):
            AppConfig.from_environment(one)

    monkeypatch.setenv(APP_ID_VARIABLE, "1")
    monkeypatch.delenv(APP_KEY_VARIABLE, raising=False)
    with pytest.raises(SystemExit) as stopped:
        connector_main.main(["--repository", "acme/product"])
    assert stopped.value.code == 2
    assert f"{APP_KEY_VARIABLE} is not set" in capsys.readouterr().err
