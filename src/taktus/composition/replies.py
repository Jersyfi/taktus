"""Answering in a channel: the reply operation of the connector that serves it.

A connector whose intake serves a channel may declare the operation `<channel>.reply`
(`contracts/connector/v1` §7): it says a text at a reply address the intake produced. This is
how the identity component's answer to an unknown sender reaches them (ADR-0040). Taktus says
it as itself (ADR-0033): the call carries Taktus's own identity and references the credential
the connector declares for actions, which the connector's runtime holds.

A channel whose connector declares no reply operation, or a delivery that fails, is answered
`False` and logged; the intake's outcome says the sender was not answered. Nothing retries it:
the source system redelivers an event it wants answered, and the idempotency key derived from
the delivery makes a second delivery say it once.
"""

from __future__ import annotations

import structlog

from taktus.components.run.ports import ConnectorPool
from taktus.ports.connector import (
    REPLY_OPERATION,
    CallContext,
    CallFailed,
    ChannelReplies,
    ConnectorError,
    IntakeReplyTo,
)
from taktus.ports.worker import CredentialReference

TAKTUS = "taktus"
"""The identity Taktus acts as on its own behalf (ADR-0033)."""

log = structlog.get_logger("taktusd")


class ConnectorReplies(ChannelReplies):
    def __init__(self, connectors: ConnectorPool) -> None:
        self._connectors = connectors

    async def reply(self, tenant: str, to: IntakeReplyTo, text: str, *, key: str) -> bool:
        operation = REPLY_OPERATION.format(channel=to.channel)
        resolved = await self._connectors.resolve(to.channel)
        if resolved is None or resolved.declaration.operation(operation) is None:
            log.warning("no connector answers in this channel", channel=to.channel)
            return False
        context = CallContext(
            tenant=tenant,
            identity=TAKTUS,
            run_id="intake",
            step_id="reply",
            attempt=1,
            idempotency_key=key,
            credentials=tuple(
                CredentialReference(name=need.name, injected_as="env")
                for need in resolved.declaration.credentials
                if need.purpose == "actions"
            ),
        )
        document = {"address": to.address, "text": text}
        if to.thread is not None:
            document["thread"] = to.thread
        try:
            await resolved.connector.call(operation, context, document)
        except (CallFailed, ConnectorError) as error:
            log.error(
                "the answer to a sender did not reach the channel",
                channel=to.channel,
                adapter=resolved.adapter,
                error=type(error).__name__,
            )
            return False
        return True
