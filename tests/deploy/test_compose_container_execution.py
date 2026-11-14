"""The overlay for worker steps on one server (deploy/docker/compose.container-execution.yml):
it switches the execution port to `container`, mounts the engine's socket where the setting
names it, joins the gateway to the network Compose creates, and Compose accepts it over
compose.yml. Whether a job then runs end to end through the mounted socket is not proven here:
no test runs Taktus inside a container with the socket (single-server.md)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.composition.settings import load_execution

DOCKER = Path(__file__).resolve().parents[2] / "deploy" / "docker"
OVERLAY = DOCKER / "compose.container-execution.yml"


def overlay() -> dict:
    return yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))["services"]["taktus"]


def test_the_overlay_wires_the_container_execution_the_settings_read() -> None:
    taktus = overlay()
    environment = taktus["environment"]
    project = yaml.safe_load((DOCKER / "compose.yml").read_text(encoding="utf-8"))["name"]
    assert environment["TAKTUS_EXECUTION_NETWORK"] == f"{project}_default"
    (mount,) = taktus["volumes"]
    assert mount.rsplit(":", 1)[1] == environment["TAKTUS_EXECUTION_ENGINE_SOCKET"]
    settings = load_execution(
        EnvironmentConfiguration({**environment, "TAKTUS_EXECUTION_UNIT": "worker:1"})
    )
    assert settings.kind.value == "container"
    assert settings.engine_socket == environment["TAKTUS_EXECUTION_ENGINE_SOCKET"]
    assert settings.network == "taktus_default"
    assert taktus["group_add"], "the image's user reaches the socket through its group"


def test_compose_accepts_the_overlay_over_compose_yml(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("the compose check needs docker with the compose plugin")
    probe = subprocess.run(  # noqa: S603 — a fixed command
        [docker, "compose", "version"], capture_output=True, text=True, check=False
    )
    if probe.returncode != 0:
        pytest.skip("the compose check needs docker with the compose plugin")
    shutil.copy(DOCKER / "compose.yml", tmp_path / "compose.yml")
    shutil.copy(OVERLAY, tmp_path / "overlay.yml")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    for name in ("postgres_password", "database_url"):
        (secrets / name).write_text("stand-in\n", encoding="utf-8")
    command = [
        docker,
        "compose",
        "--project-directory",
        str(tmp_path),
        "-f",
        str(tmp_path / "compose.yml"),
        "-f",
        str(tmp_path / "overlay.yml"),
        "config",
        "--format",
        "json",
    ]
    refused = subprocess.run(  # noqa: S603 — a fixed command and files of this test
        command, capture_output=True, text=True, check=False, env={"PATH": "/usr/bin:/bin"}
    )
    assert refused.returncode != 0 and "TAKTUS_ENGINE_SOCKET_GID" in refused.stderr
    completed = subprocess.run(  # noqa: S603 — a fixed command and files of this test
        command,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "TAKTUS_ENGINE_SOCKET_GID": "998"},
    )
    assert completed.returncode == 0, completed.stderr
    taktus = json.loads(completed.stdout)["services"]["taktus"]
    assert taktus["environment"]["TAKTUS_EXECUTION"] == "container"
    assert taktus["group_add"] == ["998"]
    sources = [v.get("source") for v in taktus["volumes"]]
    assert "/var/run/docker.sock" in sources
