"""B-3.02 with the sender's account and the helpdesk record (NTC-0293): the bundle for a case
whose customer is known reads the account and the subscriptions only when the product confirms
the sender is that customer's verified address, each read scoped to the customer; and the reply
that was sent is noted on the case's helpdesk ticket.

The world of `test_software_operations_accounts.py`, with a helpdesk beside it. What is faked:
the mailbox, the payment provider, the product's server, the helpdesk and the model.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import helpdesk_service
from taktus_connectors.zendesk.operations import Config as DeskConfig
from taktus_connectors.zendesk.server import build_server as desk_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.domain.model import RunState

from .test_software_operations import DRAFT, Outside, replying
from .test_software_operations import outside as outside
from .test_software_operations_accounts import SEED, AccountsWorld
from .test_software_operations_accounts import accounts_credential as accounts_credential

PAIR = "agent@product.example:tok-" + secrets.token_hex(8)
REPLY = "Your monthly plan is active; you change it on your account page."


@pytest.fixture
def desk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    path = tmp_path / "HELPDESK_TOKEN"
    path.write_text(PAIR, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_HELPDESK_TOKEN_FILE", str(path))
    server = helpdesk_service.make_server("127.0.0.1", 0, {PAIR})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


class ToolsWorld(AccountsWorld):
    """The accounts world, with a helpdesk."""

    def __init__(self, outside: Outside, desk: str) -> None:
        super().__init__(outside)
        pool = self.engine._connectors
        assert isinstance(pool, StaticConnectorPool)
        helpdesk = desk_server(DeskConfig(desk, timeout=5.0))
        pool._connectors.append(("connector.helpdesk", McpActionConnector(helpdesk, timeout=10.0)))

    async def ready(self) -> ToolsWorld:
        await super().ready()
        return self


def drafted(w: AccountsWorld) -> str:
    prompt = next(p for p in w.model.prompts if (p.system or "").startswith(DRAFT))
    return str(prompt.document() if hasattr(prompt, "document") else prompt)


def comments(desk: str, ticket: int) -> list[dict[str, Any]]:
    state = httpx.get(f"{desk}/_fake/state", timeout=5).json()
    found: list[dict[str, Any]] = next(t for t in state["tickets"] if t["id"] == ticket)["comments"]
    return found


async def test_the_verified_senders_account_and_subscriptions_reach_the_draft(
    outside: Outside,
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.02-draft-reply-account.yaml")
    replying(w, REPLY)
    before = outside.submitted()
    run = await w.confirmed(await w.start(version, message=SEED, customer="cus_fake1"))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "sender-verified"))["output"]["verified"] is True
    shown = drafted(w)
    assert "sub_fake1" in shown and "plan-monthly" in shown
    assert "customer@mail.example" not in shown.split("account, as the product")[1], (
        "the account's address is never read"
    )
    assert w.calls() == {"verify_address": 1, "read_account": 1}
    assert outside.submitted() == before + 1


async def test_a_sender_who_is_not_the_customer_gets_a_reply_without_account_data(
    outside: Outside,
) -> None:
    w = await AccountsWorld(outside).ready()
    version = await w.registered("B-3.02-draft-reply-account.yaml")
    replying(w, "Thank you; a colleague will look at your account.")
    run = await w.confirmed(await w.start(version, message=SEED, customer="cus_fake2"))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "sender-verified"))["output"]["verified"] is False
    for step in ("account", "subscriptions"):
        assert (await w.result(run, step))["skipped"] is True
    shown = drafted(w)
    assert "sub_fake2" not in shown and "plan-monthly" not in shown
    assert w.calls() == {"verify_address": 1}, "nothing of another customer's account was read"


async def test_the_sent_reply_is_noted_on_the_cases_ticket_once(
    outside: Outside, desk: str
) -> None:
    w = await ToolsWorld(outside, desk).ready()
    version = await w.registered("B-3.02-draft-reply.yaml")
    replying(w, REPLY)
    before = len(comments(desk, 1))
    run = await w.confirmed(await w.start(version, message=SEED, ticket="1"))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    added = comments(desk, 1)[before:]
    assert len(added) == 1
    assert REPLY in added[0]["body"] and added[0]["public"] is False


async def test_without_a_ticket_no_helpdesk_is_written(outside: Outside, desk: str) -> None:
    w = await ToolsWorld(outside, desk).ready()
    version = await w.registered("B-3.02-draft-reply.yaml")
    replying(w, REPLY)
    before = len(comments(desk, 1))
    run = await w.confirmed(await w.start(version, message=SEED))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "note-ticket"))["skipped"] is True
    assert len(comments(desk, 1)) == before
