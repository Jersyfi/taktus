"""S-05 Guides, end to end: the guides rendered from a repository and put into a knowledge system
by a process of Taktus, with everything outside faked and everything inside real (UC-13.6,
ADR-0065, ADR-0066).

What is real: the bundle as shipped, the run engine, the reference repository connector over
MCP, the loopback connector and the wiring behind it, the knowledge and reporting components.
What is faked: the repository hosting service (`tests/fakes/repository_service.py`), which holds
the repository's own guides manifest and every file it names, copied from this checkout; the
knowledge system (`tests/fakes/knowledge_system.py`); and the owner's chat, which records what it
was told (`tests/fakes/owner_channel.py`).

What is proven: a first run writes every page, each naming the commit; a change merged into
the repository that alters one page is written to that page and no other at the next run, and
the page names the new commit; a page edited by hand is kept, and its difference reaches the
person responsible for the documentation once, however many runs find it; a page whose sources
changed under an edit is shown out of date on its guide's contents page; every step writes its
ledger entries, and the report names how many pages were created, updated, kept and withheld;
and switching the process off leaves the repository's documentation as it was, because nothing
the process does writes there.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fakes import FakeIdentifiers
from fakes.knowledge_system import FakeKnowledgeSystem
from fakes.maturity import VERIFIED
from fakes.owner_channel import OwnerChannel, owner_channel

from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.knowledge.domain.model import Mark
from taktus.components.process.application.service.deactivate import (
    DEACTIVATED,
    DeactivateProcess,
    DeactivateProcessHandler,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.guides import InstanceGuides
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, Plan, ReplyTo

from .conftest import Service

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "blueprints" / "self-operation" / "processes" / "S-05-guides.yaml"
MANIFEST = "docs/guides/guides.yaml"
REPOSITORY = "acme/product"
TENANT = "t"
PERSON = "idn_owner"
ASKING = ("Taktus", "Using Taktus", "Asking Taktus for something")
PEOPLE = ("Taktus", "Using Taktus", "What Taktus never does with people")
CONTENTS = ("Taktus", "Using Taktus", "Contents")

type Json = dict[str, Any]


def bundle() -> Json:
    with BUNDLE.open(encoding="utf-8") as handle:
        loaded: Json = yaml.safe_load(handle)
    return loaded


def repository_files() -> dict[str, str]:
    """The manifest and every file it names, as this checkout holds them."""
    manifest = yaml.safe_load((ROOT / MANIFEST).read_text(encoding="utf-8"))
    paths = {MANIFEST} | {
        part["file"]
        for guide in manifest["guides"]
        for page in guide["pages"]
        for part in page["parts"]
    }
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in sorted(paths)}


class Hosted:
    """The repository on the fake service: a push to `main` is a merge."""

    def __init__(self, service: Service) -> None:
        self._service = service
        self._repo = f"/repos/{REPOSITORY}"

    def _send(self, method: str, path: str, body: Json | None = None) -> Json:
        answer = httpx.request(
            method,
            f"{self._service.url}{self._repo}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self._service.write_value}"},
            timeout=5.0,
        )
        answer.raise_for_status()
        result: Json = answer.json()
        return result

    def head(self) -> str:
        return str(self._send("GET", "/git/ref/heads/main")["object"]["sha"])

    def merge(self, files: dict[str, str]) -> str:
        head = self.head()
        tree = self._send("GET", f"/git/commits/{head}")["tree"]["sha"]
        entries = [
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": self._send("POST", "/git/blobs", {"content": content})["sha"],
            }
            for path, content in files.items()
        ]
        made = self._send("POST", "/git/trees", {"base_tree": tree, "tree": entries})
        commit = self._send(
            "POST", "/git/commits", {"message": "merge", "tree": made["sha"], "parents": [head]}
        )
        self._send("PATCH", "/git/refs/heads/main", {"sha": commit["sha"]})
        return str(commit["sha"])

    def read(self, path: str) -> str | None:
        answer = httpx.get(
            f"{self._service.url}{self._repo}/contents/{path}",
            params={"ref": "main"},
            headers={"Authorization": f"Bearer {self._service.write_value}"},
            timeout=5.0,
        )
        if answer.status_code == 404:
            return None
        answer.raise_for_status()

        return base64.b64decode(answer.json()["content"]).decode("utf-8")


class World:
    """One instance of Taktus over memory, with S-05 registered for the owner channel's tenant."""

    def __init__(self, service: Service, given: OwnerChannel) -> None:
        self.given = given
        self.hosted = Hosted(service)
        self.knowledge = FakeKnowledgeSystem()
        persistence = given.persistence
        ledger = given.identity.ledger
        clock = given.clock
        ids = FakeIdentifiers()
        loopback = LoopbackConnector()
        config = Config(target=service.url, repository=REPOSITORY, timeout=5.0)
        connectors = StaticConnectorPool(
            [
                ("connector.repo", McpActionConnector(build_server(config), timeout=5.0)),
                ("connector.knowledge", self.knowledge),
                (LOOPBACK, loopback),
            ]
        )
        loopback.bind(
            guides=InstanceGuides(connectors, given.owner.channel, given.owner.raising, clock)
        )
        self.runs = MemoryRepository(persistence, Run)
        self.objects = MemoryObjectStore()
        self.engine = RunEngine(
            runs=self.runs,
            work=persistence,
            objects=self.objects,
            ledger=ledger,
            provenance=MemoryProvenanceStore(persistence),
            workers=StaticWorkerPool([]),
            clock=clock,
            ids=ids,
            telemetry=NoTelemetry(),
            maturities=VERIFIED,
            connectors=connectors,
        )
        processes = MemoryRepository(persistence, Process)
        self.processes = processes
        self.register = RegisterProcessVersionHandler(
            MemoryRepository(persistence, ProcessVersion),
            persistence,
            processes,
            ledger=ledger,
            clock=clock,
        )
        self.commission = CommissionPlanHandler(
            MemoryRepository(persistence, Command),
            MemoryRepository(persistence, Plan),
            persistence,
            clock,
            ids,
        )
        self.deactivate = DeactivateProcessHandler(processes, persistence, ledger)
        self.ids = ids
        self.version: ProcessVersion | None = None

    async def run(self) -> Run:
        """One run of S-05 as its daily trigger starts it: with the trigger's inputs."""
        if self.version is None:
            self.version = await self.register.execute(
                RegisterProcessVersion(bundle(), tenant=TENANT, by=PERSON)
            )
        version = self.version
        (trigger,) = version.triggers
        plan = await self.commission.execute(
            CommissionPlan(
                command=Command(
                    id=self.ids.new("cmd"),
                    channel="channel.schedule",
                    identity=PERSON,
                    org_path=(TENANT,),
                    intent=Intent(raw=f"run {version.ref} on schedule", recognised="process.run"),
                    reply_to=ReplyTo(channel="channel.schedule", address=version.ref),
                    received_at=self.given.clock.now(),
                ),
                tenant=TENANT,
                goal=f"run {version.ref}",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=PERSON,
                tenant=TENANT,
                inputs=dict(trigger.inputs or {}),
            )
        )

    def page(self, place: tuple[str, ...]) -> str:
        return self.knowledge.pages[place].body

    def commit_of(self, place: tuple[str, ...]) -> str:
        mark = Mark.decode(self.knowledge.pages[place].mark)
        assert mark is not None, place
        return mark.commit

    async def result(self, run: Run, step: str) -> Any:
        checkpoint = run.step_run(step).checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None, step
        return json.loads(await self.objects.get(checkpoint.result_digest) or b"null")

    async def report(self, run: Run) -> str:
        line = await self.result(run, "report")
        assert isinstance(line, str), line
        return line

    async def entries(self, run: Run) -> list[Any]:
        async with self.given.persistence.transaction(TENANT):
            return list(await self.given.identity.ledger.entries(TENANT, run.id))


