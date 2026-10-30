"""The one command that starts a process, whatever channel asked (UC-1.13, ADR-0159 §2)."""

from __future__ import annotations

from datetime import UTC, datetime

from taktus.components.command.domain.service.start import start_command
from taktus.shared.v1 import Command, ReplyTo

AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def test_two_channels_issue_the_same_intent_and_context_and_differ_only_in_where() -> None:
    def on(channel: str, inputs: dict[str, str]) -> Command:
        return start_command(
            id=f"cmd_{channel}",
            channel=channel,
            identity="idn_ada",
            org_path=("t",),
            process_version="daily@3",
            inputs=inputs,
            reply_to=ReplyTo(channel=channel, address="ledger"),
            received_at=AT,
        )

    web, chat = on("channel.web", {"a": "1"}), on("channel.chat", {"a": "1"})
    assert web.intent == chat.intent
    assert web.intent.raw == "run daily@3"
    assert web.intent.recognised == "process.run"
    assert web.context == chat.context == {"inputs": {"a": "1"}}
    assert on("channel.cli", {}).context is None
