"""The cloud operations connector reads log entries, daily costs and the metadata of secrets of
one project; it never reads a secret's value, never copies a person, sums every amount exactly,
exchanges a service account key at its own token endpoint, and maps the provider's refusals to
the contract's causes.

Against the fake under `tests/fakes/cloud_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import cloud_service
from fakes.ports import free_port
from taktus_connectors.gcp.api import Config
from taktus_connectors.gcp.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "CLOUD_TOKEN"
ACCOUNT = "reader@example.iam.gserviceaccount.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use(tmp_path, monkeypatch, TOKEN)


def use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    path = tmp_path / "cloud"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


def _serve(**options: Any) -> Iterator[str]:
    numbers = KEY.public_key().public_numbers()
    server = cloud_service.make_server(
        "127.0.0.1", 0, {TOKEN}, service_accounts={ACCOUNT: (numbers.n, numbers.e)}, **options
    )
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def cloud() -> Iterator[str]:
    yield from _serve()


@pytest.fixture
def busy() -> Iterator[str]:
    """More entries, rows and secrets than one page holds, and a query that is slow to finish."""
    yield from _serve(logs=250, secret_count=150, pending=2, page_rows=7)


@pytest.fixture
def stuck() -> Iterator[str]:
    """A query that does not finish within the connector's bound."""
    yield from _serve(pending=10)


def state(url: str) -> dict[str, Any]:
    with urlopen(f"{url}/_fake/state") as response:  # noqa: S310 - the fake's own address
        answer: dict[str, Any] = json.load(response)
        return answer


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


def connector(
    url: str, project: str = "example", table: str = cloud_service.TABLE
) -> McpActionConnector:
    return McpActionConnector(build_server(Config.at(project, table, 5.0, url)))


# logs.query.entries


async def test_log_entries_are_read_newest_first_without_a_person(cloud: str) -> None:
    result = await connector(cloud).call(
        "logs.query.entries", context(), {"filter": "severity>=DEFAULT", "since_minutes": 60}
    )
    assert result.effect.kind.value == "read"
    output = result.output
    entries = output["entries"]
    assert [e["id"] for e in entries] == ["entry00000", "entry00001", "entry00002", "entry00003"]
    assert [e["message"] for e in entries] == [
        "request 0 failed",
        "slow response 1",
        '{"event":"restart","attempt":2}',
        "google.iam.admin.v1.CreateServiceAccountKey",
    ]
    assert entries[0]["severity"] == "ERROR"
    assert entries[0]["source"] == "projects/example/logs/app"
    assert entries[0]["timestamp"].endswith("Z")
    assert set(entries[0]) == {"timestamp", "severity", "message", "source", "id"}
    assert "a.person" not in json.dumps(output), "a principal is never copied (principle 14)"
    assert output["count"] == 4
    assert output["complete"] is True
    assert output["start"] < output["end"]


async def test_log_pages_are_followed_up_to_the_limit(busy: str) -> None:
    every = await connector(busy).call(
        "logs.query.entries", context(), {"filter": "severity>=DEFAULT", "since_minutes": 60}
    )
    assert every.output["count"] == 100
    assert every.output["complete"] is False, "cut by the default limit"

    asked = {"filter": "severity>=DEFAULT", "since_minutes": 60, "limit": 1000}
    all_of_them = await connector(busy).call("logs.query.entries", context(), asked)
    assert all_of_them.output["count"] == 250
    assert all_of_them.output["complete"] is True
    stamps = [e["timestamp"] for e in all_of_them.output["entries"]]
    assert stamps == sorted(stamps, reverse=True)


async def test_the_window_bounds_the_entries(cloud: str) -> None:
    result = await connector(cloud).call(
        "logs.query.entries",
        context(),
        {
            "filter": "severity>=DEFAULT",
            "start": "2020-01-01T00:00:00Z",
            "end": "2020-01-02T00:00:00Z",
        },
    )
    assert result.output["entries"] == []
    assert result.output["start"] == "2020-01-01T00:00:00Z"
    assert result.output["complete"] is True


# billing.costs.daily


