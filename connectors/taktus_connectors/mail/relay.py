"""The relay: every new message in the mailbox reaches the instance's intake, signed.

A mailbox sends nothing; it is read. The relay is the sender a webhook would be. It reads the
inbox over IMAP every `interval` seconds and delivers each message not yet relayed to the intake
address of the channel — `POST <prefix>/intake/channel.mail` of an instance — signed with the
intake secret, exactly as `intake.py` verifies it. The instance hands the delivery to this
connector's intake tool like any webhook delivery.

**What has been relayed is kept in the mailbox.** A message relayed carries the keyword
`$TaktusRelayed`, set once the instance answered. The relay keeps no memory of its own, so a
second relay, or one restarted, reads the same mailbox and relays only what carries no keyword.
A relay stopped after the delivery and before the keyword delivers the message again. That is a
redelivery: the intake keeps one event per message identifier.

What the instance's answer means for the message:

| Answer | The message |
|---|---|
| 2xx: accepted, refused as no event, or answered | relayed: the keyword is set |
| 400: the delivery cannot be read | relayed: it never will be; the log names it |
| 401: the signature does not verify | kept: the relay's secret is not the connector's |
| anything else, or no answer | kept: delivered again at the next pass |

The relay reads the mailbox with the password `MAIL_PASSWORD` and signs with
`MAIL_INTAKE_SECRET`, each from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, at every pass.
Messages are read without being marked read: a person who reads the mailbox too sees what is new.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from dataclasses import dataclass, field

import httpx

from taktus_connectors.mail.declaration import (
    ACTIONS_CREDENTIAL,
    INTAKE_CREDENTIAL,
)
from taktus_connectors.mail.intake import signed
from taktus_connectors.mail.protocol import Config, imap
from taktus_connectors.serving import TargetError, now, secret_named

RELAYED = "$TaktusRelayed"
BATCH = 50
"""The most messages one pass relays; the rest wait for the next."""


@dataclass
class Pass:
    """What one pass did, counted."""

    relayed: int = 0
    kept: int = 0
    notes: list[str] = field(default_factory=list)


def log(message: str) -> None:
    sys.stderr.write(f"{now()} mail-relay {message}\n")
    sys.stderr.flush()


def _pending(config: Config, password: str) -> list[tuple[str, bytes]]:
    with imap(config, password) as session:
        session.select(config.inbox)
        uids = session.search("UNKEYWORD", RELAYED)[:BATCH]
        return [(uid, session.fetch(uid)) for uid in uids]


def _mark(config: Config, password: str, uids: list[str]) -> None:
    if not uids:
        return
    with imap(config, password) as session:
        session.select(config.inbox, readonly=False)
        for uid in uids:
            session.flag(uid, RELAYED)


def delivery(config: Config, uid: str, raw: bytes) -> str:
    """The body the relay delivers: the mailbox, the UID, the message in base64."""
    return json.dumps(
        {
            "mailbox": config.inbox,
            "uid": int(uid),
            "message": base64.b64encode(raw).decode("ascii"),
        },
        separators=(",", ":"),
    )


async def relay_once(
    config: Config,
    intake: str,
    *,
    wait: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> Pass:
    """One pass: read what is new, deliver each, keep what the instance did not take.
    `wait` is how long the instance may take to answer a delivery, in seconds; `client`
    is the HTTP client to deliver with, which a test hands in."""
    done = Pass()
    password = secret_named(ACTIONS_CREDENTIAL)
    secret = secret_named(INTAKE_CREDENTIAL)
    if password is None or secret is None:
        done.notes.append(f"no value under {ACTIONS_CREDENTIAL} or {INTAKE_CREDENTIAL}")
        return done
    try:
        pending = await asyncio.to_thread(_pending, config, password)
    except TargetError as error:
        done.notes.append(f"the mailbox could not be read: {error.cause}")
        return done
    relayed: list[str] = []
    async with client or httpx.AsyncClient(timeout=wait) as http:
        for uid, raw in pending:
            body = delivery(config, uid, raw)
            headers = {"content-type": "application/json", **signed(body, secret)}
            try:
                answer = await http.post(intake, content=body.encode(), headers=headers)
            except httpx.HTTPError as error:
                done.kept += 1
                done.notes.append(f"message {uid}: no answer ({type(error).__name__})")
                continue
            if 200 <= answer.status_code < 300 or answer.status_code == 400:
                relayed.append(uid)
                if answer.status_code == 400:
                    done.notes.append(f"message {uid}: the intake cannot read it")
            else:
                done.kept += 1
                done.notes.append(f"message {uid}: the intake answered {answer.status_code}")
    try:
        await asyncio.to_thread(_mark, config, password, relayed)
    except TargetError as error:
        done.notes.append(f"the keyword could not be set: {error.cause}; relayed again next")
        return done
    done.relayed = len(relayed)
    return done


async def relay(config: Config, intake: str, *, interval: float, once: bool) -> None:
    while True:
        done = await relay_once(config, intake)
        log(f"relayed {done.relayed}, kept {done.kept}")
        for note in done.notes:
            log(note)
        if once:
            return
        await asyncio.sleep(interval)
