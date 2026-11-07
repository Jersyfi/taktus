"""The rules of domain blueprints and the dialogue of an instance (ADR-0263, UC-15.1), over
memory and fakes of the three ports.

A blueprint missing a part does not enter the catalogue, and every missing part is named. An
instance asks one question per capability and one for the owner; nothing is proposed while one
is open; every process is proposed at level 2 or below; a later version is offered as proposals,
never applied.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers

from taktus.adapters.driven.memory import MemoryPersistence, MemoryRepository
from taktus.components.catalog.application.service import DomainInstances, DomainRefused
from taktus.components.catalog.domain.model.blueprint import (
    Admitted,
    BundleFacts,
    BundleFile,
    DomainInstance,
)
from taktus.components.catalog.domain.service import blueprints as rules
from taktus.components.catalog.ports.domains import Refused

TENANT = "t"
WHO = "idn_ada"
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def document() -> dict[str, Any]:
    return {
        "kind": "Blueprint",
        "metadata": {"id": "books", "name": "Books", "domain": "finance", "version": "1"},
        "requires": {"connectors": [{"capability": "accounting.bookings"}]},
        "anchors": {"strategic": [], "legal": ["moving_money"]},
        "value_criteria": {"cost": ["compute"], "benefit": ["working_time_saved"]},
        "processes": [
            {"id": "F-01", "name": "Propose bookings", "bundle": "processes/f-01.yaml"},
            {
                "id": "F-02",
                "name": "Close the month",
                "autonomy": {"level": 1, "reason": "described, not built"},
            },
        ],
    }


def facts(level: int = 3, capabilities: tuple[str, ...] = ("accounting.bookings",)) -> Any:
    def of(path: str) -> BundleFacts:
        assert path == "processes/f-01.yaml"
        return BundleFacts(
            process="f-01",
            version="1",
            level=level,
            reason="a rule proposes; a person books",
            capabilities=capabilities,
        )

    return of


def admitted(level: int = 3, digest: str = DIGEST, version: str = "1") -> Admitted:
    raw = document()
    raw["metadata"]["version"] = version
    admission = rules.admit(raw, facts(level))
    assert admission.blueprint is not None, admission.findings
    bundle = {
        "id": "f-01",
        "version": "1",
        "autonomy": {"level": level, "reason": "a rule proposes; a person books"},
    }
    return Admitted(
        blueprint=admission.blueprint,
        bundles={"F-01": BundleFile(content=bundle, digest=digest)},
    )


def test_a_complete_blueprint_is_admitted_with_its_level_and_reason_from_the_bundle() -> None:
    admission = rules.admit(document(), facts())
    assert admission.admitted, admission.findings
    blueprint = admission.blueprint
    assert blueprint is not None
    first = blueprint.process("F-01")
    assert first is not None and first.level == 3 and first.process == "f-01"
    assert first.reason == "a rule proposes; a person books"
    assert blueprint.legal == ("moving_money",)


@pytest.mark.parametrize(
    ("change", "finding"),
    [
        (lambda d: d["metadata"].pop("version"), "its metadata names no version"),
        (lambda d: d["metadata"].pop("domain"), "its metadata names no domain"),
        (lambda d: d.update(processes=[]), "it names no process"),
        (
            lambda d: d.update(anchors={"strategic": [], "legal": []}),
            "it names no act that stays with a person",
        ),
        (lambda d: d["value_criteria"].pop("cost"), "its value criteria name no cost"),
        (lambda d: d["value_criteria"].pop("benefit"), "its value criteria name no benefit"),
        (
            lambda d: d["processes"][1].pop("autonomy"),
            "the process F-02 has no usual autonomy level",
        ),
        (
            lambda d: d["processes"][1]["autonomy"].pop("reason"),
            "the process F-02 gives no reason for its autonomy level",
        ),
        (
            lambda d: d["requires"].update(connectors=[{"capability": "Ledgerly"}]),
            "is not named as area.object",
        ),
        (lambda d: d["processes"][0].update(autonomy={"level": 4}), "states level 4"),
    ],
)
def test_a_blueprint_missing_a_part_does_not_enter_the_catalogue(change: Any, finding: str) -> None:
    raw = document()
    change(raw)
    admission = rules.admit(raw, facts())
    assert not admission.admitted and admission.blueprint is None
    assert any(finding in f for f in admission.findings), admission.findings


def test_every_finding_is_named_at_once_and_a_bundle_calls_only_what_it_requires() -> None:
    raw = document()
    raw["metadata"].pop("version")
    raw["value_criteria"] = {}
    admission = rules.admit(raw, facts(capabilities=("accounting.bookings", "crm.contacts")))
    assert len(admission.findings) == 4, admission.findings
    assert any("calls crm.contacts, which requires.connectors" in f for f in admission.findings)


def test_a_bundle_that_registration_refuses_refuses_the_blueprint() -> None:
    admission = rules.admit(
        document(), lambda path: BundleFacts(findings=("a step has no method",))
    )
    assert admission.findings == (
        "the process F-01's bundle processes/f-01.yaml: a step has no method",
        "the process F-01 has no usual autonomy level from 1 to 4",
        "the process F-01 gives no reason for its autonomy level",
    )


def test_a_process_starts_at_level_two_at_most_and_its_reason_names_the_usual_level() -> None:
    found = admitted(level=4)
    process = found.blueprint.process("F-01")
    assert process is not None
    started = rules.starting(found.bundles["F-01"].content, process, found.blueprint)
    assert started["autonomy"]["level"] == 2
    assert "usual level is 4" in started["autonomy"]["reason"]
    assert started["autonomy"]["toward_next"]
    lower = admitted(level=1)
    process = lower.blueprint.process("F-01")
    assert process is not None
    assert rules.starting(lower.bundles["F-01"].content, process, lower.blueprint) == dict(
        lower.bundles["F-01"].content
    ), "a process usual at level 1 starts unchanged"


def test_two_bundles_of_one_process_are_a_choice_the_instance_must_make() -> None:
    raw = document()
    raw["processes"].append(
        {"id": "F-01-b", "name": "Propose bookings, another way", "bundle": "processes/f-01.yaml"}
    )
    admission = rules.admit(raw, lambda path: facts()("processes/f-01.yaml"))
    assert admission.blueprint is not None
    assert admission.blueprint.alternatives() == (("F-01", "F-01-b"),)


# --- the dialogue -------------------------------------------------------------------------------


class Proposed:
    def __init__(self) -> None:
        self.made: list[tuple[str, Mapping[str, Any], str]] = []
        self.refuse: tuple[str, ...] = ()

    async def propose(
        self, tenant: str, process_id: str, bundle: Mapping[str, Any], by: str, request: str
    ) -> tuple[str, str]:
        if self.refuse:
            raise Refused(self.refuse)
        self.made.append((process_id, copy.deepcopy(dict(bundle)), request))
        return f"prp_{len(self.made)}", str(len(self.made))


class Known:
    async def known(self, tenant: str, identity: str) -> bool:
        return identity == WHO


class Declared:
    def declaring(self, capability: str) -> tuple[str, ...]:
        return ("connector.books",) if capability == "accounting.bookings" else ()


def instances() -> tuple[DomainInstances, Proposed, MemoryRepository[DomainInstance]]:
    persistence = MemoryPersistence()
    repository = MemoryRepository(persistence, DomainInstance)
    proposed = Proposed()
    return (
        DomainInstances(
            repository, persistence, proposed, Known(), Declared(), FakeClock(), FakeIdentifiers()
        ),
        proposed,
        repository,
    )


async def test_the_dialogue_asks_for_each_tool_and_the_owner_and_proposes_nothing_before() -> None:
    domains, proposed, _ = instances()
    found = admitted(level=3)
    instance = await domains.start(TENANT, found, by=WHO)
    asked = domains.questions(found, instance)
    assert [(q.kind, q.subject, q.options) for q in asked] == [
        ("capability", "accounting.bookings", ("connector.books",)),
        ("owner", "owner", ()),
        ("jurisdiction", "jurisdiction", ()),
    ]
    with pytest.raises(DomainRefused) as refused:
        await domains.propose(TENANT, found, instance.id, by=WHO)
    assert refused.value.kind == "open" and len(refused.value.questions) == 3

    instance = await domains.answer(
        TENANT, found, instance.id, "accounting.bookings", "connector.books", by=WHO
    )
    with pytest.raises(DomainRefused, match="Who owns this domain"):
        await domains.propose(TENANT, found, instance.id, by=WHO)
    assert proposed.made == [], "no process is proposed before the domain has its owner"

    instance = await domains.name_owner(TENANT, instance.id, WHO)
    with pytest.raises(DomainRefused, match="country's law"):
        await domains.propose(TENANT, found, instance.id, by=WHO)
    with pytest.raises(DomainRefused, match="no ISO 3166 code"):
        await domains.name_jurisdiction(TENANT, instance.id, "Germany")
    instance = await domains.name_jurisdiction(TENANT, instance.id, "DE")
    instance = await domains.propose(TENANT, found, instance.id, by=WHO)
    assert domains.questions(found, instance) == ()
    [(process_id, bundle, request)] = proposed.made
    assert process_id == "f-01" and bundle["autonomy"]["level"] == 2
    assert "books 1" in request and instance.id in request
    [made] = instance.proposed
    assert (made.process, made.level, made.proposal, made.digest) == ("F-01", 2, "prp_1", DIGEST)

    again = await domains.propose(TENANT, found, instance.id, by=WHO)
    assert len(proposed.made) == 1 and again.proposed == instance.proposed, "proposed once"


async def test_an_answer_is_an_adapter_that_declares_the_capability_or_none() -> None:
    domains, _, _ = instances()
    found = admitted()
    instance = await domains.start(TENANT, found, by=WHO)
    with pytest.raises(DomainRefused, match=r"connector\.other declares no capability"):
        await domains.answer(
            TENANT, found, instance.id, "accounting.bookings", "connector.other", by=WHO
        )
    with pytest.raises(DomainRefused, match=r"asks for no capability 'crm\.contacts'"):
        await domains.answer(TENANT, found, instance.id, "crm.contacts", None, by=WHO)
    instance = await domains.answer(TENANT, found, instance.id, "accounting.bookings", None, by=WHO)
    binding = instance.binding("accounting.bookings")
    assert binding is not None and binding.adapter is None, "the organisation has no such tool"
    with pytest.raises(DomainRefused, match="not an identity of the tenant"):
        await domains.name_owner(TENANT, instance.id, "idn_nobody")


async def test_a_process_left_out_is_not_proposed_and_a_refused_proposal_is_named() -> None:
    domains, proposed, _ = instances()
    found = admitted()
    instance = await domains.start(TENANT, found, by=WHO)
    await domains.answer(TENANT, found, instance.id, "accounting.bookings", None, by=WHO)
    await domains.name_owner(TENANT, instance.id, WHO)
    await domains.name_jurisdiction(TENANT, instance.id, "DE")
    with pytest.raises(DomainRefused, match="no process F-09"):
        await domains.leave_out(TENANT, found, instance.id, ["F-09"])
    proposed.refuse = ("the version '1' is registered already",)
    with pytest.raises(DomainRefused, match="F-01 is not proposed: the version"):
        await domains.propose(TENANT, found, instance.id, by=WHO)
    proposed.refuse = ()
    await domains.leave_out(TENANT, found, instance.id, ["F-01"])
    instance = await domains.propose(TENANT, found, instance.id, by=WHO)
    assert instance.proposed == () and proposed.made == []


async def test_a_later_version_is_offered_as_proposals_and_never_applied() -> None:
    domains, proposed, repository = instances()
    first = admitted(level=3)
    instance = await domains.start(TENANT, first, by=WHO)
    await domains.answer(TENANT, first, instance.id, "accounting.bookings", None, by=WHO)
    await domains.name_owner(TENANT, instance.id, WHO)
    await domains.name_jurisdiction(TENANT, instance.id, "DE")
    await domains.propose(TENANT, first, instance.id, by=WHO)

    unchanged = await domains.offer(TENANT, admitted(level=3, version="2"), instance.id, by=WHO)
    assert unchanged.proposed == () and len(proposed.made) == 1, "an unchanged bundle is kept"

    later = admitted(level=3, digest=OTHER, version="2")
    offer = await domains.offer(TENANT, later, instance.id, by=WHO)
    [made] = offer.proposed
    assert made.blueprint_version == "2" and made.digest == OTHER and made.level == 2
    assert len(proposed.made) == 2
    async with domains._work.transaction(TENANT):
        stored = await repository.get(TENANT, instance.id)
    assert stored is not None and stored.blueprint_version == "1", (
        "the instance keeps the version it was instantiated from"
    )


def test_the_runs_of_an_instance_are_counted_per_domain_without_rehearsals() -> None:
    found = admitted()
    instance = DomainInstance(
        id="dom_1",
        tenant=TENANT,
        created_at=FakeClock().now(),
        blueprint="books",
        blueprint_version="1",
        domain="finance",
        started_by=WHO,
        proposed=(
            {
                "process": "F-01",
                "process_id": "f-01",
                "version": "1",
                "proposal": "prp_1",
                "level": 2,
                "digest": DIGEST,
                "blueprint_version": found.blueprint.version,
            },
        ),
    )
    counted = rules.figures(
        instance,
        [
            ("f-01", "finished", False),
            ("f-01", "finished", False),
            ("f-01", "failed", False),
            ("f-01", "finished", True),
            ("other", "finished", False),
        ],
    )
    assert counted.domain == "finance" and counted.runs == 3
    [process] = counted.processes
    assert process.process_id == "f-01" and dict(process.by_state) == {"failed": 1, "finished": 2}