async def test_costs_are_summed_exactly_per_day(cloud: str) -> None:
    result = await connector(cloud).call(
        "billing.costs.daily", context(), {"days": 3, "end": "2026-10-04"}
    )
    output = result.output
    assert output["currency"] == "EUR"
    assert output["group_by"] == "service"
    assert output["metric"] == "unblended"
    assert [d["date"] for d in output["days"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    first = output["days"][0]
    assert first["groups"] == [
        {"group": "BigQuery", "amount": "0.000002"},
        {"group": "Cloud Storage", "amount": "0.4"},
        {"group": "Compute Engine", "amount": "0.2"},
    ]
    assert first["total"] == "0.600002"
    assert first["estimated"] is False
    for day in output["days"]:
        assert Decimal(day["total"]) == sum(Decimal(g["amount"]) for g in day["groups"])
    assert output["complete"] is True


async def test_net_costs_carry_the_credits_and_group_by_project(cloud: str) -> None:
    result = await connector(cloud).call(
        "billing.costs.daily",
        context(),
        {"days": 1, "end": "2026-10-02", "metric": "net_unblended", "group_by": "account"},
    )
    day = result.output["days"][0]
    assert day["groups"] == [
        {"group": "", "amount": "0.000002"},
        {"group": "example", "amount": "0.15"},
        {"group": "example-data", "amount": "0.4"},
    ]
    assert day["total"] == "0.550002"


async def test_an_unfinished_query_is_awaited_and_its_pages_read(busy: str) -> None:
    result = await connector(busy).call(
        "billing.costs.daily", context(), {"days": 5, "end": "2026-10-06", "group_by": "region"}
    )
    assert len(result.output["days"]) == 5
    assert all(len(d["groups"]) == 3 for d in result.output["days"])
    assert result.output["complete"] is True
    paths = state(busy)["paths"]
    assert sum(p.endswith("/queries") for p in paths) == 1
    assert sum("/queries/job_" in p for p in paths) == 2 + 2, "two waits, then pages two and three"


async def test_a_query_that_does_not_finish_is_unavailable(stuck: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(stuck).call("billing.costs.daily", context(), {"days": 1})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


async def test_the_dates_are_parameters_never_query_text(cloud: str) -> None:
    from taktus_connectors.gcp.billing import statement

    text = statement(cloud_service.TABLE, "service", "unblended")
    assert "@start" in text and "@end" in text
    assert "2026" not in text


@pytest.mark.parametrize(
    "input",
    [
        {"metric": "amortized"},
        {"metric": "blended"},
        {"group_by": "person"},
        {"days": 0},
        {"days": 93},
        {"end": "yesterday"},
    ],
)
async def test_a_cost_call_that_cannot_be_answered_is_invalid(
    cloud: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(cloud).call("billing.costs.daily", context(), input)
    assert failed.value.error.cause.value == "invalid"


@pytest.mark.parametrize("table", ["", "not a table", "a.b.c`; DROP", "example-billing.x.missing"])
async def test_costs_without_a_usable_table_are_invalid(cloud: str, table: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(cloud, table=table).call("billing.costs.daily", context(), {"days": 1})
    assert failed.value.error.cause.value == "invalid"


# secrets.metadata.list


async def test_secrets_are_listed_oldest_change_first_without_a_value(cloud: str) -> None:
    result = await connector(cloud).call("secrets.metadata.list", context(), {})
    output = result.output
    names = [s["name"] for s in output["secrets"]]
    assert names == ["api-key", "db-password", "tls-cert"]
    key, password, cert = output["secrets"]
    assert key["rotation"] == {
        "automatic": True,
        "period_days": None,
        "next_at": "2026-12-01T00:00:00Z",
    }
    assert password["changed_at"] == "2026-06-01T08:00:00.123456Z", "the newest enabled version"
    assert password["created_at"] == "2026-01-10T00:00:00Z"
    assert password["rotation"]["automatic"] is False
    assert isinstance(password["age_days"], int) and password["age_days"] < key["age_days"]
    assert cert["changed_at"] is None and cert["age_days"] is None, "no version is enabled"
    assert cert["expires_at"] == "2027-01-01T00:00:00Z"
    assert all(s["last_accessed_at"] is None for s in output["secrets"])
    assert output["complete"] is True
    assert output["read_at"].endswith("Z")
    fake = state(cloud)
    assert not any(p.endswith(":access") for p in fake["paths"]), "a value is never asked"
    assert "the-secret-value" not in json.dumps(output)


async def test_a_prefix_keeps_only_names_that_start_with_it(cloud: str) -> None:
    result = await connector(cloud).call("secrets.metadata.list", context(), {"prefix": "db"})
    assert [s["name"] for s in result.output["secrets"]] == ["db-password"]


async def test_secret_pages_are_followed_up_to_the_limit(busy: str) -> None:
    bounded = await connector(busy).call("secrets.metadata.list", context(), {"limit": 120})
    assert len(bounded.output["secrets"]) == 120
    assert bounded.output["complete"] is False
    every = await connector(busy).call("secrets.metadata.list", context(), {"limit": 500})
    assert len(every.output["secrets"]) == 150
    assert every.output["complete"] is True
    assert not any(p.endswith(":access") for p in state(busy)["paths"])


@pytest.mark.parametrize("input", [{"prefix": "a b"}, {"prefix": "x)"}, {"limit": 501}])
async def test_a_secret_call_that_cannot_be_answered_is_invalid(
    cloud: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(cloud).call("secrets.metadata.list", context(), input)
    assert failed.value.error.cause.value == "invalid"


# The service account key.


def _key_document(token_uri: str = "https://elsewhere.example/token") -> str:  # noqa: S107
    pem = KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "example",
            "private_key_id": "k1",
            "private_key": pem,
            "client_email": ACCOUNT,
            "token_uri": token_uri,
        }
    )


async def test_a_service_account_key_is_exchanged_at_the_configured_endpoint(
    cloud: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(tmp_path, monkeypatch, _key_document())
    logs = await connector(cloud).call("logs.query.entries", context(), {"filter": "x"})
    assert logs.output["count"] == 4
    assert logs.consumption.quota_units == 2, "the exchange counts as a request"
    found = await connector(cloud).call("secrets.metadata.list", context(), {})
    assert len(found.output["secrets"]) == 3
    fake = state(cloud)
    assert fake["paths"].count("/token") == 2
    first, second = fake["assertions"]
    assert first["header"] == {"alg": "RS256", "typ": "JWT", "kid": "k1"}
    assert first["claims"]["iss"] == ACCOUNT
    assert first["claims"]["aud"] == f"{cloud}/token", "never the key's own token_uri"
    assert first["claims"]["exp"] - first["claims"]["iat"] == 3600
    assert first["claims"]["scope"] == "https://www.googleapis.com/auth/cloud-platform.read-only"
    assert second["claims"]["scope"] == "https://www.googleapis.com/auth/cloud-platform"
    assert not any(t.startswith("{") for t in fake["seen_tokens"]), "the key is never sent"


async def test_a_key_the_endpoint_refuses_is_unauthenticated(
    cloud: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    document = json.loads(_key_document())
    document["private_key"] = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    use(tmp_path, monkeypatch, json.dumps(document))
    with pytest.raises(CallFailed) as failed:
        await connector(cloud).call("logs.query.entries", context(), {"filter": "x"})
    assert failed.value.error.cause.value == "unauthenticated"


@pytest.mark.parametrize("value", ['{"type": "authorized_user"}', "{not json"])
async def test_a_key_document_that_is_no_service_account_is_unauthenticated(
    cloud: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    use(tmp_path, monkeypatch, value)
    with pytest.raises(CallFailed) as failed:
        await connector(cloud).call("logs.query.entries", context(), {"filter": "x"})
    assert failed.value.error.cause.value == "unauthenticated"


# The causes.


@pytest.mark.parametrize(
    "input",
    [
        {"filter": ""},
        {"filter": "x" * 2001},
        {"filter": "(unbalanced"},
        {"filter": "x", "source": "a-log"},
        {"filter": "x", "since_minutes": 0},
        {"filter": "x", "limit": 1001},
        {"filter": "x", "start": "yesterday"},
        {"filter": "x", "start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
        {"filter": "x", "end": "2026-01-01T00:00:00Z"},
    ],
)
async def test_a_log_call_that_cannot_be_answered_is_invalid(
    cloud: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(cloud).call("logs.query.entries", context(), input)
    assert failed.value.error.cause.value == "invalid"


@pytest.mark.parametrize("project", ["elsewhere", "Not A Project"])
async def test_an_unknown_project_is_invalid(cloud: str, project: str) -> None:
    for operation, input in (
        ("logs.query.entries", {"filter": "x"}),
        ("secrets.metadata.list", {}),
        ("billing.costs.daily", {"days": 1}),
    ):
        with pytest.raises(CallFailed) as failed:
            await connector(cloud, project).call(operation, context(), input)
        assert failed.value.error.cause.value == "invalid", operation


async def test_a_token_the_provider_does_not_admit_is_unauthenticated(
    cloud: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(tmp_path, monkeypatch, "not-the-token")
    for operation, input in (
        ("logs.query.entries", {"filter": "x"}),
        ("secrets.metadata.list", {}),
        ("billing.costs.daily", {"days": 1}),
    ):
        with pytest.raises(CallFailed) as failed:
            await connector(cloud).call(operation, context(), input)
        assert failed.value.error.cause.value == "unauthenticated", operation


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    url = f"http://127.0.0.1:{free_port()}"
    with pytest.raises(CallFailed) as failed:
        await connector(url).call("logs.query.entries", context(), {"filter": "x"})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
