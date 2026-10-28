"""A one-server install deploys any configured connector, as the chart does.

`deploy/docker/README.md`, *Connectors*.

The beta runs on one server without Kubernetes (docs/roadmap.md). `deploy/docker/connectors.py`
turns the operator's list into a compose file laid over `compose.yml`: one service per
connector, its credentials as compose secrets read from files, and `TAKTUS_CONNECTORS` on the
`taktus` service. The program is read here as a module; `docker compose config` then reads what
it wrote beside `compose.yml`, in a copy outside the checkout. Without docker compose that last
test skips and says so.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

DOCKER = Path(__file__).resolve().parents[2] / "deploy" / "docker"
EVERY_INTERFACE = "0.0.0.0"  # noqa: S104 — inside the connector's container, as compose runs it
MOUNTED = "/run/secrets/connector_payments_payments_token"
"""Where the payment key's file is mounted: a path, never a value."""


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "taktus_compose_connectors", DOCKER / "connectors.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


connectors = load()

PAYMENTS: dict[str, Any] = {
    "name": "payments",
    "capability": "payments.subscriptions",
    "module": "taktus.adapters.driven.connectors.stripe",
    "port": 9111,
    "credentials": [{"name": "PAYMENTS_TOKEN", "file": "payments_token"}],
}
ERRORS: dict[str, Any] = {
    "name": "errors",
    "capability": "errors.issues",
    "image": "errors-connector:1.2.0",
    "port": 9200,
    "args": ["--target", "https://errors.invalid"],
    "healthPath": "",
}


