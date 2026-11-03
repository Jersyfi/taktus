"""The one command that starts a process, whatever channel asked for it (UC-1.13, ADR-0159).

A person starts a process from the command line, from a chat, from their own agent or from the
list of what they may ask for in the web app. Each asks for the same thing, so each issues the
same command: the intent `run <process>@<version>`, recognised as `process.run`, with the inputs
as its context. Only the channel, its reply address and who asked differ. Every entry point
builds the command here, so that no channel's start can drift from another's.

Pure: the facts in, the command out.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from taktus.shared.v1 import Command, Intent, ReplyTo

RECOGNISED = "process.run"
"""What every start of a process is recognised as."""


def start_intent(process_version: str) -> Intent:
    """The intent a start of `process_version` carries, on any channel."""
    return Intent(raw=f"run {process_version}", recognised=RECOGNISED)


def start_command(
    *,
    id: str,
    channel: str,
    identity: str,
    org_path: tuple[str, ...],
    process_version: str,
    inputs: Mapping[str, Any],
    reply_to: ReplyTo,
    received_at: datetime,
) -> Command:
    """The command that starts `process_version` with `inputs`, asked by `identity` on
    `channel`. The inputs are its context, the way an issue or a thread is a channel's."""
    given = dict(inputs)
    return Command(
        id=id,
        channel=channel,
        identity=identity,
        org_path=org_path,
        intent=start_intent(process_version),
        context={"inputs": given} if given else None,
        reply_to=reply_to,
        received_at=received_at,
    )
