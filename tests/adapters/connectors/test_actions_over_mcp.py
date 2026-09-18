"""The action half of the connector port over MCP, against the reference connector in process.

What the adapter owes the core: a declaration read and validated, a result read and validated,
a classified error raised as `CallFailed` with the connector's own cause, and a `ConnectorError`
for everything the contract does not allow — an unreachable connector, an unclassified error.
"""

from __future__ import annotations

from typing import Any

import pytest

from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Cause,
    ConnectorError,
    Effect,
    Idempotency,
    idempotency_key,
)
from taktus.ports.worker import CredentialReference

from .conftest import READ_CREDENTIAL, WRITE_CREDENTIAL, Service

REPOSITORY = "acme/product"
RUN = "run_0123456789abcdef0123"


def connector(service: Service, **overrides: Any) -> McpActionConnector:
    config = Config(target=service.url, repository=REPOSITORY, timeout=5.0, **overrides)
    return McpActionConnector(build_server(config), timeout=5.0)


def context(step: str, attempt: int = 1, credential: str = WRITE_CREDENTIAL) -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_7f3a2c",
        run_id=RUN,
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key(RUN, step, attempt),
        credentials=(CredentialReference(name=credential, injected_as="env"),),
        autonomy_level=2,
    )


@pytest.mark.usefixtures("credentials")
async def test_the_declaration_is_read_and_bound(service: Service) -> None:
    declaration = await connector(service).capabilities()
    assert declaration.contract == "connector/v1"
    assert "repository.pullrequests" in declaration.capabilities
    open_pr = declaration.operation("repository.pullrequests.open")
    assert open_pr is not None
    assert open_pr.effect is Effect.WRITE and open_pr.idempotency is Idempotency.MARKED
    assert open_pr.outward and open_pr.repeatable
    trigger = declaration.operation("repository.pipelines.trigger")
    assert trigger is not None and not trigger.repeatable
    read = declaration.operation("repository.issues.read")
    assert read is not None and not read.outward


@pytest.mark.usefixtures("credentials")
async def test_a_call_returns_a_result_with_the_declared_effect(service: Service) -> None:
    result = await connector(service).call("repository.issues.read", context("read"), {"number": 1})
    assert result.effect.kind is Effect.READ
    assert result.output["number"] == 1
    assert result.consumption.quota_units == 1


@pytest.mark.usefixtures("credentials")
async def test_an_outward_call_repeated_with_the_same_key_is_replayed(service: Service) -> None:
    input = {"head": "taktus/issue-9", "base": "main", "title": "t", "body": "b"}
    first = await connector(service).call("repository.pullrequests.open", context("pr"), input)
    again = await connector(service).call("repository.pullrequests.open", context("pr"), input)
    assert first.effect.replayed is False and again.effect.replayed is True
    assert again.effect.records == first.effect.records
    assert service.state()[REPOSITORY]["pulls"] == 1


@pytest.mark.usefixtures("credentials")
async def test_a_classified_error_is_raised_with_its_cause(service: Service) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(service).call(
            "repository.issues.create", context("c", credential=READ_CREDENTIAL), {"title": "x"}
        )
    assert failed.value.error.cause is Cause.FORBIDDEN
    assert failed.value.error.effect == "none"
    assert failed.value.error.retryable is False
    with pytest.raises(CallFailed) as missing:
        await connector(service).call("repository.issues.read", context("r"), {"number": 999})
    assert missing.value.error.cause is Cause.NOT_FOUND


@pytest.mark.usefixtures("credentials")
async def test_an_unclassified_error_is_a_broken_contract(service: Service) -> None:
    with pytest.raises(ConnectorError, match="not classified"):
        await connector(service, fault="C-06").call(
            "repository.issues.read", context("r"), {"number": 999}
        )


async def test_an_unreachable_connector_is_a_connector_error() -> None:
    unreachable = McpActionConnector("http://127.0.0.1:9/mcp", timeout=1.0)
    with pytest.raises(ConnectorError, match="did not"):
        await unreachable.capabilities()
    with pytest.raises(ConnectorError, match="did not"):
        await unreachable.call("repository.issues.read", context("r"), {"number": 1})


@pytest.mark.usefixtures("credentials")
async def test_the_pool_resolves_by_capability_and_reads_the_declaration_once(
    service: Service,
) -> None:
    pool = StaticConnectorPool([("connector.repository", connector(service))])
    resolved = await pool.resolve("repository.comments")
    assert resolved is not None
    assert resolved.adapter == "connector.repository"
    assert resolved.declaration.operation("repository.comments.create") is not None
    assert await pool.resolve("chat.threads") is None
    assert (await pool.resolve("repository.issues")) is not None