@pytest.fixture
def world(service: Service, credentials: None) -> World:
    w = World(service, owner_channel())
    w.hosted.merge(repository_files())
    return w


async def test_the_guides_are_published_every_page_naming_its_commit(world: World) -> None:
    await world.given.configure(roles=["owner", "documentation"])
    head = world.hosted.head()

    run = await world.run()

    assert run.state is RunState.FINISHED, [(s.step_id, s.state, s.reason) for s in run.step_runs]
    pages = world.knowledge.pages
    assert len(pages) == 10, sorted(pages)  # eight pages and two contents pages
    for place in pages:
        assert world.commit_of(place) == head
        assert f"commit `{head}`" in world.page(place)
    assert (await world.report(run)).startswith(
        f"Guides at {head}: 10 pages created, 0 updated, 0 kept, 0 withheld."
    )

    # Every step wrote its ledger entries; the publication is an egress record per page.
    entries = await world.entries(run)
    finished = [e.refs.step_id for e in entries if e.kind == "step.finished"]
    assert world.version is not None
    assert finished == [s.id for s in world.version.ordered()]
    (egress,) = [e for e in entries if e.kind.startswith("egress.")]
    assert egress.kind == "egress.write" and egress.refs.step_id == "publish"
    assert egress.outcome == "acted"
    assert run.step_run("read-sources").state is StepState.SUCCEEDED
    # Read at one commit: the sources were read at the commit the manifest was read at.
    sources = await world.result(run, "read-sources")
    assert isinstance(sources, dict) and sources["output"]["commit"] == head

    # The next run with nothing changed writes nothing.
    again = await world.run()
    assert again.state is RunState.FINISHED
    assert (await world.report(again)).startswith(
        f"Guides at {head}: 0 pages created, 0 updated, 10 kept"
    )
    (quiet,) = [e for e in await world.entries(again) if e.kind.startswith("egress.")]
    assert quiet.outcome == "replayed", "a publication that wrote nothing acted on nothing"


