"""The chat connector against the real service: the contract's suite, and the promise of
ADR-0005, tested outside.

A fake proves the mechanics; only the real service proves that its web interface keeps what the
connector relies on — the metadata on a message, returned when asked for, and a thread read in
order. This test runs when a scratch conversation and the app's token are set, and skips
otherwise:

    TAKTUS_LIVE_CHAT_CONVERSATION=C…           the identifier of a conversation that exists for
                                               this test alone, with the app in it; the test
                                               posts a handful of messages there and deletes none
    TAKTUS_CREDENTIAL_CHAT_TOKEN_FILE=…        the file that holds the app's bot token
                                               (NEED-0018); or CHAT_TOKEN, for a run by hand

It runs in the workflow `live`, monthly and by dispatch on `main`, never on a pull request
(DEC-0048). The value is read by the connector at the moment of each call and never written
anywhere by this test. The intake checks of the suite sign recorded payloads with a secret this
test makes up: they prove the connector's verification, which no real delivery is needed for.
"""

from __future__ import annotations

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

from taktus.adapters.driven.connectors.slack.declaration import (
    ACTIONS_CREDENTIAL,
    INTAKE_CREDENTIAL,
)
from taktus.adapters.driven.connectors.slack.server import (
    DEFAULT_TARGET,
    Config,
    Connector,
    secret_named,
)
from taktus.conformance import ConnectorSuiteOptions, Status, run_connector_suite

type Json = dict[str, Any]

CONVERSATION = os.environ.get("TAKTUS_LIVE_CHAT_CONVERSATION", "")
TARGET = os.environ.get("TAKTUS_LIVE_CHAT_TARGET") or DEFAULT_TARGET
"""The service's web interface; another only to rehearse this test against the fake."""
CONNECTOR = Path(__file__).resolve().parents[3] / "src/taktus/adapters/driven/connectors/slack"

pytestmark = pytest.mark.skipif(
    not (CONVERSATION and secret_named(ACTIONS_CREDENTIAL)),
    reason="set TAKTUS_LIVE_CHAT_CONVERSATION and the app's token "
    "(TAKTUS_CREDENTIAL_CHAT_TOKEN_FILE, or CHAT_TOKEN) to run against the service",
)


def context(step: str, key: str) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_live",
        "run_id": "run_live",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key,
        "credentials": [{"name": ACTIONS_CREDENTIAL, "injected_as": "env"}],
    }


async def post(text: str, key: str, thread: str | None = None) -> Json:
    """One post, on a connector of its own: no memory is shared between two calls."""
    input: Json = {"address": CONVERSATION, "text": text}
    if thread is not None:
        input["thread"] = thread
    result = await Connector(Config(target=TARGET)).call(
        "chat.threads.post", context("post", key), input
    )
    content = result.structured_content
    assert isinstance(content, dict) and not result.is_error, content
    return content


@pytest.fixture
def connector(tmp_path: Path) -> Iterator[tuple[str, Path, str]]:
    """The connector as a process against the real service, with a made-up signing secret."""
    secret = "live-" + secrets.token_hex(16)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    log = tmp_path / "chat-connector.log"
    env = {**os.environ, INTAKE_CREDENTIAL: secret}
    env.pop(f"TAKTUS_CREDENTIAL_{INTAKE_CREDENTIAL}_FILE", None)
    with log.open("wb") as handle:
        process = subprocess.Popen(  # noqa: S603 — our own module, fixed arguments
            [
                sys.executable,
                "-m",
                "taktus.adapters.driven.connectors.slack",
                "--port",
                str(port),
                "--target",
                TARGET,
            ],
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=env,
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
        yield f"http://127.0.0.1:{port}/mcp", log, secret
    finally:
        process.terminate()
        process.wait(timeout=5)


async def test_the_suite_passes_against_the_real_service(
    connector: tuple[str, Path, str],
) -> None:
    endpoint, log, secret = connector
    unique = secrets.token_hex(6)
    parent = await post(f"Conformance run {unique} of the chat connector.", f"live:{unique}:parent")
    thread = parent["output"]["ts"]
    scenario = json.loads((CONNECTOR / "scenario.json").read_text())
    scenario["read"]["input"] = {"address": CONVERSATION, "thread": thread}
    scenario["writes"] = [
        {
            "operation": "chat.threads.post",
            "input": {
                "address": CONVERSATION,
                "thread": thread,
                "text": "Reply {{unique}} from the conformance suite.",
            },
        }
    ]
    scenario["invalid"]["input"] = {"address": "C0000000000", "thread": thread}
    token = secret_named(ACTIONS_CREDENTIAL)
    assert token is not None
    report = await run_connector_suite(
        ConnectorSuiteOptions(
            endpoint=endpoint,
            scenario=scenario,
            credential_values={ACTIONS_CREDENTIAL: token, INTAKE_CREDENTIAL: secret},
            adapter_log=log,
            timeout=60.0,
            scenario_dir=CONNECTOR,
        )
    )
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert {c.id: c.status for c in report.checks}["C-10"] is Status.PENDING


async def test_a_reply_retried_after_a_restart_is_posted_once_on_the_real_service() -> None:
    unique = secrets.token_hex(6)
    parent = await post(f"Restart test {unique}.", f"live:{unique}:parent")
    thread = parent["output"]["ts"]
    key = f"live:{unique}:reply"
    first = await post(f"The answer of {unique}.", key, thread)
    again = await post(f"The answer of {unique}.", key, thread)
    assert first["effect"]["replayed"] is False and again["effect"]["replayed"] is True
    assert again["effect"]["records"] == first["effect"]["records"]
    read = await Connector(Config(target=TARGET)).call(
        "chat.threads.read",
        context("read", f"live:{unique}:read"),
        {"address": CONVERSATION, "thread": thread},
    )
    content = read.structured_content
    assert isinstance(content, dict) and not read.is_error, content
    answers = [m for m in content["output"]["messages"] if m["text"] == f"The answer of {unique}."]
    assert len(answers) == 1, "the service holds one reply"
    token = secret_named(ACTIONS_CREDENTIAL)
    assert token is not None and token not in json.dumps([first, again, content])


async def test_the_member_list_is_read_from_the_real_service() -> None:
    """DEC-0127's proof on the real service: the app reads the workspace's member list, each
    member with the fields a link needs and nothing else. Only counts are asserted, so that a
    failure prints no member of the workspace into a public log."""
    result = await Connector(Config(target=TARGET)).call(
        "chat.members.list", context("members", f"live:{secrets.token_hex(6)}:members"), {}
    )
    content = result.structured_content
    assert isinstance(content, dict)
    cause = content.get("cause") if result.is_error else None
    assert cause is None, f"the member list was refused: {cause}"
    members = content["output"]["members"]
    fields = {"account", "name", "kind", "active", "address", "address_confirmed"}
    shaped = sum(1 for m in members if set(m) == fields)
    people = sum(1 for m in members if m["kind"] == "person" and m["active"])
    automations = sum(1 for m in members if m["kind"] == "automation")
    addressed = sum(1 for m in members if m["kind"] == "person" and m["address"])
    assert content["output"]["complete"] is True
    assert shaped == len(members), "every member carries exactly the six fields"
    assert people >= 1, "at least one active person: the owner"
    assert automations >= 1, "at least one automation: Taktus's own app"
    assert addressed >= 1, "the address permission is granted and names an address"
