"""A shipped scaffold reaches production through SC-01, and a process furnishes a project through
the loopback connector (ADR-0308, UC-13.2).

SC-01 of `blueprints/method-scaffolds/` is registered as it is. Its step `advise` names the
development scaffold, so the scaffold's round runs on SC-01's evaluation cases, both sides as
rehearsals, with the check read through `orchestrator.scaffolds.check` from the fake repository
service. A person approves at SC-01's level 2, and the scaffold goes into production. Then
`orchestrator.scaffolds.furnish` creates the missing artifacts as one pull request, and a repeat
creates nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import composition.test_evaluations as ev
import composition.test_skills as sk
import pytest
import yaml
from taktus_connectors.github.server import Config, build_server

from taktus.adapters.driven.connectors.loopback import (
    ADAPTER as LOOPBACK,
)
from taktus.adapters.driven.connectors.loopback import (
    SCAFFOLD_CHECK,
    SCAFFOLD_FURNISH,
    LoopbackConnector,
)
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.catalog.domain.model import SkillError, SkillStage
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.composition.scaffolds import InstanceScaffolds, LoopbackScaffolds
from taktus.ports.connector import CallContext, CallFailed, Effect, idempotency_key
from taktus.ports.model import Completion, Prompt
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import PriceKinds

from .conftest import WRITE_CREDENTIAL, Service

ROOT = Path(__file__).resolve().parents[3]
SC01 = (
    ROOT
    / "blueprints"
    / "method-scaffolds"
    / "processes"
    / "SC-01-check-a-development-project.yaml"
)
REPOSITORY = "acme/scaffold-process"
SCAFFOLD = "development-scaffold"
TENANT = sk.TENANT
WHO = sk.WHO


@dataclass
class Advisor(ev.Speaker):
    """A model that follows the scaffold it is handed: with the development scaffold's
    instructions before its system text it names every artifact it was given; without, it says
    nothing useful."""

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        system = prompt.system or ""
        if "Development scaffold" in system:
            missing = prompt.user.split("Missing:", 1)[1].split("\n", 1)[0]
            titles = [t.strip(" '\"[]") for t in missing.split(",")]
            text = " ".join(f"{t}." for t in titles if t)
        else:
            text = "No."
        return Completion(
            text=text,
            model=self.name,
            tokens_in=3,
            tokens_out=3,
            by_kind=PriceKinds(input=3, output=3),
            finish="stop",
        )


def context(run: str) -> CallContext:
    return CallContext(
        tenant=TENANT,
        identity=WHO,
        run_id=run,
        step_id="furnish",
        attempt=1,
        idempotency_key=idempotency_key(run, "furnish", 1),
        credentials=(CredentialReference(name=WRITE_CREDENTIAL, injected_as="env"),),
    )


async def world_with_sc01(service: Service) -> tuple[sk.World, LoopbackConnector]:
    world = sk.World()
    world.model = Advisor()
    world.engine._models = ev.StaticModelPool(  # type: ignore[attr-defined]
        [("model.fake", ["drafting", "judging"], world.model, "fake-model@1")]
    )
    repository = McpActionConnector(
        build_server(Config(target=service.url, repository=REPOSITORY, timeout=5.0)),
        timeout=10.0,
    )
    loopback = LoopbackConnector()
    pool = StaticConnectorPool([(LOOPBACK, loopback), ("connector.repository", repository)])
    loopback.bind(scaffolds=LoopbackScaffolds(InstanceScaffolds(world.catalog, pool)))
    world.engine._connectors = pool  # type: ignore[attr-defined]
    await world.identity.directory.add(TENANT, WHO, (TENANT, "support"))
    bundle: dict[str, Any] = yaml.safe_load(SC01.read_text(encoding="utf-8"))
    await world.register.execute(RegisterProcessVersion(bundle, tenant=TENANT, by=WHO))
    return world, loopback


@pytest.mark.usefixtures("credentials")
async def test_the_development_scaffold_reaches_production_through_sc01_and_then_furnishes(
    service: Service,
) -> None:
    world, loopback = await world_with_sc01(service)
    _, refused = await world.lifecycle.register_directory(
        TENANT, ROOT / "scaffolds", "1.0.0", by=WHO
    )
    assert not refused
    scaffold_id = f"{SCAFFOLD}@1.0.0"
    assert [v.process_id for v in await world.lifecycle.using(TENANT, SCAFFOLD)] == ["sc-01"]

    # A draft is read by the check, through the loopback operation a process calls.
    checked = await loopback.call(
        SCAFFOLD_CHECK, context("scaffold-check-0001"), {"scaffold": SCAFFOLD, "branch": "main"}
    )
    assert checked.effect.kind is Effect.READ
    assert checked.output["stage"] == "draft"
    assert checked.output["missing"] == [
        "Use cases",
        "Architecture decisions",
        "Test strategy",
        "Definition of done",
    ]
    with pytest.raises(CallFailed) as early:
        await loopback.call(
            SCAFFOLD_FURNISH,
            context("scaffold-furnish-0001"),
            {"scaffold": SCAFFOLD, "branch": "main"},
        )
    assert "not_in_production" in early.value.error.detail

    # The same rounds and approval as a learned skill, on SC-01's cases.
    version = await world.round(scaffold_id)
    assert version.stage is SkillStage.EVALUATED, version.rounds
    assert version.rounds[0].dry_run is True
    with pytest.raises(SkillError):
        await world.lifecycle.approve(TENANT, scaffold_id, by=None)
    await world.lifecycle.approve(TENANT, scaffold_id, by=WHO)
    await world.lifecycle.look(TENANT)
    produced = await world.catalog.get(TENANT, scaffold_id)
    assert produced is not None and produced.stage is SkillStage.PRODUCTION
    handed = [p.system or "" for p in world.model.prompts]
    assert any("Development scaffold" in s for s in handed), "the round handed the scaffold over"

    furnished = await loopback.call(
        SCAFFOLD_FURNISH, context("scaffold-furnish-0002"), {"scaffold": SCAFFOLD, "branch": "main"}
    )
    assert furnished.effect.kind is Effect.WRITE and furnished.effect.replayed is False
    assert furnished.output["created"] == [
        "use-cases",
        "architecture-decisions",
        "test-strategy",
        "definition-of-done",
    ]
    assert furnished.output["pull_request"] is not None
    records = furnished.effect.records or ()
    assert records[0].kind == "vcs.pull_request"

    again = await loopback.call(
        SCAFFOLD_FURNISH, context("scaffold-furnish-0002"), {"scaffold": SCAFFOLD, "branch": "main"}
    )
    assert again.output["pull_request"] == furnished.output["pull_request"]
    assert service.state()[REPOSITORY]["pulls"] == 1, "a repeat creates nothing twice"
