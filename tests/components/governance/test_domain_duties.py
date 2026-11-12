"""A domain's escalations, raise proposals and takeover test are addressed to its owner, and the
catalogue in force appears in the conformity evidence (UC-15.5, ADR-0280 §3 and §4)."""

from __future__ import annotations

import json

from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryObjectStore, MemoryRepository
from taktus.components.governance.application.service import ConfigureAnchors
from taktus.components.governance.application.service.domains import (
    ConformityEvidence,
    TenantDomains,
)
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    IncidentState,
)
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .test_domains import AT, CORRECTION, TENANT, Checked, Given, legal


class WithIncidents(Given):
    def __init__(self, tests: Checked | None = None) -> None:
        super().__init__(tests)
        self.incidents = MemoryRepository(self.persistence, Incident)
        self.domains = TenantDomains(
            self.repository,
            self.configurations,
            self.identities.directory,
            self.ledger,
            self.persistence,
            FakeClock(AT),
            tests,
            incidents=self.incidents,
        )

    async def record(self, kind: str, version: str, run: str | None = None) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=TENANT, process_version=version, run_id=run),
                    outcome="x",
                ),
            )


async def test_escalations_raise_proposals_and_the_takeover_test_are_addressed_to_the_owner() -> (
    None
):
    given = WithIncidents(Checked(takeover=set(), removal=set()))
    await given.person("idn_ada")
    await given.person("idn_bo")
    await given.payroll()
    await given.record("run.escalated", "pay-run@2", "run_1")
    await given.record("run.escalated", "pay-run@2", "run_2")
    await given.record("run.resumed", "pay-run@2", "run_2")
    await given.record("run.escalated", "other@1", "run_3")
    await given.record("autonomy.proposed", "pay-run@2")
    async with given.persistence.transaction(TENANT):
        for iid, state in (("inc_open", IncidentState.OPEN), ("inc_closed", IncidentState.CLOSED)):
            await given.incidents.put(
                TENANT,
                Incident(
                    id=iid,
                    tenant=TENANT,
                    kind=IncidentKind.STOP,
                    process_id="tenant",
                    process_version="tenant",
                    rule="stop.person",
                    facts={"processes": "other,pay-run"},
                    raised_at=AT,
                    state=state,
                ),
            )

    [duties] = await given.domains.duties(TENANT, owner="idn_ada")
    assert duties.domain == "payroll" and duties.to == "idn_ada"
    assert [(d.kind, d.subject) for d in duties.duties] == [
        ("escalation", "run_1"),
        ("escalation", "inc_open"),
        ("raise", "pay-run@2"),
        ("takeover", "pay-run"),
    ], "a resumed run, a closed incident and another process's run are not its duties"
    assert await given.domains.duties(TENANT, owner="idn_bo") == [], "nobody else's"

    await given.domains.vacate(TENANT, "payroll", by="idn_admin")
    [ownerless] = await given.domains.duties(TENANT)
    assert ownerless.to is None, "addressed to nobody while the domain has no owner"


async def test_a_passed_takeover_test_is_no_longer_a_duty() -> None:
    given = WithIncidents(Checked(takeover={"pay-run"}, removal=set()))
    await given.person("idn_ada")
    await given.payroll()
    [duties] = await given.domains.duties(TENANT, owner="idn_ada")
    assert duties.duties == ()


async def test_the_catalogue_in_force_appears_in_the_conformity_evidence() -> None:
    given = WithIncidents(Checked(takeover={"pay-run"}, removal={"pay-run"}))
    await given.person("idn_ada")
    await given.configure.execute(
        ConfigureAnchors(
            tenant=TENANT,
            document={
                "anchors": [
                    legal("anc-tax-by", jurisdiction="DE-BY"),
                    legal("anc-tax-fr", jurisdiction="FR"),
                    CORRECTION,
                ]
            },
            actor="idn_admin",
        )
    )
    await given.payroll(jurisdiction="DE-BY")
    objects = MemoryObjectStore()
    evidence = ConformityEvidence(
        given.domains, given.ledger, objects, given.persistence, FakeClock(AT)
    )

    document = await evidence.generate(TENANT, by="idn_admin")
    [payroll] = document["domains"]
    assert payroll["owner"] == "idn_ada" and payroll["jurisdiction"] == "DE-BY"
    assert [a["id"] for a in payroll["legal_anchors"]] == ["anc-tax-by"], "only those in force"
    assert payroll["runs_without_taktus"] is True
    kept = await objects.get(document["digest"])
    assert kept is not None and json.loads(kept)["domains"] == document["domains"]
    async with given.persistence.transaction(TENANT):
        [generated] = await given.ledger.of_kinds(TENANT, ("conformity.generated",))
    assert generated.content_digest == document["digest"] and generated.refs.actor == "idn_admin"
