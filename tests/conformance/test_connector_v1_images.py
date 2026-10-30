# ruff: noqa: S104, S108, S607 — containers of the test bind inside themselves; the engine is on the path
"""The suite against every connector this release ships, each from its own image (ADR-0158,
issue #339).

The other files of this directory prove each connector as a process from the checkout, faults
included. This one proves what ships: each connector runs from `taktus-connector-<name>`, the
image `.github/workflows/images.yml` releases, built from its stage of `connectors/Dockerfile`
(tests/images.py), and must pass the same suite against the same fake of its product. The
starters are the same fixtures; only `LAUNCH` differs (`ImageLauncher`). The fakes stay on the
host, and the container reaches them as `host.docker.internal`. The mail connector is the one
exception: it refuses to send a password in clear to any machine but its own, so its fake runs
in a container of its own and the connector shares that container's network.

Needs Docker; skips without it, and fails under TAKTUS_REQUIRE_DATABASE, where Docker is
required, as every image test does.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fakes.ports import free_port

from taktus.conformance import Report, Status

from . import conftest
from .conftest import (
    BUSINESS,
    CONNECTORS,
    FAKE_MAIL,
    MAIL_ACTIONS,
    MAIL_INTAKE,
    MAIL_LOGIN,
    ROOT,
    VENDOR,
    ImageLauncher,
    RunningConnector,
    _secret_files,
    wait_ready,
)

type Start = Callable[..., RunningConnector]
PROVEN = frozenset(
    {*BUSINESS, "github", "slack", "bookstack", "mail", "prometheus", "httpcheck", "vendor"}
)
"""Every connector a test below starts from its image."""


@pytest.fixture
def in_images(
    connector_image: Callable[[str], str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ImageLauncher]:
    launcher = ImageLauncher(connector_image, mounts=[tmp_path, ROOT / "tests"])
    monkeypatch.setattr(conftest, "LAUNCH", launcher)
    yield launcher
    launcher.remove()


def passed(report: Report, connector: RunningConnector) -> None:
    assert report.failed == [] and report.inconclusive == [], report.render()
    statuses = {c.id: c.status for c in report.checks}
    assert statuses["C-10"] is Status.PENDING, report.render()
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text


@pytest.mark.parametrize("module", sorted(BUSINESS))
async def test_a_business_connector_passes_from_its_image(
    module: str, in_images: ImageLauncher, start_business_connector: Start
) -> None:
    connector = start_business_connector(module)
    passed(await connector.run_suite(), connector)


async def test_the_reference_connector_passes_from_its_image(
    in_images: ImageLauncher, start_connector: Start
) -> None:
    connector = start_connector()
    passed(await connector.run_suite(), connector)


async def test_the_chat_connector_passes_from_its_image(
    in_images: ImageLauncher, start_chat_connector: Start
) -> None:
    connector = start_chat_connector()
    passed(await connector.run_suite(), connector)


async def test_the_knowledge_connector_passes_from_its_image(
    in_images: ImageLauncher, start_knowledge_connector: Start
) -> None:
    connector = start_knowledge_connector()
    passed(await connector.run_suite(), connector)


@pytest.fixture
def mail_in_its_image(
    connector_image: Callable[[str], str], tmp_path: Path
) -> Iterator[RunningConnector]:
    """The fake mail server in a container from the connector's image, and the connector in
    a second container on the first one's network, so that the fake is on its own machine."""
    image = connector_image("mail")
    password, secret = "pw-" + secrets.token_hex(12), "mis-" + secrets.token_hex(12)
    imap, smtp, http, port = free_port(), free_port(), free_port(), free_port()
    suffix = secrets.token_hex(3)
    pod, name = f"taktus-conformance-mail-fake-{suffix}", f"taktus-conformance-mail-{suffix}"
    user = ["--user", f"{os.getuid()}:{os.getgid()}"] if sys.platform == "linux" else []
    fake_env = {**os.environ, "FAKE_MAIL_ACCOUNTS": f"{MAIL_LOGIN}:{password}"}
    fakes = FAKE_MAIL.parent
    fake_log = tmp_path / "mail-fake.log"
    with fake_log.open("wb") as handle:
        fake = subprocess.Popen(  # noqa: S603 — our own image and script, fixed arguments
            [
                "docker",
                "run",
                "--rm",
                "--name",
                pod,
                "-e",
                "FAKE_MAIL_ACCOUNTS",
                "-p",
                f"127.0.0.1:{http}:{http}",
                "-p",
                f"127.0.0.1:{port}:{port}",
                "-v",
                f"{fakes}:{fakes}:ro",
                "--entrypoint",
                "python",
                image,
                str(FAKE_MAIL),
                "--host",
                "0.0.0.0",
                "--imap-port",
                str(imap),
                "--smtp-port",
                str(smtp),
                "--http-port",
                str(http),
            ],
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=fake_env,
        )
    service_url = f"http://127.0.0.1:{http}"
    env = {
        **os.environ,
        **_secret_files(tmp_path, "image", {MAIL_ACTIONS: password, MAIL_INTAKE: secret}),
    }
    log = tmp_path / "mail-connector.log"
    started = [fake]
    try:
        wait_ready(fake, f"{service_url}/_fake/state", fake_log, "fake mail server")
        variables = [
            arg for key in env if key.startswith("TAKTUS_CREDENTIAL_") for arg in ("-e", key)
        ]
        with log.open("wb") as handle:
            connector = subprocess.Popen(  # noqa: S603 — our own image, fixed arguments
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    name,
                    "--network",
                    f"container:{pod}",
                    "--read-only",
                    "--tmpfs",
                    "/tmp",
                    *user,
                    *variables,
                    "-v",
                    f"{tmp_path}:{tmp_path}:ro",
                    image,
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(port),
                    "--imap",
                    f"127.0.0.1:{imap}",
                    "--smtp",
                    f"127.0.0.1:{smtp}",
                    "--user",
                    MAIL_LOGIN,
                    "--security",
                    "none",
                ],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=env,
            )
        started.append(connector)
        endpoint = f"http://127.0.0.1:{port}"
        wait_ready(connector, f"{endpoint}/health", log, "mail connector")
        yield RunningConnector(
            f"{endpoint}/mcp",
            log,
            service_url,
            {MAIL_ACTIONS: password, MAIL_INTAKE: secret},
            connector,
            scenario=CONNECTORS / "mail" / "scenario.json",
        )
    finally:
        for container in (name, pod):
            subprocess.run(  # noqa: S603 — the containers this fixture started
                ["docker", "rm", "--force", container],
                capture_output=True,
                check=False,
                timeout=60,
            )
        for process in started:
            process.wait(timeout=30)


async def test_the_mail_connector_passes_from_its_image(
    mail_in_its_image: RunningConnector,
) -> None:
    passed(await mail_in_its_image.run_suite(), mail_in_its_image)


async def test_the_metrics_connector_passes_from_its_image(
    in_images: ImageLauncher, start_metrics_connector: Start
) -> None:
    connector = start_metrics_connector()
    passed(await connector.run_suite(), connector)


async def test_the_check_connector_passes_from_its_image(
    in_images: ImageLauncher, start_check_connector: Start
) -> None:
    connector = start_check_connector()
    passed(await connector.run_suite(), connector)


async def test_the_vendor_connector_passes_from_its_image_under_a_manifest(
    in_images: ImageLauncher, start_vendor_connector: Start
) -> None:
    connector = start_vendor_connector(server="notes", manifest=VENDOR / "notes-manifest.json")
    passed(await connector.run_suite(), connector)


def test_every_connector_the_release_ships_is_proven_here() -> None:
    """A connector added under connectors/ without a test above fails here, not in silence."""
    shipped = {path.parent.name for path in CONNECTORS.glob("*/__main__.py")}
    assert shipped == PROVEN
