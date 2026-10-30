"""What a person may ask Taktus for, and a start of it, on the HTTP surface (UC-1.13,
ADR-0159).

The catalogue lists the processes with an active version the reader may see, each with what it
needs and how to start it on each channel; a start from it is the one start command on
`channel.web`, the same command the command line and a person's own agent issue; a process the
reader may not see is answered as one that does not exist; nothing like a ticket is kept.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx

from taktus.adapters.driven.memory import MemoryRepository
from taktus.adapters.driving.cli.run_command import _command
from taktus.components.command.domain.service.start import RECOGNISED as COMMAND_RECOGNISED
from taktus.components.identity.domain.model import Right
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.reporting.domain.service.catalogue import RECOGNISED
from taktus.shared.v1 import Command

from .conftest import OTHER, TENANT, Services
from .test_agent_surface import agent, call, registered
from .test_process_level import bearer
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]


async def commands(given: Services) -> list[Command]:
    async with given.persistence.transaction(TENANT):
        return await MemoryRepository(given.persistence, Command).list(TENANT)


async def test_the_catalogue_lists_what_the_reader_may_start_and_how_on_each_channel(
    client: Client,
) -> None:
    http, given, base = client
    await registered(given)
    assert is_problem(await http.get(f"{base}/catalogue"), 401)
    _, key = await given.identity.person(TENANT, "idn_ada")
    listed = (await http.get(f"{base}/catalogue", headers=bearer(key))).json()
    (entry,) = listed["entries"]
    assert entry["process"] == "daily" and entry["version"] == "daily@1"
    assert entry["level"] == 3
    assert [(i["name"], i["required"]) for i in entry["needs"]] == [("target", True)]
    assert entry["command"] == {"intent": "run daily@1", "recognised": "process.run"}
    assert entry["start"]["web"] == "/catalogue/daily/start"
    assert entry["start"]["agent"]["tool"] == "start_process"
    assert entry["start"]["agent"]["held"] is False, "no role of hers grants agent.start"
    assert "chat" not in entry["start"], "a reply cannot give the input it needs"
    assert "Needs target" in entry["text"]
    assert listed["summary"] == "You may start 1 process."
    _, elsewhere = await given.identity.person(OTHER, "idn_bob")
    other = (await http.get(f"{base}/catalogue", headers=bearer(elsewhere))).json()
    assert other["entries"] == [], "another tenant's processes are never listed"


async def test_a_start_from_the_web_app_is_the_command_the_cli_and_an_agent_issue(
    client: Client,
) -> None:
    http, given, base = client
    await registered(given)
    key = await agent(given, "idn_ada", "ops")
    await given.identities.grant(TENANT, "ops", Right.START, by="idn_admin")
    account = await given.identities.issue_key(TENANT, "idn_ada")

    missing = await http.post(f"{base}/catalogue/daily/start", json={}, headers=bearer(account))
    assert is_problem(missing, 409) and "target" in missing.json()["detail"]
    started = await http.post(
        f"{base}/catalogue/daily/start", json={"inputs": {"target": "x"}}, headers=bearer(account)
    )
    assert started.status_code == 201, started.text
    run_id = started.json()["run_id"]
    async with given.persistence.transaction(TENANT):
        run = await given.runs.get(TENANT, run_id)
    assert run is not None and run.identity == "idn_ada"

    by_agent = await call(http, base, key, "start_process", process="daily", inputs={"target": "x"})
    assert not by_agent["error"], by_agent
    web, mcp = sorted(await commands(given), key=lambda c: c.channel, reverse=True)
    assert (web.channel, mcp.channel) == ("channel.web", "channel.agent")

    async with given.persistence.transaction(TENANT):
        version = await MemoryRepository(given.persistence, ProcessVersion).get(TENANT, "daily@1")
    assert version is not None
    cli = _command(
        SimpleNamespace(ids=given.ids, clock=given.clock),  # type: ignore[arg-type]
        version,
        SimpleNamespace(identity="idn_ada", org_path=(TENANT, "ops")),  # type: ignore[arg-type]
        {"target": "x"},
    )

    def asked(command: Command) -> tuple[Any, ...]:
        return (command.intent, command.context, command.identity)

    assert asked(web) == asked(mcp) == asked(cli)
    assert web.intent.recognised == RECOGNISED == COMMAND_RECOGNISED


async def test_a_process_the_reader_may_not_see_is_answered_as_one_that_does_not_exist(
    client: Client,
) -> None:
    http, given, base = client
    await registered(given)
    _, elsewhere = await given.identity.person(OTHER, "idn_bob")
    unseen = await http.post(
        f"{base}/catalogue/daily/start", json={"inputs": {"target": "x"}}, headers=bearer(elsewhere)
    )
    _, key = await given.identity.person(TENANT, "idn_ada")
    absent = await http.post(
        f"{base}/catalogue/nothing/start", json={"inputs": {}}, headers=bearer(key)
    )
    assert is_problem(unseen, 404) and is_problem(absent, 404)
    assert unseen.json()["detail"].replace("daily", "x") == absent.json()["detail"].replace(
        "nothing", "x"
    )
    assert await commands(given) == [], "nothing was asked"
