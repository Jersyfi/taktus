"""Every domain has a person: its owner, its legal anchors per jurisdiction, and whether it can
run without Taktus (UC-15.5, ADR-0259)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock
from fakes.identity import directory
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import (
    AnchorsInForce,
    AnchorsRefused,
    ConfigureAnchors,
    ConfigureAnchorsHandler,
)
from taktus.components.governance.application.service.domains import (
    DomainRefused,
    InstantiateDomain,
    TenantDomains,
)
from taktus.components.governance.domain.model.anchors import AnchorConfiguration
from taktus.components.governance.domain.model.domains import Domain
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion, RaiseRefused

TENANT = "default"
AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


def legal(id: str, **scope: str) -> dict[str, Any]:
    anchor: dict[str, Any] = {
        "id": id,
        "class": "legal",
        "act": "file the payroll tax return",
        "applies_to": {"actions": ["tax.file"]},
        "decider": {"role": "owner"},
    }
    if scope:
        anchor["scope"] = scope
    return anchor


CORRECTION = {
    "id": "anc-correction",
    "class": "correction",
    "act": "correct a result that left",
    "applies_to": {"actions": ["correction.*"]},
    "decider": {"role": "owner"},
}


class Checked:
    def __init__(self, takeover: set[str], removal: set[str]) -> None:
        self.takeover, self.removal = takeover, removal

    async def takeover_passed(self, tenant: str, process: str) -> bool:
        return process in self.takeover

    async def removal_passed(self, tenant: str, process: str) -> bool:
        return process in self.removal


class Given:
    def __init__(self, tests: Checked | None = None) -> None:
        self.identities = directory()
        self.persistence = MemoryPersistence()
        clock = FakeClock(AT)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), clock)
        self.repository = MemoryRepository(self.persistence, Domain)
        self.configurations = MemoryRepository(self.persistence, AnchorConfiguration)
        self.domains = TenantDomains(
            self.repository,
            self.configurations,
            self.identities.directory,
            self.ledger,
            self.persistence,
            clock,
            tests,
        )
        self.configure = ConfigureAnchorsHandler(
            self.configurations, self.persistence, self.ledger, clock, self.repository
        )
        self.anchors = AnchorsInForce(self.configurations, self.persistence, self.repository)
        self.register = RegisterProcessVersionHandler(
            MemoryRepository(self.persistence, ProcessVersion),
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
            clock=clock,
            domains=self.domains,
        )

    async def person(self, identity: str) -> None:
        await self.identities.directory.add(TENANT, identity, (TENANT,))

    async def payroll(self, owner: str | None = "idn_ada", jurisdiction: str = "DE-BY") -> Domain:
        return await self.domains.instantiate(
            InstantiateDomain(
                tenant=TENANT,
                domain="payroll",
                name="Payroll",
                owner=owner,
                jurisdiction=jurisdiction,
                processes=("pay-run",),
            ),
            by="idn_admin",
        )


async def test_a_domain_without_an_owner_or_with_an_unknown_one_is_not_instantiated() -> None:
    given = Given()
    with pytest.raises(DomainRefused, match="names no owner"):
        await given.payroll(owner=None)
    with pytest.raises(DomainRefused, match="no identity of the tenant"):
        await given.payroll(owner="idn_nobody")
    assert await given.domains.every(TENANT) == []


async def test_an_owner_who_leaves_leaves_the_domain_shown_without_one_until_one_is_named() -> None:
    given = Given()
    await given.person("idn_ada")
    await given.person("idn_bo")
    await given.payroll()
    left = await given.domains.vacate(TENANT, "payroll", by="idn_admin")
    assert left.owner is None
    [view] = await given.domains.views(TENANT)
    assert view.owner is None
    assert await given.domains.ownerless(TENANT, "pay-run") == "payroll"
    named = await given.domains.name_owner(TENANT, "payroll", "idn_bo", by="idn_admin")
    assert named.owner == "idn_bo" and await given.domains.ownerless(TENANT, "pay-run") is None
    async with given.persistence.transaction(TENANT):
        kinds = [e.kind for e in await given.ledger.entries(TENANT)]
    assert kinds[-3:] == ["domain.instantiated", "domain.owner_left", "domain.owner_named"]


def bundle(version: str, level: int) -> dict[str, Any]:
    return instructed(
        {
            "id": "pay-run",
            "version": version,
            "name": "pay run",
            "autonomy": {"level": level, "reason": "a test", "toward_next": "nothing"},
            "steps": [
                {
                    "id": "sum",
                    "method": "rule",
                    "reason": "a sum",
                    "rejected": [],
                    "exactness": "tolerant",
                }
            ],
        }
    )


async def test_while_a_domain_has_no_owner_nothing_in_it_is_raised() -> None:
    given = Given()
    await given.person("idn_ada")
    await given.payroll()
    await given.register.execute(RegisterProcessVersion(bundle=bundle("1", 1), tenant=TENANT))
    await given.domains.vacate(TENANT, "payroll", by="idn_admin")
    with pytest.raises(RaiseRefused, match="no owner now"):
        await given.register.execute(
            RegisterProcessVersion(
                bundle=bundle("2", 2), tenant=TENANT, by="idn_ada", approved_by="idn_ada"
            )
        )
    async with given.persistence.transaction(TENANT):
        refused = [e for e in await given.ledger.entries(TENANT) if e.kind == "autonomy.refused"]
    assert [e.outcome for e in refused] == ["no_owner"]
    same = await given.register.execute(
        RegisterProcessVersion(bundle=bundle("3", 1), tenant=TENANT)
    )
    assert same.ref == "pay-run@3", "a version that raises nothing registers"


async def test_the_catalogue_is_per_domain_and_jurisdiction_and_never_emptied() -> None:
    given = Given()
    await given.person("idn_ada")
    await given.configure.execute(
        ConfigureAnchors(
            tenant=TENANT,
            document={"anchors": [legal("anc-de", jurisdiction="DE"), CORRECTION]},
            actor="idn_admin",
        )
    )
    with pytest.raises(DomainRefused, match="no legal anchor"):
        await given.payroll(jurisdiction="FR")
    domain = await given.payroll(jurisdiction="DE-BY")
    [view] = await given.domains.views(TENANT)
    assert [a.id for a in view.legal] == ["anc-de"], "DE covers DE-BY"
    held = await given.anchors.applying(TENANT, "pay-run", ["tax.file"])
    assert [a.id for a in held] == ["anc-de"]
    assert domain.jurisdiction == "DE-BY"
    with pytest.raises(AnchorsRefused, match="payroll"):
        await given.configure.execute(
            ConfigureAnchors(
                tenant=TENANT,
                document={"anchors": [legal("anc-fr", jurisdiction="FR"), CORRECTION]},
                actor="idn_admin",
            )
        )


async def test_an_anchor_scoped_to_a_domain_holds_there_and_not_in_another_process() -> None:
    given = Given()
    await given.person("idn_ada")
    await given.configure.execute(
        ConfigureAnchors(
            tenant=TENANT,
            document={
                "anchors": [legal("anc-any"), legal("anc-payroll", domain="payroll"), CORRECTION]
            },
            actor="idn_admin",
        )
    )
    await given.payroll()
    inside = await given.anchors.applying(TENANT, "pay-run", ["tax.file"])
    outside = await given.anchors.applying(TENANT, "support", ["tax.file"])
    assert [a.id for a in inside] == ["anc-any", "anc-payroll"]
    assert [a.id for a in outside] == ["anc-any"]


async def test_a_domain_runs_without_taktus_only_where_both_tests_passed() -> None:
    given = Given(Checked(takeover={"pay-run"}, removal=set()))
    await given.person("idn_ada")
    await given.payroll()
    [view] = await given.domains.views(TENANT)
    assert view.takeover == {"pay-run": True} and view.removal == {"pay-run": False}
    assert not view.runs_without_taktus
    given.domains._tests = Checked(takeover={"pay-run"}, removal={"pay-run"})
    [view] = await given.domains.views(TENANT)
    assert view.runs_without_taktus
