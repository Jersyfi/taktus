"""The wiki connector against the real wiki: the contract's suite, the digest of an untouched
page, a hand edit kept, and the guides published there.

A fake proves the mechanics; only the real wiki proves that its interface keeps what the
connector relies on — the tags beside a page, returned unchanged — and shows how it changes the
text it stores. This test runs when the wiki's address and the token are set, and skips
otherwise:

    TAKTUS_LIVE_KNOWLEDGE_TARGET=…                the wiki's base address (NEED-0021)
    TAKTUS_CREDENTIAL_KNOWLEDGE_TOKEN_FILE=…      the file that holds the token `<id>:<secret>`
                                                  of the wiki's user `Taktus`

It runs in the workflow `live`, monthly and by dispatch on `main`, never on a pull request
(DEC-0048). The suite and the edit test write into the scratch book `SCRATCH`, on a shelf of its
own, so that the guides' shelf holds the guides alone; the role may delete nothing, so every run
leaves a handful of pages there. The last test leaves the guides in their two books as
`taktusctl guides publish` would. The token is read by the connector at the moment of each call
and never written anywhere by this test.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from taktus_connectors.bookstack import declaration
from taktus_connectors.bookstack.server import (
    Config,
    Connector,
    build_server,
    secret_named,
)

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driving.cli.guides_command import rendered
from taktus.components.knowledge.application.service import PublishGuides, PublishGuidesHandler
from taktus.conformance import ConnectorSuiteOptions, Status, run_connector_suite
from taktus.ports.worker import CredentialReference

type Json = dict[str, Any]

TARGET = os.environ.get("TAKTUS_LIVE_KNOWLEDGE_TARGET", "")
SCRATCH = ("Taktus live test", "Live test")
"""The shelf and the book NEED-0021 asks for this test alone."""
ROOT = Path(__file__).resolve().parents[3]
CONNECTOR = ROOT / "connectors/taktus_connectors/bookstack"
TOKEN = declaration.ACTIONS_CREDENTIAL

pytestmark = pytest.mark.skipif(
    not (TARGET and secret_named(TOKEN)),
    reason="set TAKTUS_LIVE_KNOWLEDGE_TARGET and the file TAKTUS_CREDENTIAL_KNOWLEDGE_TOKEN_FILE "
    "names to run against the wiki",
)


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def context(step: str, key: str) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_live",
        "run_id": "run_live",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key,
        "credentials": [{"name": TOKEN, "injected_as": "env"}],
    }


async def call(name: str, step: str, input: Json) -> tuple[bool, Json]:
    """One call, on a connector of its own: no memory is shared between two calls."""
    key = f"live:{secrets.token_hex(8)}:{step}"
    result = await Connector(Config(target=TARGET)).call(name, context(step, key), input)
    content = result.structured_content
    assert isinstance(content, dict)
    return bool(result.is_error), content


@pytest.fixture
def connector(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """The connector as a process against the real wiki."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    log = tmp_path / "knowledge-connector.log"
    with log.open("wb") as handle:
        process = subprocess.Popen(  # noqa: S603 — our own module, fixed arguments
            [
                sys.executable,
                "-m",
                "taktus_connectors.bookstack",
                "--port",
                str(port),
                "--target",
                TARGET,
            ],
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=dict(os.environ),
        )
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert process.poll() is None and time.monotonic() < deadline, log.read_text()
            time.sleep(0.1)
        yield f"http://127.0.0.1:{port}/mcp", log
    finally:
        process.terminate()
        process.wait(timeout=5)


async def test_the_suite_passes_against_the_real_wiki(connector: tuple[str, Path]) -> None:
    endpoint, log = connector
    unique = secrets.token_hex(6)
    seeded = [*SCRATCH, f"Conformance run {unique}"]
    failed, answer = await call(
        declaration.WRITE,
        "seed",
        {"place": seeded, "body": f"The page the suite reads, {unique}.", "mark": "live"},
    )
    assert not failed, answer
    scenario = json.loads((CONNECTOR / "scenario.json").read_text())
    scenario["read"]["input"] = {"place": seeded}
    scenario["writes"][0]["input"]["place"] = [*SCRATCH, f"Conformance {unique} {{{{unique}}}}"]
    scenario["invalid"]["input"] = {"place": [*SCRATCH, f"No such page {unique}"]}
    token = secret_named(TOKEN)
    assert token is not None
    report = await run_connector_suite(
        ConnectorSuiteOptions(
            endpoint=endpoint,
            scenario=scenario,
            credential_values={TOKEN: token},
            adapter_log=log,
            timeout=60.0,
            scenario_dir=CONNECTOR,
        )
    )
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert {c.id: c.status for c in report.checks}["C-10"] is Status.PENDING


async def test_an_untouched_page_keeps_its_digest_and_an_edit_is_kept() -> None:
    unique = secrets.token_hex(6)
    place = [*SCRATCH, f"Digest {unique}"]
    body = f"# Digest {unique}\r\n\r\nA line with spaces at its end.   \r\n\r\n\r\n"
    failed, written = await call(
        declaration.WRITE, "write", {"place": place, "body": body, "mark": "live", "expected": None}
    )
    assert not failed, written
    page_id = written["effect"]["records"][0]["id"]

    failed, page = await call(declaration.READ, "read", {"place": place})
    assert not failed, page
    assert page["output"]["digest"] == digest(body), "untouched, so not edited by hand"
    assert page["output"]["mark"] == "live"

    # A person edits the page: its text changes, its tags stay.
    token = secret_named(TOKEN)
    async with httpx.AsyncClient(timeout=30.0) as client:
        edited = await client.put(
            f"{TARGET.rstrip('/')}/api/pages/{page_id}",
            json={"markdown": "Edited by a person."},
            headers={"Authorization": f"Token {token}"},
        )
    assert edited.status_code == 200, edited.status_code

    failed, page = await call(declaration.READ, "read", {"place": place})
    assert not failed, page
    assert page["output"]["digest"] != digest(body)
    assert page["output"]["mark"] == "live"
    failed, error = await call(
        declaration.WRITE,
        "rewrite",
        {"place": place, "body": "Taktus's text again.", "mark": "live", "expected": digest(body)},
    )
    assert failed and error["cause"] == "conflict", error


async def test_the_guides_are_published_into_the_wiki() -> None:
    """The guides of this checkout, published as `taktusctl guides publish` would publish them
    into a directory; then again, where nothing is to be written any more."""
    manifest, source, pages = rendered(ROOT, "HEAD", None, "docs/guides/guides.yaml")
    handler = PublishGuidesHandler(
        McpActionConnector(build_server(Config(target=TARGET)), timeout=60.0)
    )

    def command() -> PublishGuides:
        return PublishGuides(
            tenant="default",
            identity="idn_live",
            run_id=f"guides-live-{secrets.token_hex(8)}",
            manifest=manifest,
            manifest_source=source,
            pages=pages,
            credentials=(CredentialReference(name=TOKEN, injected_as="env"),),
        )

    first = await handler.execute(command())
    print("first", first.counted())
    again = await handler.execute(command())
    print("again", again.counted())
    counted = again.counted()
    assert counted["created"] == counted["updated"] == 0, "a page Taktus wrote looks edited"
    assert counted["kept"] + counted["withheld"] == len(pages) + 2
