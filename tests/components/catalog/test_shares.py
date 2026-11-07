"""An entry of the catalogue shared with circles: whole for its kind, visible inside its
circles and nowhere else, withdrawn only with its removal verdict known, and used with each
caller's own credential (ADR-0246, ADR-0247; UC-8.6, UC-8.8, UC-14.3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.catalog.application.service import CatalogueShares, ShareEntry
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    AgentCore,
    CallerCredential,
    CatalogueShare,
    CoreState,
    Grants,
    Origin,
    ProcessFinding,
    RemovalResult,
    ShareError,
    ShareKind,
    SkillFile,
    SkillOrigin,
    SkillOwnership,
    SkillStage,
    SkillVersion,
    Verdict,
)
from taktus.components.catalog.domain.model.skill import OriginKind
from taktus.components.catalog.domain.service import shares as rules
from taktus.components.ledger.application.service import ChainedLedger

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
TENANT = "acme"
SUPPORT = ("acme", "support")
SALES = ("acme", "sales")


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.maturities = MemoryRepository(self.persistence, AdapterMaturity)
        self.skills = MemoryRepository(self.persistence, SkillVersion)
        self.owners = MemoryRepository(self.persistence, SkillOwnership)
        self.cores = MemoryRepository(self.persistence, AgentCore)
        self.shares = CatalogueShares(
            MemoryRepository(self.persistence, CatalogueShare),
            MemoryRepository(self.persistence, CallerCredential),
            self.maturities,
            self.skills,
            self.owners,
            self.cores,
            self.persistence,
            self.ledger,
            self.clock,
        )

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [
                f"{e.kind}:{e.outcome}"
                for e in await self.ledger.entries(TENANT)
                if e.kind.startswith(("catalogue.", "credential."))
            ]

    async def put(self, repository: Any, item: Any) -> None:
        async with self.persistence.transaction(TENANT):
            await repository.put(TENANT, item)


def model(**changes: Any) -> ShareEntry:
    fields: dict[str, Any] = {
        "tenant": TENANT,
        "kind": ShareKind.MODEL,
        "subject": "model.local",
        "owner": "idn_owner",
        "purpose": "Drafts replies for the support team",
        "circles": ("acme/support",),
        "actor": "idn_owner",
        "location": "own",
        "cost_model": "per_hardware_time",
        "origin": Origin.PROVIDED,
    }
    fields.update(changes)
    return ShareEntry(**fields)


def skill(name: str, stage: SkillStage, *, owned: bool = False) -> SkillVersion:
    return SkillVersion(
        id=f"{name}@1",
        tenant=TENANT,
        name=name,
        version="1",
        file=SkillFile(name=name, description="d", digest="sha256:" + "b" * 64),
        origin=SkillOrigin(kind=OriginKind.OWN_USE if owned else OriginKind.BUNDLE),
        owned=owned,
        shared=owned,
        stage=stage,
        registered_at=AT,
    )


# --- a model entry ---------------------------------------------------------------------------


async def test_a_model_entry_missing_its_classification_or_cost_model_cannot_be_shared() -> None:
    world = World()
    with pytest.raises(ShareError) as refused:
        await world.shares.share(model(location=None, cost_model=None))
    assert refused.value.reason == "incomplete"
    assert "where it processes data" in str(refused.value)
    assert "cost model" in str(refused.value)
    with pytest.raises(ShareError) as trained:
        await world.shares.share(model(origin=Origin.TRAINED))
    assert "version" in str(trained.value) and "evaluation history" in str(trained.value)
    assert await world.kinds() == [
        "catalogue.share_refused:incomplete",
        "catalogue.share_refused:incomplete",
    ]


async def test_a_trained_model_enters_the_hub_with_its_version_owner_and_evaluations() -> None:
    world = World()
    share = await world.shares.share(
        model(
            subject="model.reply-clf",
            origin=Origin.TRAINED,
            version="sha256:" + "c" * 64,
            evaluations=("evl_held_out_1", "evl_held_out_2"),
        )
    )
    assert (share.owner, share.version, share.evaluations) == (
        "idn_owner",
        "sha256:" + "c" * 64,
        ("evl_held_out_1", "evl_held_out_2"),
    )
    assert await world.kinds() == ["catalogue.shared:shared"]


async def test_a_model_shared_with_one_team_is_unavailable_to_another() -> None:
    world = World()
    await world.shares.share(model())
    support = await world.shares.visible(TENANT, "idn_ann", SUPPORT)
    sales = await world.shares.visible(TENANT, "idn_bob", SALES)
    assert [s.id for s in support] == ["model:model.local"]
    assert sales == []
    assert await world.shares.admits(TENANT, ShareKind.MODEL, "model.local", "idn_ann", SUPPORT)
    assert not await world.shares.admits(TENANT, ShareKind.MODEL, "model.local", "idn_bob", SALES)
    assert await world.shares.admits(TENANT, ShareKind.MODEL, "model.other", "idn_bob", SALES), (
        "an entry with no share is the tenant's, as the operator configured it"
    )


async def test_a_circle_of_one_identity_admits_that_identity_alone() -> None:
    world = World()
    await world.shares.share(model(circles=("identity:idn_ann",)))
    assert await world.shares.visible(TENANT, "idn_ann", SUPPORT)
    assert not await world.shares.visible(TENANT, "idn_cid", SUPPORT)


async def test_nothing_is_shared_without_a_person_acting() -> None:
    world = World()
    with pytest.raises(ShareError) as refused:
        await world.shares.share(model(actor=None))
    assert refused.value.reason == "not_accepted"


# --- withdrawing -----------------------------------------------------------------------------


def removal(verdict: Verdict) -> AdapterMaturity:
    return AdapterMaturity(
        id="model.local",
        tenant=TENANT,
        family="model",
        removal=RemovalResult(
            integration="model.local",
            family="model",
            verdict=verdict,
            tested_at=AT,
            run_id="run_s01",
            processes=(
                ProcessFinding(process="replies@3", exercised="run", verdict=verdict, steps=()),
            ),
        ),
        updated_at=AT,
    )


async def test_a_withdrawal_takes_effect_only_with_its_removal_verdict_known() -> None:
    world = World()
    await world.shares.share(model())
    with pytest.raises(ShareError) as unknown:
        await world.shares.withdraw(TENANT, ShareKind.MODEL, "model.local", "idn_owner")
    assert unknown.value.reason == "no_verdict"
    await world.put(world.maturities, removal(Verdict.BROKE))
    with pytest.raises(ShareError) as broke:
        await world.shares.withdraw(TENANT, ShareKind.MODEL, "model.local", "idn_owner")
    assert broke.value.reason == "broke" and "replies@3" in str(broke.value)
    assert await world.shares.visible(TENANT, "idn_ann", SUPPORT), "still shared"
    withdrawn = await world.shares.withdraw(
        TENANT, ShareKind.MODEL, "model.local", "idn_owner", despite_broke=True
    )
    assert withdrawn.state == "withdrawn"
    assert not await world.shares.visible(TENANT, "idn_ann", SUPPORT)
    assert await world.kinds() == [
        "catalogue.shared:shared",
        "catalogue.share_refused:no_verdict",
        "catalogue.share_refused:broke",
        "catalogue.withdrawn:broke",
    ]


async def test_a_changed_verdict_withdraws_and_names_it() -> None:
    world = World()
    await world.shares.share(model())
    await world.put(world.maturities, removal(Verdict.CHANGED))
    await world.shares.withdraw(TENANT, ShareKind.MODEL, "model.local", "idn_owner")
    assert (await world.kinds())[-1] == "catalogue.withdrawn:changed"


# --- a skill and an agent --------------------------------------------------------------------


async def test_only_an_approved_skill_is_shared_and_appears_in_the_hub() -> None:
    world = World()
    await world.put(world.skills, skill("triage", SkillStage.EVALUATED))
    with pytest.raises(ShareError) as refused:
        await world.shares.share(
            ShareEntry(
                tenant=TENANT,
                kind=ShareKind.SKILL,
                subject="triage",
                owner="idn_owner",
                purpose="Sorts incoming tickets",
                circles=("acme/support",),
                actor="idn_owner",
            )
        )
    assert refused.value.reason == "not_approved"
    assert await world.shares.skill_hub(TENANT, "idn_ann", SUPPORT) == []
    await world.put(world.skills, skill("triage", SkillStage.PRODUCTION))
    await world.shares.share(
        ShareEntry(
            tenant=TENANT,
            kind=ShareKind.SKILL,
            subject="triage",
            owner="idn_owner",
            purpose="Sorts incoming tickets",
            circles=("acme/support",),
            actor="idn_owner",
        )
    )
    assert [v.id for v in await world.shares.skill_hub(TENANT, "idn_ann", SUPPORT)] == ["triage@1"]
    assert await world.shares.skill_hub(TENANT, "idn_bob", SALES) == []


async def test_a_skill_from_a_persons_own_use_is_shared_only_by_that_person() -> None:
    world = World()
    await world.put(world.skills, skill("my-notes", SkillStage.APPROVED, owned=True))
    await world.put(world.owners, SkillOwnership(id="my-notes@1", tenant=TENANT, owner="idn_ann"))
    entry = ShareEntry(
        tenant=TENANT,
        kind=ShareKind.SKILL,
        subject="my-notes",
        owner="idn_ann",
        purpose="Meeting notes in the team's form",
        circles=("acme/support",),
        actor="idn_admin",
    )
    with pytest.raises(ShareError) as refused:
        await world.shares.share(entry)
    assert refused.value.reason == "not_owner"
    shared = await world.shares.share(replace(entry, actor="idn_ann"))
    assert shared.shared_by == "idn_ann"


async def test_an_agent_is_shared_only_with_an_active_core() -> None:
    world = World()
    entry = ShareEntry(
        tenant=TENANT,
        kind=ShareKind.AGENT,
        subject="replies",
        owner="idn_owner",
        purpose="Answers late-parcel mail",
        circles=("acme/support",),
        actor="idn_owner",
    )
    with pytest.raises(ShareError) as refused:
        await world.shares.share(entry)
    assert refused.value.reason == "not_accepted"
    await world.put(
        world.cores,
        AgentCore(
            id="replies@1",
            tenant=TENANT,
            agent="replies",
            version="1",
            purpose="p",
            instructions="i",
            flow="replies",
            autonomy_level=2,
            grants=Grants(),
            state=CoreState.ACTIVE,
            proposed_at=AT,
        ),
    )
    assert (await world.shares.share(entry)).subject == "replies"


# --- a caller's own credential ---------------------------------------------------------------


async def test_a_shared_connector_names_each_callers_own_parameter_and_never_the_works() -> None:
    world = World()
    await world.shares.share(
        ShareEntry(
            tenant=TENANT,
            kind=ShareKind.CONNECTOR,
            subject="connector.tickets",
            owner="idn_admin",
            purpose="The ticket system",
            circles=("acme",),
            actor="idn_admin",
        )
    )
    await world.shares.bind_credential(TENANT, "idn_ann", "TICKETS_TOKEN", "ANN", "idn_admin")
    ann = await world.shares.caller_credentials(
        TENANT, "connector.tickets", "idn_ann", ["TICKETS_TOKEN"]
    )
    bob = await world.shares.caller_credentials(
        TENANT, "connector.tickets", "idn_bob", ["TICKETS_TOKEN"]
    )
    assert ann == rules.Resolved(names=("TICKETS_TOKEN_ANN",), lacking=())
    assert bob == rules.Resolved(names=(), lacking=("TICKETS_TOKEN",))
    unshared = await world.shares.caller_credentials(
        TENANT, "connector.other", "idn_bob", ["TICKETS_TOKEN"]
    )
    assert unshared is None, "an unshared connector names what its work names"
    assert "credential.bound:bound" in await world.kinds()


def test_use_is_counted_per_unit_and_only_the_viewers_own_calls_apart() -> None:
    calls = [
        rules.Call(run_id="r1", org_unit="acme/support", identity="idn_ann"),
        rules.Call(run_id="r2", org_unit="acme/support", identity="idn_cid"),
        rules.Call(run_id="r3", org_unit="acme/sales", identity="idn_bob"),
    ]
    seen = rules.use(calls, "idn_ann")
    assert seen.by_unit == {"acme/sales": 1, "acme/support": 2}
    assert (seen.own, seen.total) == (1, 3)
    assert "idn_cid" not in repr(seen) and "idn_bob" not in repr(seen)