def test_each_connector_is_a_service_its_credentials_files_and_the_roles_told_where() -> None:
    written = connectors.compose([PAYMENTS, ERRORS])
    services = written["services"]
    payments = services["connector-payments"]
    assert payments["image"] == "taktus:local"
    assert payments["command"] == [
        "python",
        "-m",
        "taktus.adapters.driven.connectors.stripe",
        "--host",
        EVERY_INTERFACE,
        "--port",
        "9111",
    ]
    assert payments["secrets"] == ["connector_payments_payments_token"]
    assert payments["environment"] == {"TAKTUS_CREDENTIAL_PAYMENTS_TOKEN_FILE": MOUNTED}
    assert "ports" not in payments, "reached by the compose network alone"
    assert "/health" in payments["healthcheck"]["test"][-1]
    assert written["secrets"] == {
        "connector_payments_payments_token": {"file": "./secrets/payments_token"}
    }
    errors = services["connector-errors"]
    assert errors["image"] == "errors-connector:1.2.0"
    assert errors["command"] == ["--target", "https://errors.invalid"]
    assert "healthcheck" not in errors and "environment" not in errors
    taktus = services["taktus"]
    assert taktus["environment"]["TAKTUS_CONNECTORS"] == (
        "payments.subscriptions=http://connector-payments:9111/mcp,"
        "errors.issues=http://connector-errors:9200/mcp"
    )
    assert taktus["depends_on"] == {
        "connector-payments": {"condition": "service_healthy"},
        "connector-errors": {"condition": "service_started"},
    }


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([PAYMENTS, {**ERRORS, "name": "payments"}], "is named twice"),
        ([{**PAYMENTS, "name": "chat"}], "is named twice"),
        (
            [PAYMENTS, {**ERRORS, "capability": "payments.subscriptions"}],
            "another connector's label",
        ),
        ([{**ERRORS, "module": "taktus.adapters.driven.connectors.sentry"}], "not both"),
        ([{"name": "a", "capability": "a.b", "port": 1}], "module or image"),
        ([{"name": "a", "capability": "a.b", "module": "m"}], "port is required"),
        ([{**ERRORS, "image": "errors-connector:latest"}], "is not a version"),
        ([{**ERRORS, "image": "errors-connector"}], "names no tag"),
        ([{**PAYMENTS, "credentials": [{"name": "payments", "file": "x"}]}], "not a parameter"),
        ([{**PAYMENTS, "credentials": [{"name": "A_B", "file": "../x"}]}], "needs file"),
        ([{**PAYMENTS, "name": "Payments"}], "is not a connector name"),
    ],
)
def test_a_connector_that_cannot_be_deployed_is_refused(
    entries: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(connectors.Refused, match=message):
        connectors.compose(entries)


def test_without_a_list_nothing_is_written_and_only_its_own_stale_file_goes(tmp_path: Path) -> None:
    listed, output, settings = tmp_path / "connectors.json", tmp_path / "out.yml", tmp_path / "env"
    assert connectors.write(listed, output, settings) == "connectors: none configured"
    assert not output.exists()
    listed.write_text(json.dumps({"connectors": [PAYMENTS]}), encoding="utf-8")
    connectors.write(listed, output, settings)
    assert output.is_file()
    listed.unlink()
    assert "removed" in connectors.write(listed, output, settings)
    assert not output.exists()
    output.write_text("services: {}\n", encoding="utf-8")
    connectors.write(listed, output, settings)
    assert output.is_file(), "a file it did not write is never removed"


def test_the_list_and_the_operators_settings_never_both_name_the_connectors(tmp_path: Path) -> None:
    listed, output, settings = tmp_path / "connectors.json", tmp_path / "out.yml", tmp_path / "env"
    listed.write_text(json.dumps({"connectors": [PAYMENTS]}), encoding="utf-8")
    settings.write_text(
        "TAKTUS_LOG_LEVEL=debug\nTAKTUS_CONNECTORS=a=http://a/mcp\n", encoding="utf-8"
    )
    with pytest.raises(connectors.Refused, match="sets TAKTUS_CONNECTORS"):
        connectors.write(listed, output, settings)
    assert not output.exists()


def test_the_example_list_is_one_compose_accepts(tmp_path: Path) -> None:
    """`docker compose config` reads compose.yml with the file written from the shipped example,
    in a copy outside the checkout, with stand-in secret files."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("the compose check needs docker with the compose plugin")
    probe = subprocess.run(  # noqa: S603 — a fixed command
        [docker, "compose", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("the compose check needs docker with the compose plugin")
    shutil.copy(DOCKER / "compose.yml", tmp_path / "compose.yml")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    for name in ("postgres_password", "database_url", "payments_token", "model_costs_token"):
        (secrets / name).write_text("stand-in\n", encoding="utf-8")
    listed = tmp_path / "connectors.json"
    shutil.copy(DOCKER / "connectors.example.json", listed)
    output = tmp_path / "compose.connectors.yml"
    connectors.write(listed, output, tmp_path / "taktus.env")
    completed = subprocess.run(  # noqa: S603 — a fixed command and files of this test
        [
            docker,
            "compose",
            "--project-directory",
            str(tmp_path),
            "-f",
            str(tmp_path / "compose.yml"),
            "-f",
            str(output),
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    config = json.loads(completed.stdout)
    services = config["services"]
    payments = services["connector-payments"]
    assert payments["image"] == "taktus:local"
    assert [s["source"] for s in payments["secrets"]] == ["connector_payments_payments_token"]
    assert payments["environment"]["TAKTUS_CREDENTIAL_PAYMENTS_TOKEN_FILE"] == MOUNTED
    assert "ports" not in payments
    assert config["secrets"]["connector_payments_payments_token"]["file"] == str(
        secrets / "payments_token"
    )
    taktus = services["taktus"]
    assert taktus["environment"]["TAKTUS_CONNECTORS"] == (
        "payments.subscriptions=http://connector-payments:9111/mcp,"
        "models.costs=http://connector-model-costs:9112/mcp"
    )
    assert taktus["environment"]["TAKTUS_DATABASE_URL_FILE"] == "/run/secrets/database_url"
    assert set(taktus["depends_on"]) == {"postgres", "connector-payments", "connector-model-costs"}
