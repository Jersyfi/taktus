"""The cloud billing connector reads an account's cost per day, signed with the requesting
identity's key pair, with every amount as the provider's decimal text and each day's total as
their exact sum (ADR-0150, issue #447).

Against the fake under `tests/fakes/cloud_billing_service.py`, in a thread of this process. It
recomputes every request's signature, so a request that reaches an answer was signed right. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes import cloud_billing_service
from fakes.ports import free_port
from taktus_connectors.aws.operations import Config
from taktus_connectors.aws.server import build_server
from taktus_connectors.aws.signing import Key

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

KEY_ID = "key-" + secrets.token_hex(6)
SIGNING = "sig-" + secrets.token_hex(12)
OPERATION = "billing.costs.daily"


def use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    path = tmp_path / "billing_key"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_BILLING_KEY_FILE", str(path))


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use(tmp_path, monkeypatch, f"{KEY_ID}:{SIGNING}")


def serve(page_days: int) -> Iterator[str]:
    server = cloud_billing_service.make_server("127.0.0.1", 0, {KEY_ID: SIGNING}, page_days)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def provider() -> Iterator[str]:
    yield from serve(10)


@pytest.fixture
def paged() -> Iterator[str]:
    yield from serve(2)


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name="BILLING_KEY", injected_as="env"),),
    )


def billing(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


async def test_each_day_is_read_by_service_with_its_exact_total(provider: str) -> None:
    result = await billing(provider).call(OPERATION, context(), {"days": 3, "end": "2026-10-01"})
    assert result.effect.kind.value == "read"
    output = result.output
    assert output["currency"] == "USD"
    assert (output["group_by"], output["metric"], output["complete"]) == (
        "service",
        "unblended",
        True,
    )
    assert [d["date"] for d in output["days"]] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert output["days"][0] == {
        "date": "2026-09-28",
        "estimated": False,
        "total": "13.6310",
        "groups": [
            {"group": "Compute", "amount": "12.00"},
            {"group": "Functions", "amount": "1.20"},
            {"group": "Storage", "amount": "0.4310"},
        ],
    }
    assert output["days"][-1]["estimated"] is True, "the provider has not closed the last day"
    assert result.consumption.quota_units == 1


async def test_an_amount_keeps_every_digit_the_provider_gave(provider: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{provider}/_fake/costs",
            content=json.dumps(
                {"2026-09-30": {"Compute": "0.1", "Storage": "0.2", "Functions": "0"}}
            ),
        )
    result = await billing(provider).call(OPERATION, context(), {"days": 1, "end": "2026-10-01"})
    (day,) = result.output["days"]
    assert day["total"] == "0.3", "decimal arithmetic: 0.1 + 0.2 is 0.3, not 0.30000000000000004"


async def test_by_account_a_day_is_one_group(provider: str) -> None:
    result = await billing(provider).call(
        OPERATION, context(), {"days": 1, "end": "2026-10-01", "group_by": "account"}
    )
    (day,) = result.output["days"]
    assert day["groups"] == [{"group": "000000000000", "amount": "13.6310"}]


async def test_every_page_is_read_and_counted(paged: str) -> None:
    result = await billing(paged).call(OPERATION, context(), {"days": 5, "end": "2026-10-01"})
    assert len(result.output["days"]) == 5
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 3


@pytest.mark.parametrize(
    "input",
    [
        {"days": 0},
        {"days": 93},
        {"end": "yesterday"},
        {"group_by": "team"},
        {"metric": "blended"},
        {"days": 3, "end": "2019-06-01"},  # refused by the provider
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    provider: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await billing(provider).call(OPERATION, context(), input)
    assert failed.value.error.cause.value == "invalid"


@pytest.mark.parametrize(
    "value",
    [
        f"{KEY_ID}:sig-not-the-one",  # a signature the provider recomputes differently
        f"key-unknown:{SIGNING}",  # a key id the provider does not know
        "only-one-part",  # not a key pair at all
    ],
    ids=["wrong-signature", "unknown-key", "not-a-pair"],
)
async def test_a_key_the_provider_does_not_admit_is_unauthenticated(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    use(tmp_path, monkeypatch, value)
    with pytest.raises(CallFailed) as failed:
        await billing(provider).call(OPERATION, context(), {"days": 1})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_the_secret_half_never_leaves_the_connector(provider: str) -> None:
    await billing(provider).call(OPERATION, context(), {"days": 1, "end": "2026-10-01"})
    async with httpx.AsyncClient() as client:
        state = (await client.get(f"{provider}/_fake/state")).json()
    assert state["seen_keys"] == [KEY_ID]
    assert SIGNING not in repr(Key.parse(f"{KEY_ID}:{SIGNING}"))


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await billing(f"http://127.0.0.1:{free_port()}").call(OPERATION, context(), {"days": 1})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
