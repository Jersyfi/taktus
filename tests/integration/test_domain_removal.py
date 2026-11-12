"""Replacing the system behind an instance of a domain blueprint breaks none of its processes
(ADR-0263, UC-15.1 §2, UC-8.9): the removal test of S-01, run for real, over a process an
instance proposed and a person commissioned.

The instance binds its capability to one connector. A second connector declares the same
capability, as a replacement system does. Withholding the bound one leaves every step served by
the other, so the verdict is *changed*, never *broke*, and nothing leaves the system.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fakes import FakeConnector

from integration.test_removal_test import (
    FAKE_PROCESS,
    RECORDS,
    TENANT,
    connector_services,
    result_of,
    run_removal,
)
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.catalog.application.service import DomainInstances
from taktus.components.catalog.domain.model import DomainInstance
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.domain.model.proposal import Proposal
from taktus.components.run.domain.model import RunState
from taktus.composition.domain_blueprints import (
    DeclaredAdapters,
    KnownPeople,
    ProposalsOfProcesses,
    admitted,
)

SECOND = "connector.second"
WHO = "idn_test"


def blueprint_in(tmp_path: Path) -> Path:
    directory = tmp_path / "records"
    (directory / "processes").mkdir(parents=True)
    (directory / "processes" / "R-01.yaml").write_text(
        yaml.safe_dump(FAKE_PROCESS, sort_keys=False), encoding="utf-8"
    )
    (directory / "blueprint.yaml").write_text(
        yaml.safe_dump(
            {
                "kind": "Blueprint",
                "metadata": {
                    "id": "records",
                    "name": "Records",
                    "domain": "administration",
                    "version": "1",
                },
                "requires": {"connectors": [{"capability": "fake.records"}]},
                "anchors": {"strategic": ["records.delete"], "legal": []},
                "value_criteria": {"cost": ["compute"], "benefit": ["working_time_saved"]},
                "processes": [
                    {"id": "R-01", "name": "Read and write", "bundle": "processes/R-01.yaml"}
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


async def test_replacing_the_system_behind_an_instance_changes_its_process_and_breaks_none(
    tmp_path: Path,
) -> None:
    services = connector_services(FakeConnector(), others=((SECOND, FakeConnector()),))
    await services.identities.add(TENANT, WHO, (TENANT,))
    persistence = services.work
    versions = MemoryRepository(persistence, ProcessVersion)  # type: ignore[arg-type]
    proposals = Proposals(
        versions,
        MemoryRepository(persistence, Process),  # type: ignore[arg-type]
        MemoryRepository(persistence, Proposal),  # type: ignore[arg-type]
        persistence,
        services.clock,
        services.ids,
    )
    domains = DomainInstances(
        MemoryRepository(persistence, DomainInstance),  # type: ignore[arg-type]
        persistence,
        ProposalsOfProcesses(proposals, versions, persistence),
        KnownPeople(services.identities),
        DeclaredAdapters({RECORDS: ("fake.records",), SECOND: ("fake.records",)}),
        services.clock,
        services.ids,
    )
    found = admitted(blueprint_in(tmp_path))
    instance = await domains.start(TENANT, found, by=WHO)
    [question] = [q for q in domains.questions(found, instance) if q.kind == "capability"]
    assert question.options == (RECORDS, SECOND), "both systems declare the capability"
    await domains.answer(TENANT, found, instance.id, "fake.records", RECORDS, by=WHO)
    await domains.name_owner(TENANT, instance.id, WHO)
    await domains.name_jurisdiction(TENANT, instance.id, "DE")
    instance = await domains.propose(TENANT, found, instance.id, by=WHO)
    [made] = instance.proposed
    proposal = await proposals.find(TENANT, made.proposal)
    # A person commissions the proposal: registration registers its bundle.
    registered = await services.register_version.execute(
        RegisterProcessVersion(proposal.bundle, tenant=TENANT, by=WHO)
    )
    assert registered.autonomy_level == 2

    run = await run_removal(services, RECORDS)
    assert run.state is RunState.FINISHED, run.reason
    result = (await result_of(services, run, "exercise"))["output"]
    assert result["verdict"] == "changed", result
    [process] = result["processes"]
    assert process["process"] == registered.ref and process["verdict"] == "changed"
    for step in process["steps"]:
        assert step["verdict"] == "changed" and step["alternative"] == SECOND, step
    async with persistence.transaction(TENANT):
        entries = list(await services.ledger.entries(TENANT))
    assert not [e for e in entries if e.kind.startswith("egress.")], "nothing left the system"
