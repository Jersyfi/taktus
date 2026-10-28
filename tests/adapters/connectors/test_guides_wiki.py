"""S-05 Guides into the wiki, and the removal test of the wiki's connector (issue #197).

The process as shipped, the run engine, the reference repository connector and the wiki
connector over MCP, the loopback connector and the wiring behind it — everything inside real,
the repository hosting service and the wiki faked (`tests/fakes/repository_service.py`,
`tests/fakes/wiki_service.py`).

What is proven: through the wiki connector the guides reach the wiki, every page created once,
and the next run keeps every page although the wiki changed every text it stored. With the
connector removed, no process breaks: the guides go to the directory the instance serves where
one is configured, and nowhere otherwise — the run then stops at the step that reads the
knowledge system and hands it to a person, as the step's fallback says.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes.owner_channel import owner_channel

from taktus.adapters.driven.connectors.bookstack.server import Config, build_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.guides import served_directory
from taktus.ports.connector import ActionConnector

from .conftest import Service, Wiki
from .test_guides_process import World, repository_files

PAGES = 13  # eleven pages and two contents pages


def world(service: Service, knowledge: list[tuple[str, ActionConnector]]) -> World:
    w = World(service, owner_channel(), knowledge)
    w.hosted.merge(repository_files())
    return w


def markdown_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.md"))


def wiki_connector(wiki: Wiki) -> list[tuple[str, ActionConnector]]:
    server = build_server(Config(target=wiki.url, timeout=5.0))
    return [("connector.knowledge", McpActionConnector(server, timeout=10.0))]


@pytest.mark.usefixtures("credentials", "wiki_credentials")
async def test_the_guides_reach_the_wiki_and_stay_its_text(service: Service, wiki: Wiki) -> None:
    w = world(service, wiki_connector(wiki))
    await w.given.configure(roles=["owner", "documentation"])
    head = w.hosted.head()

    run = await w.run()

    assert run.state is RunState.FINISHED, [(s.step_id, s.state, s.reason) for s in run.step_runs]
    assert (await w.report(run)).startswith(
        f"Guides at {head}: {PAGES} pages created, 0 updated, 0 kept, 0 withheld."
    )
    books = {
        b: n for b, n in wiki.state()["pages"].items() if b in {"Administration", "Using Taktus"}
    }
    assert books == {"Administration": 7, "Using Taktus": 6}
    for page in wiki.pages():
        if page["name"] == "Contents":
            assert f"commit `{head}`" in page["markdown"]

    again = await w.run()
    assert again.state is RunState.FINISHED
    assert (await w.report(again)).startswith(
        f"Guides at {head}: 0 pages created, 0 updated, {PAGES} kept, 0 withheld."
    ), "the wiki changed every text it stored, and no page looks edited by hand"


@pytest.mark.usefixtures("credentials", "wiki_credentials")
async def test_with_the_wiki_removed_the_guides_go_to_the_configured_directory(
    service: Service, wiki: Wiki, tmp_path: Path
) -> None:
    w = world(service, served_directory(tmp_path))

    run = await w.run()

    assert run.state is RunState.FINISHED, [(s.step_id, s.state, s.reason) for s in run.step_runs]
    files = markdown_files(tmp_path)
    assert len(files) == PAGES
    assert {f.parent.name for f in files} == {"Administration", "Using Taktus"}
    assert wiki.state()["requests"] == 0, "nothing reached the wiki"


@pytest.mark.usefixtures("credentials", "wiki_credentials")
async def test_with_no_knowledge_system_the_guides_go_nowhere_and_a_person_is_asked(
    service: Service, wiki: Wiki
) -> None:
    w = world(service, [])

    run = await w.run()

    assert run.state is RunState.ESCALATED, "handed to a person, not broken"
    held = run.step_run("read-held")
    assert held.state is StepState.FAILED
    assert "no configured connector serves 'knowledge.pages'" in (held.reason or "")
    assert run.step_run("publish").state is StepState.PLANNED, "nothing was published"
    assert run.step_run("render").state is StepState.SUCCEEDED, "the guides still render"
    assert wiki.state()["requests"] == 0
