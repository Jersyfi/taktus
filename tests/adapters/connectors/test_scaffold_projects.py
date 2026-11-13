"""A project checked against its method scaffold and furnished in the organisation's own systems:
the repository connector against the fake repository service, the knowledge system as the
directory connector (ADR-0307, UC-13.2).

The check reads when each artifact last changed through `repository.files.dates` and names it
present, missing, unmaintained or unread. Furnishing creates exactly what is missing: files as
one pull request a person merges, pages in the knowledge system, and nothing twice on a repeat.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import pytest
from taktus_connectors.github.server import Config, build_server

from taktus.adapters.driven.connectors.directory import DirectoryConnector
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driving.cli.bundle_command import scaffold_of, skill_on_disk
from taktus.components.catalog.application.service.scaffolds import (
    Acting,
    Project,
    ScaffoldProjects,
)
from taktus.components.catalog.domain.model.scaffold import ArtifactState, Scaffold
from taktus.ports.worker import CredentialReference

from .conftest import WRITE_CREDENTIAL, Service

type Json = dict[str, Any]

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = "acme/scaffolded"
PLACE = ("Projects", "Shop")


def development() -> Scaffold:
    scaffold = scaffold_of(skill_on_disk(ROOT / "scaffolds" / "skills" / "development-scaffold"))
    assert scaffold is not None
    return scaffold


def acting(run: str) -> Acting:
    return Acting(
        tenant="default",
        identity="idn_scaffold",
        run_id=run,
        credentials=(CredentialReference(name=WRITE_CREDENTIAL, injected_as="env"),),
    )


def control(service: Service, path: str, body: Json) -> Json:
    answer = httpx.post(
        f"{service.url}{path}",
        json=body,
        headers={"Authorization": f"Bearer {service.write_value}"},
        timeout=5.0,
    )
    answer.raise_for_status()
    result: Json = answer.json()
    return result


def project_branch(service: Service) -> str:
    """A project with use cases, an old definition of done and recent code, on `project`."""
    headers = {"Authorization": f"Bearer {service.write_value}"}
    base = f"{service.url}/repos/{REPOSITORY}/git"

    def commit(parent: str, files: dict[str, str], date: str) -> str:
        tree_base = httpx.get(f"{base}/commits/{parent}", headers=headers, timeout=5.0).json()
        entries = [
            {"path": p, "mode": "100644", "type": "blob", "sha": _blob(service, c)}
            for p, c in files.items()
        ]
        tree = control(
            service,
            f"/repos/{REPOSITORY}/git/trees",
            {"base_tree": tree_base["tree"]["sha"], "tree": entries},
        )
        made = control(
            service,
            f"/repos/{REPOSITORY}/git/commits",
            {"message": "work", "tree": tree["sha"], "parents": [parent]},
        )
        control(
            service, "/_fake/date", {"repository": REPOSITORY, "sha": made["sha"], "date": date}
        )
        return str(made["sha"])

    main = httpx.get(f"{base}/ref/heads/main", headers=headers, timeout=5.0).json()
    first = commit(
        main["object"]["sha"],
        {"docs/usecases/UC-1.md": "# UC-1\n", "docs/definition-of-done.md": "# Done\n"},
        "2024-01-10T09:00:00Z",
    )
    head = commit(first, {"src/app.py": "print('shop')\n"}, "2026-05-30T09:00:00Z")
    control(service, f"/repos/{REPOSITORY}/git/refs", {"ref": "refs/heads/project", "sha": head})
    return head


def read(service: Service, tail: str, params: Json | None = None) -> Any:
    answer = httpx.get(
        f"{service.url}/repos/{REPOSITORY}/{tail}",
        params=params,
        headers={"Authorization": f"Bearer {service.write_value}"},
        timeout=5.0,
    )
    answer.raise_for_status()
    return answer.json()


def _blob(service: Service, content: str) -> str:
    made = control(
        service, f"/repos/{REPOSITORY}/git/blobs", {"content": content, "encoding": "utf-8"}
    )
    return str(made["sha"])


def projects(service: Service, pages: Path | None) -> ScaffoldProjects:
    repository = McpActionConnector(
        build_server(Config(target=service.url, repository=REPOSITORY, timeout=5.0)),
        timeout=10.0,
    )
    return ScaffoldProjects(repository, None if pages is None else DirectoryConnector(pages))


@pytest.mark.usefixtures("credentials")
async def test_a_project_is_checked_and_every_artifact_named_from_the_dates_it_last_changed(
    service: Service, tmp_path: Path
) -> None:
    head = project_branch(service)
    check = await projects(service, tmp_path).check(
        development(), "1.0.0", "draft", Project("project", PLACE), acting("scaffold-check-0001")
    )
    assert check.scaffold == "development-scaffold@1.0.0" and check.stage == "draft"
    assert check.commit == head
    states = {f.artifact: f.state for f in check.findings}
    assert states == {
        "use-cases": ArtifactState.UNMAINTAINED,
        "architecture-decisions": ArtifactState.MISSING,
        "test-strategy": ArtifactState.MISSING,
        "definition-of-done": ArtifactState.UNMAINTAINED,
        "glossary": ArtifactState.MISSING,
    }
    done = next(f for f in check.findings if f.artifact == "definition-of-done")
    assert done.stale_days == 871, "from 2024-01-10 to the project's newest change, 2026-05-30"

    unread = await projects(service, None).check(
        development(), "1.0.0", "draft", Project("project", PLACE), acting("scaffold-check-0002")
    )
    glossary = next(f for f in unread.findings if f.artifact == "glossary")
    assert glossary.state is ArtifactState.UNREAD
    assert glossary.reason == "no knowledge system is configured"


@pytest.mark.usefixtures("credentials")
async def test_furnishing_creates_what_is_missing_as_a_pull_request_and_pages_and_nothing_twice(
    service: Service, tmp_path: Path
) -> None:
    project_branch(service)
    furnishing = projects(service, tmp_path)
    scaffold = development()
    first = await furnishing.furnish(
        scaffold, "1.0.0", "production", Project("project", PLACE), acting("scaffold-furnish-01")
    )
    assert set(first.created) == {"architecture-decisions", "test-strategy", "glossary"}
    assert first.pull_request is not None and first.branch is not None
    pull = read(service, f"pulls/{first.pull_request}")
    assert pull["base"]["ref"] == "project" and pull["head"]["ref"] == first.branch
    assert "content is yours to write" in pull["body"]
    assert "Definition of done, 871 days behind the project" in pull["body"]
    for path, template in [
        ("docs/adr/decision.md", "templates/decision.md"),
        ("docs/test-strategy.md", "templates/test-strategy.md"),
    ]:
        found = read(service, f"contents/{path}", {"ref": first.branch})
        assert base64.b64decode(found["content"]).decode() == scaffold.templates[template]
    untouched = read(service, f"pulls/{first.pull_request}/files")
    assert sorted(f["filename"] for f in untouched) == [
        "docs/adr/decision.md",
        "docs/test-strategy.md",
    ], "an artifact that is there is never overwritten"
    page = tmp_path / "Projects" / "Shop" / "Glossary.md"
    assert page.read_text(encoding="utf-8").startswith(scaffold.templates["templates/glossary.md"])

    again = await furnishing.furnish(
        scaffold, "1.0.0", "production", Project("project", PLACE), acting("scaffold-furnish-01")
    )
    assert again.pull_request == first.pull_request and again.branch == first.branch
    assert set(again.created) == {"architecture-decisions", "test-strategy"}, (
        "the glossary is there now; the files wait for the person to merge them"
    )
    state = service.state()[REPOSITORY]
    assert state["pulls"] == 1, "a repeat found its pull request by its mark"
