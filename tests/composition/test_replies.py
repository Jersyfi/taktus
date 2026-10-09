"""Answering a sender in a channel: the reply operation of the channel's connector, called as
Taktus itself with the credential the connector declares for actions (ADR-0040)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from fakes import failure

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.composition.replies import TAKTUS, ConnectorReplies
from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Capabilities,
    Effect,
    EffectReport,
    IntakeReplyTo,
    Record,
    Result,
)
from taktus.shared.v1 import Consumption

TO = IntakeReplyTo(channel="channel.repo", address="acme/product#11", thread="9")
KEY = "taktus:intake:dlv-1:reply"


@dataclass
class Channel:
    """A connector serving `channel.repo`, with or without the reply operation."""

    replies: bool = True
    fails: bool = False
    calls: list[tuple[str, CallContext, Mapping[str, Any]]] = field(default_factory=list)

    async def capabilities(self) -> Capabilities:
        operations = [
            {
                "name": "channel.repo.read",
                "capability": "channel.repo",
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "read",
            }
        ]
        if self.replies:
            operations.append(
                {
                    "name": "channel.repo.reply",
                    "capability": "channel.repo",
                    "effect": "write",
                    "idempotency": "marked",
                    "demand": {"quota_units": 3},
                    "summary": "answer at a reply address",
                }
            )
        return Capabilities.model_validate(
            {
                "contract": "connector/v1",
                "version": "1.0.0",
                "capabilities": ["channel.repo"],
                "operations": operations,
                "credentials": [
                    {"name": "CHANNEL_TOKEN", "purpose": "actions"},
                    {"name": "CHANNEL_SECRET", "purpose": "intake"},
                ],
                "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 3600},
                "permissions": "passthrough",
            }
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        self.calls.append((operation, context, input))
        if self.fails:
            raise CallFailed(operation, failure("unavailable", retryable=True))
        return Result(
            output={},
            effect=EffectReport(
                kind=Effect.WRITE,
                replayed=False,
                records=(Record(kind="comment", id="11#1"),),
                content_digest="sha256:" + "ab" * 32,
            ),
            consumption=Consumption(quota_units=3),
        )


async def test_the_answer_is_said_as_taktus_with_the_connectors_actions_credential() -> None:
    channel = Channel()
    replies = ConnectorReplies(StaticConnectorPool([("connector.repo", channel)]))
    assert await replies.reply("default", TO, "Link it.", key=KEY)
    ((operation, context, input),) = channel.calls
    assert operation == "channel.repo.reply"
    assert input == {"address": "acme/product#11", "thread": "9", "text": "Link it."}
    assert context.identity == TAKTUS and context.tenant == "default"
    assert context.idempotency_key == KEY
    assert [c.name for c in context.credentials] == ["CHANNEL_TOKEN"], "never the intake secret"


async def test_a_channel_that_cannot_answer_is_said_and_not_retried() -> None:
    silent = Channel(replies=False)
    replies = ConnectorReplies(StaticConnectorPool([("connector.repo", silent)]))
    assert not await replies.reply("default", TO, "Link it.", key=KEY)
    assert silent.calls == []

    failing = Channel(fails=True)
    replies = ConnectorReplies(StaticConnectorPool([("connector.repo", failing)]))
    assert not await replies.reply("default", TO, "Link it.", key=KEY)
    assert len(failing.calls) == 1

    nobody = ConnectorReplies(StaticConnectorPool([]))
    assert not await nobody.reply("default", TO, "Link it.", key=KEY)
