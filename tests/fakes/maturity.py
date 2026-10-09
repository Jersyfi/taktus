"""A fake of the run's maturity port, and records of a verified adapter for tests that run on
real adapters.

`FakeMaturities` answers *verified* for every adapter except the ones it is told. `verified`
builds the record a conformance pass and a removal test that said `changed` would leave, for
the configuration the adapter declares — read from the adapter itself, the way the run reads it
(`Pools.configuration`), because a pass counts only for the configuration it names (ADR-0044).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fakes.model import FakeModel
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    Configuration,
    ConformanceResult,
    RemovalResult,
    Verdict,
)
from taktus.components.run.ports import Standing
from taktus.composition.pools import Pools

AT = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


class FakeMaturities:
    """Answers *verified* for every adapter but those in `below`, which it answers
    *experimental* with what they lack. Records what it was asked."""

    def __init__(self, below: Mapping[str, tuple[str, ...]] | None = None) -> None:
        self.below = dict(below or {})
        self.asked: list[str] = []

    async def standing(self, tenant: str, adapter: str) -> Standing:
        self.asked.append(adapter)
        if adapter in self.below:
            return Standing(adapter=adapter, maturity="experimental", missing=self.below[adapter])
        return Standing(adapter=adapter, maturity="verified")


VERIFIED = FakeMaturities()
"""For tests of the engine's mechanics at level 3: no adapter is held back by its maturity."""


async def configurations(
    *,
    workers: Mapping[str, str] | None = None,
    connectors: Mapping[str, str] | None = None,
    models: Mapping[str, tuple[str, Sequence[str]]] | None = None,
) -> list[Configuration]:
    """What each adapter declares, read as the run reads it: workers by endpoint, connectors by
    MCP URL, models by (model name, purposes)."""
    found: list[Configuration] = []
    for adapter, endpoint in (workers or {}).items():
        async with HttpWorker(endpoint) as worker:
            pools = Pools(
                StaticWorkerPool([(adapter, worker)]), StaticConnectorPool([]), StaticModelPool()
            )
            configuration = await pools.configuration(adapter)
            assert configuration is not None
            found.append(configuration)
    for adapter, url in (connectors or {}).items():
        pools = Pools(
            StaticWorkerPool([]),
            StaticConnectorPool([(adapter, McpActionConnector(url))]),
            StaticModelPool(),
        )
        configuration = await pools.configuration(adapter)
        assert configuration is not None
        found.append(configuration)
    for adapter, (name, purposes) in (models or {}).items():
        pools = Pools(
            StaticWorkerPool([]),
            StaticConnectorPool([]),
            StaticModelPool([(adapter, tuple(purposes), FakeModel(), name)]),
        )
        configuration = await pools.configuration(adapter)
        assert configuration is not None
        found.append(configuration)
    return found


def verified(configuration: Configuration, tenant: str, at: datetime = AT) -> AdapterMaturity:
    """The record both halves of *verified* leave for the configuration: a conformance run that
    passed under it, and a removal test that said `changed`."""
    family = configuration.adapter.split(".", 1)[0]
    assert family in ("worker", "connector", "model")
    return AdapterMaturity(
        id=configuration.adapter,
        tenant=tenant,
        family=family,  # type: ignore[arg-type]  # checked above
        conformance=ConformanceResult(
            integration=configuration.adapter,
            family=family,  # type: ignore[arg-type]
            contract=f"{family}/v1",
            taktus_version="0.0.0",
            configuration=configuration,
            outcome="passed",
            digest="sha256:" + "0" * 64,
            tested_at=at,
            actor="idn_test",
        ),
        removal=RemovalResult(
            integration=configuration.adapter,
            family=family,  # type: ignore[arg-type]
            verdict=Verdict.CHANGED,
            tested_at=at,
            run_id="run_removal",
            configuration=configuration,
        ),
        updated_at=at,
    )


def write_verified(
    state_dir: Path, configurations: Sequence[Configuration], tenants: Sequence[str]
) -> None:
    """Write the records of `verified` into a state directory's snapshot, as the in-memory
    stores read it."""
    by_tenant = {
        tenant: [verified(c, tenant).document() for c in configurations] for tenant in tenants
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "adaptermaturity.json").write_text(json.dumps(by_tenant), encoding="utf-8")
