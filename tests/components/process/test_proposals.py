"""A changed bundle becomes a proposal, never a version (UC-4.15, ADR-0091 §1, issue #294).

A proposal passes what registration checks, names a version not registered yet, and carries its
difference against the active version, step by step. The active version, and with it what runs,
is unchanged by it. A bundle that would not register gives the registration's findings and no
proposal; an open proposal can be discarded, a closed one cannot.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fakes.clock import FakeClock, FakeIdentifiers

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.proposals import (
    ProposalError,
    Proposals,
    Propose,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    ProcessVersion,
    Proposal,
    ProposalState,
)

TENANT = "default"


def bundle(version: str = "1") -> dict[str, Any]:
    return {
        "id": "invoices",
        "version": version,
        "name": "Invoices",
        "autonomy": {"level": 2, "reason": "a person confirms", "toward_next": "twenty runs"},
        "steps": [
            {
                "id": "read",
                "method": "rule",
                "reason": "fixed fields",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": 1},
            },
            {
                "id": "draft",
                "method": "llm",
                "reason": "free text",
                "rejected": [{"method": "rule", "why": "too varied"}],
                "exactness": "free",
                "fallback": {"when": "unclear", "to": "human"},
                "model": "m@1",
                "depends_on": ["read"],
                "work": {"prompt": "x"},
            },
        ],
    }


def changed() -> dict[str, Any]:
    """Version 2: `draft` gets another reason, `check` is added after it."""
    document = bundle("2")
    document["steps"][1]["reason"] = "free text, from the issue"
    document["steps"].append(
        {
            "id": "check",
            "method": "rule",
            "reason": "the title follows a pattern",
            "rejected": [{"method": "llm", "why": "a pattern needs no judgement"}],
            "exactness": "exact",
            "checks": [{"kind": "recomputation"}],
            "depends_on": ["draft"],
            "work": {"rule": "constant", "value": True},
        }
    )
    return document


class World:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        clock = FakeClock()
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.processes = MemoryRepository(self.persistence, Process)
        self.register = RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            self.processes,
            ledger=ChainedLedger(MemoryLedgerStore(self.persistence), clock),
        )
        self.proposals = Proposals(
            self.versions,
            self.processes,
            MemoryRepository(self.persistence, Proposal),
            self.persistence,
            clock,
            FakeIdentifiers(),
        )

    async def active(self) -> str | None:
        async with self.persistence.transaction(TENANT):
            process = await self.processes.get(TENANT, "invoices")
        return None if process is None else process.active_version


async def given_registered() -> World:
    world = World()
    await world.register.execute(RegisterProcessVersion(bundle(), tenant=TENANT))
    return world


async def test_a_changed_bundle_becomes_a_proposal_and_nothing_is_registered() -> None:
    world = await given_registered()
    proposal = await world.proposals.propose(
        Propose(TENANT, "invoices", changed(), by="idn_ada", request="check the title too")
    )
    assert proposal.state is ProposalState.PROPOSED
    assert (proposal.base_version, proposal.version) == ("1", "2")
    assert proposal.request == "check the title too" and proposal.requested_by == "idn_ada"
    assert await world.active() == "1", "the active version is unchanged"
    async with world.persistence.transaction(TENANT):
        assert await world.versions.get(TENANT, "invoices@2") is None
    assert [p.id for p in await world.proposals.of_process(TENANT, "invoices")] == [proposal.id]


async def test_the_difference_names_every_step_added_removed_or_changed() -> None:
    world = await given_registered()
    document = changed()
    del document["steps"][0]["checks"]
    document["steps"][0] = {**bundle()["steps"][0], "id": "load"}
    document["steps"][1]["depends_on"] = ["load"]
    proposal = await world.proposals.propose(Propose(TENANT, "invoices", document, by="idn_ada"))
    changes = {c.id: c for c in proposal.difference.steps}
    assert {c.id: c.change for c in proposal.difference.steps} == {
        "load": "added",
        "draft": "changed",
        "check": "added",
        "read": "removed",
    }
    assert changes["draft"].fields == ("depends_on", "reason")
    assert changes["draft"].before is not None and changes["draft"].after is not None
    assert changes["check"].after is not None and changes["check"].after.method == "rule"
    assert not proposal.difference.triggers_changed


async def test_a_bundle_that_would_not_register_gives_the_findings_and_no_proposal() -> None:
    world = await given_registered()
    broken = changed()
    del broken["steps"][2]["checks"]  # an exact step without a check (UC-4.13)
    with pytest.raises(InvalidProcess) as refused:
        await world.proposals.propose(Propose(TENANT, "invoices", broken, by="idn_ada"))
    assert any("check" in f for f in refused.value.findings)
    assert await world.proposals.of_process(TENANT, "invoices") == []


async def test_a_proposal_never_writes_over_a_registered_version() -> None:
    world = await given_registered()
    again = deepcopy(bundle())
    again["steps"][1]["reason"] = "changed under the same version"
    with pytest.raises(InvalidProcess, match="never written over"):
        await world.proposals.propose(Propose(TENANT, "invoices", again, by="idn_ada"))


async def test_a_bundle_for_another_process_or_an_unknown_process_is_refused() -> None:
    world = await given_registered()
    other = changed()
    other["id"] = "orders"
    with pytest.raises(InvalidProcess, match="not 'invoices'"):
        await world.proposals.propose(Propose(TENANT, "invoices", other, by="idn_ada"))
    with pytest.raises(ProposalError) as unknown:
        await world.proposals.propose(Propose(TENANT, "orders", other, by="idn_ada"))
    assert unknown.value.kind == "unknown"


async def test_an_open_proposal_is_discarded_once() -> None:
    world = await given_registered()
    proposal = await world.proposals.propose(Propose(TENANT, "invoices", changed(), by="idn_ada"))
    discarded = await world.proposals.discard(TENANT, "invoices", proposal.id)
    assert discarded.state is ProposalState.DISCARDED
    with pytest.raises(ProposalError) as closed:
        await world.proposals.discard(TENANT, "invoices", proposal.id)
    assert closed.value.kind == "closed"
    assert await world.active() == "1"
