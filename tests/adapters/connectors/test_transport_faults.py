"""A transport fault never carries what was sent (issue #267): the text of an HTTP library's error
can quote a header, and the header holds the credential (C-04). Both connectors that speak HTTP
with a bearer token name the error's type, nothing of its text."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import httpx
import pytest
from taktus_connectors.github import api as github
from taktus_connectors.github import server as github_server
from taktus_connectors.slack import api as slack
from taktus_connectors.slack import server as slack_server

from taktus.conformance.connector.rules import CHECKS
from taktus.conformance.connector.suite import ConnectorSuiteOptions, Seen, _c04
from taktus.conformance.findings import Findings

SECRET = "made-up-credential-for-this-test"  # noqa: S105


def refusing(error: type[httpx.HTTPError]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error(f"Illegal header value b'Bearer {SECRET}'", request=request)

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("error", [httpx.LocalProtocolError, httpx.ConnectError])
async def test_the_repository_connector_names_the_fault_and_never_its_text(
    error: type[httpx.HTTPError],
) -> None:
    client = github.Api("https://service.invalid", "owner/name", SECRET)
    await client.close()
    client._client = httpx.AsyncClient(  # the transport is the test's
        base_url=client.target,
        transport=refusing(error),
        headers={"Authorization": f"Bearer {SECRET}"},
    )
    with pytest.raises(github.TargetError) as raised:
        await client.get("/repos/owner/name/issues/1")
    await client.close()
    assert SECRET not in str(raised.value) and SECRET not in repr(raised.value.args)
    assert error.__name__ in str(raised.value)


@pytest.mark.parametrize("error", [httpx.LocalProtocolError, httpx.ConnectError])
async def test_the_chat_connector_names_the_fault_and_never_its_text(
    error: type[httpx.HTTPError],
) -> None:
    client = slack.Api("https://service.invalid", SECRET)
    await client.close()
    client._client = httpx.AsyncClient(  # the transport is the test's
        base_url=client.target,
        transport=refusing(error),
        headers={"Authorization": f"Bearer {SECRET}"},
    )
    with pytest.raises(slack.TargetError) as raised:
        await client.read("conversations.info", {"channel": "C1"})
    await client.close()
    assert SECRET not in str(raised.value) and SECRET not in repr(raised.value.args)
    assert error.__name__ in str(raised.value)


# --- a connector's own secrets are never a call's credential -----------------------------------


@pytest.mark.parametrize(
    ("module", "name"),
    [
        (github_server, "REPOSITORY_APP_KEY"),
        (github_server, "REPOSITORY_WEBHOOK_SECRET"),
        (slack_server, "CHAT_SIGNING_SECRET"),
    ],
)
def test_a_call_naming_the_connector_s_own_secret_acts_with_nothing(
    module: ModuleType, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = tmp_path / "own"
    held.write_text(SECRET, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(held))
    by_name = {"credentials": [{"name": name, "injected_as": "env"}]}
    by_path = {"credentials": [{"name": "ANY", "injected_as": "file", "path": str(held)}]}
    assert module.credential_value(by_name) is None
    assert module.credential_value(by_path) is None


def test_a_call_naming_its_own_credential_still_acts_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    given = tmp_path / "token"
    given.write_text(SECRET, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE", str(given))
    context = {"credentials": [{"name": "REPOSITORY_TOKEN", "injected_as": "env"}]}
    assert github_server.credential_value(context) == SECRET


# --- C-04 finds a value of several lines in an error's quoting ---------------------------------


def test_c04_finds_a_key_whose_line_breaks_an_error_escaped() -> None:
    key = "-----BEGIN KEY-----\n" + "\n".join(["A" * 40, "B" * 40]) + "\n-----END KEY-----"
    quoted = (
        f"transport fault: Illegal header value b'Bearer {key.replace(chr(10), chr(92) + 'n')}'"
    )
    seen = Seen()
    seen.note("an error", quoted)
    findings = Findings(CHECKS)
    options = ConnectorSuiteOptions(endpoint="x", scenario={}, credential_values={"KEY": key})
    _c04(options, seen, findings)
    assert findings.failed("C-04")
