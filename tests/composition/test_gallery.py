"""The gallery a person chooses a first process from (UC-10.4, ADR-0136, issue #405), over the
memory stores and the repository's own `blueprints/gallery/`.

The gallery holds a blueprint for a family, a club and a small business, each a set of open
files that `taktusctl bundle check` accepts; a blueprint removed from its directory is gone from
the gallery and nothing else breaks; no gallery is an empty one; a process starts at autonomy
level 1 or 2; choosing one makes a proposal against no version, with the person's choices; its
rehearsal runs to its end on an instance with no connector; it goes live only by commissioning.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from taktus.adapters.driven.memory import MemoryRepository
from taktus.adapters.driving.cli.bundle_command import bundle as bundle_cli
from taktus.components.process.application.service.proposals import ProposalError
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.run.domain.model import RunState
from taktus.composition.gallery import Gallery

from .test_proposals import TENANT, WHO, World

ROOT = Path(__file__).resolve().parents[2]
GALLERY = ROOT / "blueprints" / "gallery"


async def world_with(directory: Path | None) -> tuple[World, Gallery]:
    world = World()
    await world.identity.directory.add(TENANT, WHO, (TENANT, "ops"))
    gallery = Gallery(
        directory,
        world.proposals,
        MemoryRepository(world.persistence, ProcessVersion),
        world.persistence,
    )
    return world, gallery


def copy_of_gallery(tmp_path: Path) -> Path:
    target = tmp_path / "gallery"
    shutil.copytree(GALLERY, target)
    return target


def test_the_gallery_offers_a_family_a_club_and_a_small_business_at_level_two_or_below() -> None:
    gallery = Gallery(GALLERY, None, None, None)  # type: ignore[arg-type]  # reading needs none
    found = {b.id: b for b in gallery.blueprints()}
    assert set(found) == {"family", "club", "small-business"}
    for blueprint in found.values():
        assert blueprint.title and blueprint.summary
        assert blueprint.processes, blueprint.id
        for process in blueprint.processes:
            assert not process.refused, (blueprint.id, process.refused)
            assert process.level is not None and process.level <= 2
            assert process.level_reason
            assert all(step.reason for step in process.steps)
            assert process.choices, "a person can change it before rehearsing it"


def test_every_gallery_bundle_is_accepted_by_bundle_check() -> None:
    result = CliRunner().invoke(bundle_cli, [str(GALLERY)])
    assert result.exit_code == 0, result.output
    assert "3 would register, 0 refused" in result.output


def test_no_gallery_is_an_empty_one(tmp_path: Path) -> None:
    for directory in (None, tmp_path / "nowhere"):
        assert Gallery(directory, None, None, None).blueprints() == []  # type: ignore[arg-type]


async def test_a_blueprint_removed_is_gone_from_the_gallery_and_the_rest_still_works(
    tmp_path: Path,
) -> None:
    directory = copy_of_gallery(tmp_path)
    world, gallery = await world_with(directory)
    shutil.rmtree(directory / "club")
    assert {b.id for b in gallery.blueprints()} == {"family", "small-business"}
    with pytest.raises(ProposalError) as gone:
        await gallery.propose(TENANT, "club", "meeting-reminder", {}, WHO)
    assert gone.value.kind == "unknown"
    proposal = await gallery.propose(TENANT, "family", "shopping-list", {}, WHO)
    _, run = await world.acts.rehearse(TENANT, "shopping-list", proposal.id, WHO)
    assert (await world.run_through(run.id)).state is RunState.FINISHED


def test_nothing_outside_the_gallery_names_a_gallery_blueprint() -> None:
    """Removing a blueprint breaks no test but its own (UC-10.4): nothing in the product, the
    web app, the deployment or another test names a blueprint's directory or its process."""
    names: set[str] = set()
    for blueprint in GALLERY.iterdir():
        if not blueprint.is_dir():
            continue
        names.add(f"gallery/{blueprint.name}")
        for bundle in (blueprint / "processes").glob("*.yaml"):
            names.add(str(yaml.safe_load(bundle.read_text(encoding="utf-8"))["id"]))
    pattern = re.compile("|".join(rf"\b{re.escape(n)}\b" for n in sorted(names)))
    own = {Path(__file__).resolve()}
    found = []
    for folder in ("src", "web/src", "deploy", "tests", "examples"):
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or path.resolve() in own or "node_modules" in path.parts:
                continue
            if path.suffix not in {".py", ".ts", ".svelte", ".yaml", ".yml", ".sh", ".json"}:
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                found.append(str(path.relative_to(ROOT)))
    assert found == [], found