async def test_a_merged_change_reaches_its_page_and_no_other(world: World) -> None:
    await world.given.configure(roles=["owner", "documentation"])
    first = await world.run()
    assert first.state is RunState.FINISHED
    before = {place: stored.body for place, stored in world.knowledge.pages.items()}

    asking = "docs/guides/use/asking.md"
    changed = repository_files()[asking].rstrip("\n") + "\n\nA sentence the merge added.\n"
    merged = world.hosted.merge({asking: changed})

    run = await world.run()

    assert run.state is RunState.FINISHED
    assert "A sentence the merge added." in world.page(ASKING)
    assert world.commit_of(ASKING) == merged
    rewritten = [p for p, s in world.knowledge.pages.items() if s.body != before[p]]
    assert rewritten == [ASKING], rewritten
    assert (await world.report(run)).startswith(
        f"Guides at {merged}: 0 pages created, 1 updated, 9 kept"
    )


async def test_a_hand_edit_is_kept_and_its_difference_reaches_the_person_responsible(
    world: World,
) -> None:
    await world.given.configure(roles=["owner", "documentation"])
    assert (await world.run()).state is RunState.FINISHED
    world.knowledge.edit(PEOPLE, lambda body: body.replace("# What Taktus", "# What Taktus truly"))
    edited = world.page(PEOPLE)

    run = await world.run()

    assert run.state is RunState.FINISHED, [(s.step_id, s.state, s.reason) for s in run.step_runs]
    assert world.page(PEOPLE) == edited, "the person's text stands"
    assert (await world.report(run)).startswith("Guides at ")
    assert "1 withheld" in (await world.report(run))
    (said,) = world.given.deliveries.said
    assert "What Taktus truly" in said.text, "the difference is in the message"
    reports = await world.given.owner.queries.reports(TENANT)
    (report,) = reports
    assert report.kind is ReportKind.NEED and report.id.startswith("guides-use-people-")
    assert "edited by hand" in world.page(CONTENTS)

    # The next run finds the same edit: it is kept, and nobody is told twice.
    again = await world.run()
    assert again.state is RunState.FINISHED
    assert world.page(PEOPLE) == edited
    assert len(world.given.deliveries.said) == 1


async def test_a_page_whose_sources_changed_under_an_edit_is_shown_out_of_date(
    world: World,
) -> None:
    await world.given.configure(roles=["owner", "documentation"])
    assert (await world.run()).state is RunState.FINISHED
    world.knowledge.edit(ASKING, lambda body: body + "\nA note a reader added.\n")
    asking = "docs/guides/use/asking.md"
    world.hosted.merge({asking: repository_files()[asking] + "\nMerged after the edit.\n"})

    run = await world.run()

    assert run.state is RunState.FINISHED
    assert "Merged after the edit." not in world.page(ASKING)
    contents = world.page(CONTENTS)
    line = next(line for line in contents.splitlines() if "Asking Taktus" in line)
    assert "out of date" in line, contents


async def test_an_edit_nobody_can_be_told_of_stops_the_run_at_its_report(world: World) -> None:
    """A tenant whose channel carries no role for the documentation cannot be told: the run
    does not drop the edit silently, it stops at the step that would have told."""
    await world.given.configure()  # the role `owner` alone
    assert (await world.run()).state is RunState.FINISHED
    world.knowledge.edit(PEOPLE, lambda body: body + "\nmine\n")

    run = await world.run()

    assert run.state is not RunState.FINISHED
    step = run.step_run("report-edits")
    assert step.state is StepState.FAILED and "documentation" in (step.reason or "")
    assert world.page(PEOPLE).endswith("\nmine\n")


async def test_switching_the_process_off_leaves_the_repository_s_documentation_complete(
    world: World,
) -> None:
    await world.given.configure(roles=["owner", "documentation"])
    docs = {path: text for path, text in repository_files().items() if path.startswith("docs/")}
    head = world.hosted.head()
    assert (await world.run()).state is RunState.FINISHED
    assert world.version is not None

    done = await world.deactivate.execute(
        DeactivateProcess(tenant=TENANT, process_id=world.version.process_id, by=PERSON)
    )

    assert done.was == world.version.ref and done.process.active_version is None
    assert world.hosted.head() == head, "nothing was committed to the repository"
    for path, text in docs.items():
        assert world.hosted.read(path) == text, path
    async with world.given.persistence.transaction(TENANT):
        kinds = [e.kind for e in await world.given.identity.ledger.entries(TENANT)]
    assert DEACTIVATED in kinds
    again = await world.deactivate.execute(
        DeactivateProcess(tenant=TENANT, process_id=world.version.process_id, by=PERSON)
    )
    assert again.was is None, "switching off what is off changes nothing"
