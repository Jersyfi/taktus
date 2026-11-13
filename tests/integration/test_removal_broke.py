"""A verdict of *broke* names every process and step that lost its only adapter, and is raised
to the owner of each of those processes (UC-8.9 §2, ADR-0300 §3).

The process reads through the fake connector and declares no person as its fallback: without
the connector nobody takes the step over. Its owner is the role its escalation names.
"""

from __future__ import annotations

import copy
from typing import Any

from fakes import FakeConnector
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryPersistence, MemoryRepository
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.run.domain.model import RunState

from .test_removal_test import (
    FAKE_PROCESS,
    RECORDS,
    TENANT,
    connector_services,
    result_of,
    run_removal,
)


def unattended() -> dict[str, Any]:
    """FAKE_PROCESS reduced to its read, whose fallback is a model rather than a person, owned
    by the role `records-lead`."""
    bundle = copy.deepcopy({k: v for k, v in FAKE_PROCESS.items() if k != "takeover"})
    bundle["id"] = "records-unattended"
    bundle["steps"] = [bundle["steps"][0]]
    bundle["steps"][0]["fallback"] = {"when": "no connector serves it", "to": "llm"}
    bundle["escalation"] = {"role": "records-lead", "react_within": 3600}
    return instructed(bundle)


async def incidents(persistence: Any) -> list[Incident]:
    assert isinstance(persistence, MemoryPersistence)
    async with persistence.transaction(TENANT):
        return list(await MemoryRepository(persistence, Incident).list(TENANT))


async def test_a_broke_verdict_is_raised_to_the_owner_of_each_process_that_broke() -> None:
    connector = FakeConnector()
    connector.reads["issue-1"] = {"id": "issue-1", "title": "Pin the model"}
    services = connector_services(connector)
    await services.register_version.execute(RegisterProcessVersion(unattended(), tenant=TENANT))

    run = await run_removal(services, RECORDS)
    assert run.state is RunState.FINISHED, run.reason
    result = (await result_of(services, run, "exercise"))["output"]
    assert result["verdict"] == "broke"
    (process,) = result["processes"]
    assert process["process"] == "records-unattended@1" and process["verdict"] == "broke"

    (raised,) = await incidents(services.work)
    assert raised.kind is IncidentKind.REMOVAL_BROKE
    assert raised.process_id == "records-unattended"
    assert raised.facts["role"] == "records-lead", "the process's owner, a role"
    assert raised.facts["integration"] == RECORDS and raised.facts["steps"] == "read"
    assert "no other adapter serves" in str(raised.facts["reasons"])

    again = await run_removal(services, RECORDS)
    assert again.state is RunState.FINISHED
    assert len(await incidents(services.work)) == 2, "once per removal run, never twice for one"


async def test_a_changed_verdict_raises_nothing() -> None:
    connector = FakeConnector()
    services = connector_services(connector)
    await services.register_version.execute(RegisterProcessVersion(FAKE_PROCESS, tenant=TENANT))
    run = await run_removal(services, RECORDS)
    assert (await result_of(services, run, "exercise"))["output"]["verdict"] == "changed"
    assert await incidents(services.work) == []