async def test_choosing_makes_a_first_version_with_the_choices_and_it_goes_live_only_after(
    tmp_path: Path,
) -> None:
    world, gallery = await world_with(GALLERY)
    proposal = await gallery.propose(
        TENANT, "family", "shopping-list", {"household": "the Jansens", "day": "Friday"}, WHO
    )
    assert proposal.base_version is None and proposal.version == "1"
    assert proposal.request == "from the gallery: A family"
    (trigger,) = proposal.bundle["triggers"]
    assert trigger["inputs"]["household"] == "the Jansens"
    assert trigger["inputs"]["day"] == "Friday"
    async with world.persistence.transaction(TENANT):
        assert await world.processes.get(TENANT, "shopping-list") is None, "nothing is live"
    rehearsed, run = await world.acts.rehearse(TENANT, "shopping-list", proposal.id, WHO)
    assert run.rehearsal and run.inputs["household"] == "the Jansens"
    finished = await world.run_through(run.id)
    assert finished.state is RunState.FINISHED
    assert world.connector.calls == []
    version = await world.acts.commission(TENANT, "shopping-list", rehearsed.id, WHO)
    assert version.version == "1" and version.autonomy_level == 2
    async with world.persistence.transaction(TENANT):
        live = await world.processes.get(TENANT, "shopping-list")
    assert live is not None and live.active_version == "1"


async def test_every_gallery_process_rehearses_to_its_end_on_an_instance_with_no_connector() -> (
    None
):
    world, gallery = await world_with(GALLERY)
    for blueprint in gallery.blueprints():
        for process in blueprint.processes:
            proposal = await gallery.propose(TENANT, blueprint.id, process.id, {}, WHO)
            _, run = await world.acts.rehearse(TENANT, process.id, proposal.id, WHO)
            finished = await world.run_through(run.id)
            assert finished.state is RunState.FINISHED, (process.id, finished.state)
    assert world.connector.calls == []


async def test_a_choice_it_does_not_offer_and_a_process_above_level_two_are_refused(
    tmp_path: Path,
) -> None:
    directory = copy_of_gallery(tmp_path)
    path = directory / "club" / "processes" / "meeting-reminder.yaml"
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["autonomy"]["level"] = 3
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    _, gallery = await world_with(directory)
    (club,) = [b for b in gallery.blueprints() if b.id == "club"]
    (reminder,) = club.processes
    assert reminder.refused and "level 3" in reminder.refused[0]
    with pytest.raises(InvalidProcess, match="level 3"):
        await gallery.propose(TENANT, "club", "meeting-reminder", {}, WHO)
    with pytest.raises(InvalidProcess, match="no choice 'autonomy'"):
        await gallery.propose(TENANT, "family", "shopping-list", {"autonomy": 4}, WHO)


async def test_a_process_the_tenant_has_already_is_proposed_as_its_next_version() -> None:
    world, gallery = await world_with(GALLERY)
    first = await gallery.propose(TENANT, "family", "shopping-list", {}, WHO)
    _, run = await world.acts.rehearse(TENANT, "shopping-list", first.id, WHO)
    await world.run_through(run.id)
    await world.acts.commission(TENANT, "shopping-list", first.id, WHO)
    again = await gallery.propose(TENANT, "family", "shopping-list", {"day": "Monday"}, WHO)
    assert (again.base_version, again.version) == ("1", "2")
