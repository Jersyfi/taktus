"""The domain blueprints of this repository, admitted, instantiated and exported (ADR-0263,
UC-15.1), over the memory stores and the process component's own proposals.

Every blueprint under `blueprints/` enters the catalogue, names its systems by capability only,
and starts every process of an instance at level 1 or 2, as a proposal a person commissions. A
later version is offered as proposals; the active versions stay. An exported blueprint is plain
files that are admitted again as they are.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.catalog.application.service import DomainInstances, DomainRefused
from taktus.components.catalog.domain.model import DomainInstance
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    parse_bundle,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.domain.model.proposal import OPEN
from taktus.composition.domain_blueprints import (
    DeclaredAdapters,
    DomainBlueprints,
    KnownPeople,
    ProposalsOfProcesses,
    admitted,
    export,
    read,
    read_all,
)
from taktus.composition.shipped import load

from .test_proposals import TENANT, WHO, World

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINTS = ROOT / "blueprints"


def test_every_blueprint_of_the_repository_enters_the_catalogue() -> None:
    found = {r.directory.name: r for r in read_all(BLUEPRINTS)}
    assert set(found) == {"dev-orchestration", "knowledge", "self-operation", "software-operations"}
    for name, result in found.items():
        assert result.admitted is not None, (name, result.admission.findings)
        blueprint = result.admitted.blueprint
        assert blueprint.strategic or blueprint.legal, name
        assert blueprint.cost and blueprint.benefit, name
        for process in blueprint.processes:
            assert 1 <= process.level <= 4 and process.reason, (name, process.id)


def test_a_blueprint_names_its_systems_by_capability_only() -> None:
    """A product is a connector the release ships whose name is no capability's area: the
    generic ones (`accounting`, `mail`) are named after what they serve."""
    shipped = load()
    areas = {c.split(".")[0] for a in shipped.connectors for c in a.capabilities}
    # The loopback connector is the instance reaching itself, no product (ADR-0030).
    products = {a.name for a in shipped.connectors} - areas - {"loopback"}
    assert {"github", "stripe", "sentry"} <= products
    for path in sorted(BLUEPRINTS.glob("*/blueprint.yaml")):
        words = set(re.findall(r"[a-z0-9]+", path.read_text(encoding="utf-8").lower()))
        assert not words & products, (path, sorted(words & products))


def domains_of(world: World) -> DomainBlueprints:
    versions = MemoryRepository(world.persistence, ProcessVersion)
    return DomainBlueprints(
        DomainInstances(
            MemoryRepository(world.persistence, DomainInstance),
            world.persistence,
            ProposalsOfProcesses(world.proposals, versions, world.persistence),
            KnownPeople(world.identity.directory),
            DeclaredAdapters.shipped(),
            world.clock,
            world.ids,
        ),
        world.runs,
        world.persistence,
    )


async def instantiated(world: World, directory: Path) -> tuple[DomainBlueprints, DomainInstance]:
    """An instance of the blueprint with every question answered: the first adapter that
    declares a capability, or none; one of each set of alternatives; the owner."""
    await world.identity.directory.add(TENANT, WHO, (TENANT, "ops"))
    domains = domains_of(world)
    found = admitted(directory)
    instance = await domains.instances.start(TENANT, found, by=WHO)
    for question in domains.instances.questions(found, instance):
        if question.kind == "capability":
            adapter = question.options[0] if question.options else None
            instance = await domains.instances.answer(
                TENANT, found, instance.id, question.subject, adapter, by=WHO
            )
        elif question.kind == "choice":
            instance = await domains.instances.leave_out(
                TENANT, found, instance.id, question.options[1:]
            )
    with pytest.raises(DomainRefused, match="Who owns this domain"):
        await domains.instances.propose(TENANT, found, instance.id, by=WHO)
    instance = await domains.instances.name_owner(TENANT, instance.id, WHO)
    return domains, instance


async def test_software_operations_is_instantiated_in_dialogue_at_level_two_or_below() -> None:
    world = World()
    directory = BLUEPRINTS / "software-operations"
    domains, instance = await instantiated(world, directory)
    found = admitted(directory)
    assert instance.left_out == ("B-8.04-store", "B-8.05-site")
    errors = instance.binding("errors.issues")
    assert errors is not None and errors.adapter == "connector.sentry", (
        "a capability is bound to an adapter that declares it"
    )

    instance = await domains.instances.propose(TENANT, found, instance.id, by=WHO)
    assert len(instance.proposed) == len(found.blueprint.processes) - 2
    for made in instance.proposed:
        proposal = await world.proposals.find(TENANT, made.proposal)
        version = parse_bundle(proposal.bundle)
        assert version.autonomy_level <= 2 and made.level == version.autonomy_level
        assert proposal.requested_by == WHO and proposal.base_version is None
        assert f"instance {instance.id}" in (proposal.request or "")
    async with world.persistence.transaction(TENANT):
        assert list(await world.versions.list(TENANT)) == [], "nothing is registered"
        assert list(await world.processes.list(TENANT)) == [], "a person commissions"


async def test_a_process_usual_at_level_four_is_proposed_at_two_with_its_usual_level_named() -> (
    None
):
    world = World()
    directory = BLUEPRINTS / "dev-orchestration"
    domains, instance = await instantiated(world, directory)
    instance = await domains.instances.propose(TENANT, admitted(directory), instance.id, by=WHO)
    implementation = instance.proposal_of("P-03")
    assert implementation is not None and implementation.level == 2
    proposal = await world.proposals.find(TENANT, implementation.proposal)
    assert proposal.bundle["autonomy"]["level"] == 2
    assert "usual level is 4" in proposal.bundle["autonomy"]["reason"]


async def test_a_later_version_is_offered_as_a_proposal_and_the_active_version_stays(
    tmp_path: Path,
) -> None:
    world = World()
    directory = tmp_path / "dev-orchestration"
    shutil.copytree(BLUEPRINTS / "dev-orchestration", directory)
    domains, instance = await instantiated(world, directory)
    instance = await domains.instances.propose(TENANT, admitted(directory), instance.id, by=WHO)
    refinement = instance.proposal_of("P-02")
    assert refinement is not None
    first = await world.proposals.find(TENANT, refinement.proposal)
    # A person commissions the proposal: registration registers its bundle.
    await world.register.execute(RegisterProcessVersion(first.bundle, tenant=TENANT, by=WHO))

    bundle = directory / "processes" / "P-02-refinement.yaml"
    bundle.write_text(
        bundle.read_text(encoding="utf-8").replace(
            "reason: >", "reason: >\n    the blueprint's second version:", 1
        ),
        encoding="utf-8",
    )
    blueprint = directory / "blueprint.yaml"
    blueprint.write_text(
        blueprint.read_text(encoding="utf-8").replace('version: "1"', 'version: "2"', 1),
        encoding="utf-8",
    )
    later = admitted(directory)
    assert later.blueprint.version == "2"

    offer = await domains.instances.offer(TENANT, later, instance.id, by=WHO)
    assert [p.process for p in offer.proposed] == ["P-02"], "only the changed bundle is offered"
    [made] = offer.proposed
    assert made.version != first.version, "a registered version is never written over"
    offered = await world.proposals.find(TENANT, made.proposal)
    assert offered.base_version == first.version and offered.state in OPEN
    async with world.persistence.transaction(TENANT):
        process = await world.processes.get(TENANT, first.process_id)
    assert isinstance(process, Process) and process.active_version == first.version, (
        "the offer applies nothing"
    )
    kept = await domains.instances.get(TENANT, instance.id)
    assert kept.blueprint_version == "1"


def test_a_blueprint_exports_as_plain_files_that_are_admitted_again(tmp_path: Path) -> None:
    directory = BLUEPRINTS / "software-operations"
    written = export(directory, tmp_path / "out")
    names = {p.relative_to(tmp_path / "out").as_posix() for p in written}
    assert "blueprint.yaml" in names and len(names) == 1 + len(admitted(directory).bundles)
    for path in written:
        source = directory / path.relative_to(tmp_path / "out")
        assert path.read_bytes() == source.read_bytes()
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)
    again = read(tmp_path / "out")
    assert again.admitted is not None, again.admission.findings
    assert again.admitted.blueprint == admitted(directory).blueprint


def test_a_blueprint_whose_bundle_calls_an_unnamed_capability_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "knowledge"
    shutil.copytree(BLUEPRINTS / "knowledge", directory)
    blueprint = directory / "blueprint.yaml"
    blueprint.write_text(
        blueprint.read_text(encoding="utf-8").replace(
            "    - capability: knowledge.documents\n", "    - capability: knowledge.pages\n"
        ),
        encoding="utf-8",
    )
    result = read(directory)
    assert result.admitted is None
    assert result.admission.findings == (
        "the process K-01's bundle calls knowledge.documents, which requires.connectors does not "
        "name",
    )
