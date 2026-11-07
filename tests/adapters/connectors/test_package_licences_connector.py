"""The package licence connector answers the licences a public index states for the exact
versions a manifest pins, and guesses none (ADR-0232, UC-03 B-10.04).

Against the fake under `tests/fakes/package_index_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import package_index_service
from fakes.ports import free_port
from taktus_connectors.depsdev.manifests import NotTheFormat, normalised, pinned
from taktus_connectors.depsdev.operations import Config
from taktus_connectors.depsdev.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

CREDENTIAL = "PACKAGES_TOKEN"

LOCK = json.dumps(
    {
        "name": "product",
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "product", "version": "1.0.0"},
            "node_modules/react": {"version": "18.3.1"},
            "node_modules/@colors/colors": {"version": "1.5.0", "dev": True},
            "node_modules/react/node_modules/left-pad": {"version": "1.3.0"},
            "node_modules/copyleft-lib": {"version": "2.0.0"},
            "node_modules/local": {"resolved": "../local", "link": True},
            "node_modules/unheard-of": {"version": "9.9.9"},
        },
    }
)

UV_LOCK = """version = 1
requires-python = ">=3.13"

[[package]]
name = "product"
version = "0.1.0"
source = { editable = "." }

[[package]]
name = "httpx"
version = "0.28.1"
source = { registry = "https://pypi.org/simple" }
"""


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "packages"
    path.write_text("tok-" + secrets.token_hex(8), encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def index() -> Iterator[str]:
    server = package_index_service.make_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


def packages(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


async def test_the_licences_of_a_lockfiles_versions_are_read_one_request_each(index: str) -> None:
    result = await packages(index).call(
        "packages.licences.list", context(), {"format": "package-lock.json", "manifest": LOCK}
    )
    assert result.effect.kind.value == "read"
    found = {p["name"]: p for p in result.output["packages"]}
    assert set(found) == {"@colors/colors", "copyleft-lib", "left-pad", "react", "unheard-of"}
    assert found["react"] == {
        "system": "NPM",
        "name": "react",
        "version": "18.3.1",
        "dev": False,
        "licences": ["MIT"],
        "known": True,
    }
    assert found["@colors/colors"]["dev"] is True, "a scoped name arrives encoded whole"
    assert found["unheard-of"]["known"] is False and found["unheard-of"]["licences"] == []
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 5


async def test_a_limit_bounds_the_reading_and_says_so(index: str) -> None:
    result = await packages(index).call(
        "packages.licences.list",
        context(),
        {"format": "package-lock.json", "manifest": LOCK, "limit": 2},
    )
    assert len(result.output["packages"]) == 2 and result.output["complete"] is False


def test_the_manifests_pin_what_they_pin_and_leave_ranges_unpinned() -> None:
    found, unpinned = pinned(
        "requirements.txt", "Flask_Login[extra]==0.6.3 ; python_version>'3'\nrequests>=2\n# c\n"
    )
    assert [(p.name, p.version) for p in found] == [("flask-login", "0.6.3")]
    assert unpinned == ["requests"]
    found, _ = pinned("uv.lock", UV_LOCK)
    assert [(p.system, p.name, p.version) for p in found] == [("PYPI", "httpx", "0.28.1")]
    assert normalised("Zope.Interface") == "zope-interface"
    with pytest.raises(NotTheFormat):
        pinned("package-lock.json", "not json")


@pytest.mark.parametrize(
    "input",
    [
        {"format": "pom.xml", "manifest": "<project/>"},
        {"format": "uv.lock", "manifest": "not = [toml"},
        {"format": "requirements.txt", "manifest": ""},
        {"format": "requirements.txt", "manifest": "a==1", "limit": 0},
    ],
)
async def test_a_manifest_it_cannot_read_is_invalid(index: str, input: dict[str, object]) -> None:
    with pytest.raises(CallFailed) as failed:
        await packages(index).call("packages.licences.list", context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_an_index_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await packages(f"http://127.0.0.1:{free_port()}").call(
            "packages.licences.list",
            context(),
            {"format": "requirements.txt", "manifest": "httpx==0.28.1"},
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
