"""An unknown sender on the repository channel, end to end against the fake service: the
intake handler of the `command` component, the reference connector's intake and its reply
operation, both over MCP, and the fake repository service the reply lands in (issue #247).

On the installed instance one issue, opened and labelled three times within a second, received
three identical offers to link the account. Here the same deliveries arrive together, and one
offer lands on the issue; a label added alone is answered nothing; after the window a comment is
offered again.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeClock
from fakes.identity import directory

from taktus.adapters.driven.connectors.github.declaration import INTAKE_CREDENTIAL
from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector, McpIntakeConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import ReceiveIntake, ReceiveIntakeHandler
from taktus.components.command.domain.model import IntakeEvent
from taktus.composition.replies import ConnectorReplies
from taktus.ports.connector import CallContext, Delivery
from taktus.ports.worker import CredentialReference

from .conftest import WRITE_CREDENTIAL, Service
from .test_repository_intake import SHARED, recorded, signed

REPOSITORY = "placeholder-owner/placeholder-repo"
RECEIVED = datetime(2026, 10, 11, 17, 17, 30, tzinfo=UTC)
WINDOW = timedelta(hours=1)
TENANT = "default"

type Json = dict[str, Any]


class Instance:
    """The intake as `taktusd` wires it, over memory, with the reference connector in-process
    against the fake service. Nobody is linked: every sender is unknown."""

    def __init__(self, service: Service) -> None:
        server = build_server(Config(target=service.url, repository=REPOSITORY, timeout=5.0))
        self.service = service
        self.clock = FakeClock(RECEIVED)
        self.identity = directory((TENANT,), clock=self.clock)
        self.actions = McpActionConnector(server)
        self.intake = ReceiveIntakeHandler(
            {"channel.repo": McpIntakeConnector(server)},
            MemoryRepository(self.identity.persistence, IntakeEvent),
            self.identity.persistence,
            self.identity.directory,
            replies=ConnectorReplies(StaticConnectorPool([("connector.repo", self.actions)])),
            clock=self.clock,
            offer_window=WINDOW,
        )
        self.deliveries = 0

    async def issue(self) -> int:
        """An issue on the fake service, opened through the connector."""
        context = CallContext(
            tenant=TENANT,
            identity="idn_owner",
            run_id="run_setup",
            step_id="issue",
            attempt=1,
            idempotency_key="taktus:run_setup:issue:1",
            credentials=(CredentialReference(name=WRITE_CREDENTIAL, injected_as="env"),),
        )
        result = await self.actions.call(
            "repository.issues.create", context, {"title": "Pin the model"}
        )
        return int(result.output["number"])

    def delivery(self, name: str, number: int, **changes: Json) -> Delivery:
        """The recorded delivery, about issue `number`, signed, under a delivery id of its own."""
        headers, body = recorded(name)
        payload = json.loads(body)
        payload["issue"]["number"] = number
        for field, change in changes.items():
            payload[field].update(change)
        self.deliveries += 1
        headers = {**headers, "x-github-delivery": f"placeholder-delivery-{self.deliveries}"}
        text = json.dumps(payload)
        return Delivery(headers=signed(headers, text), body=text, received_at=RECEIVED)

    async def deliver(self, *deliveries: Delivery) -> list[bool]:
        """Every delivery at once, as the service sends them; whether each was answered."""
        receive = [
            ReceiveIntake(channel="channel.repo", delivery=d, tenant=TENANT) for d in deliveries
        ]
        outcomes = await asyncio.gather(*(self.intake.execute(r) for r in receive))
        assert all(o.unknown_sender is not None and o.accepted is None for o in outcomes)
        return [o.replied for o in outcomes]

    def offers(self, number: int) -> int:
        """How many comments on the issue offer to link an account."""
        comments = self.service.state()[REPOSITORY]["comments"]
        assert isinstance(comments, int)
        return comments - self.before[number]

    async def opened(self) -> int:
        number = await self.issue()
        self.before = {number: int(self.service.state()[REPOSITORY]["comments"])}
        return number


@pytest.fixture
def instance(service: Service, credentials: None, monkeypatch: pytest.MonkeyPatch) -> Instance:
    monkeypatch.delenv(f"TAKTUS_CREDENTIAL_{INTAKE_CREDENTIAL}_FILE", raising=False)
    monkeypatch.setenv(INTAKE_CREDENTIAL, SHARED)
    return Instance(service)


async def test_an_issue_opened_and_labelled_together_gets_one_offer(instance: Instance) -> None:
    """The install's case: an issue opened, three labels added and a comment written, all
    delivered at once. The labels carry nothing the sender wrote and are not answered; the
    opening and the comment wait for each other, and one offer answers both."""
    number = await instance.opened()
    replied = await instance.deliver(
        instance.delivery("issues-opened", number),
        *(
            instance.delivery("issues-labeled", number, label={"name": label})
            for label in ("task", "ready", "priority:normal")
        ),
        instance.delivery("issue-comment-created", number),
    )
    assert replied.count(True) == 1
    assert not any(replied[1:4]), "a label added is never answered"
    assert instance.offers(number) == 1, "one offer on the issue"


async def test_a_label_added_alone_is_answered_nothing(instance: Instance) -> None:
    number = await instance.opened()
    replied = await instance.deliver(instance.delivery("issues-labeled", number))
    assert replied == [False]
    assert instance.offers(number) == 0


async def test_after_the_window_a_comment_is_offered_again(instance: Instance) -> None:
    number = await instance.opened()
    comment = instance.delivery("issue-comment-created", number)
    assert await instance.deliver(comment) == [True]
    instance.clock.current += WINDOW / 2
    assert await instance.deliver(instance.delivery("issue-comment-created", number)) == [False]
    assert instance.offers(number) == 1, "within the window, nothing more"
    instance.clock.current += WINDOW
    assert await instance.deliver(instance.delivery("issue-comment-created", number)) == [True]
    assert instance.offers(number) == 2, "after it, the person may be offered again"
