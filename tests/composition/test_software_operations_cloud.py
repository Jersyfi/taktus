"""The blueprint `software-operations` on a cloud's own services (ADR-0328): the metric bundles
read a named metric through the cloud operations connector, which maps it to PromQL over the
cloud's monitoring service, with no query of a store's language in the bundle or the run.

The world of `test_software_operations_repository.py`, with the member serving
`metrics.series` replaced by the cloud operations connector over the fake under
`tests/fakes/cloud_service.py`. What is faked: every system behind a connector.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any
from urllib.request import urlopen

import pytest
from fakes import cloud_service
from taktus_connectors.gcp.api import Config as CloudConfig
from taktus_connectors.gcp.server import build_server as cloud_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.domain.model import RunState

from .test_software_operations import TOKEN, Outside
from .test_software_operations import outside as outside
from .test_software_operations_repository import RepositoryWorld
from .test_software_operations_repository import cluster as cluster

EXECUTIONS = "cloudfunctions_googleapis_com:function_execution_count"
ERROR_RATE = (
    f'sum by (function_name) (rate({EXECUTIONS}{{status!="ok"}}[15m]))'
    f" / sum by (function_name) (rate({EXECUTIONS}[15m]))"
)


@pytest.fixture
def monitoring() -> Iterator[str]:
    server = cloud_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def asked(url: str) -> list[dict[str, Any]]:
    with urlopen(f"{url}/_fake/state") as response:  # noqa: S310 - the fake's own address
        found: list[dict[str, Any]] = json.load(response)["promql"]
        return found


class CloudWorld(RepositoryWorld):
    """The repository world whose `metrics.series` is the cloud's monitoring service."""

    def __init__(self, outside: Outside, cluster: str, monitoring: str) -> None:
        super().__init__(outside, cluster)
        pool = self.engine._connectors
        assert isinstance(pool, StaticConnectorPool)
        config = CloudConfig.at(
            "example", "", 5.0, monitoring, metrics={"functions.error_rate": ERROR_RATE}
        )
        cloud = McpActionConnector(cloud_server(config), timeout=10.0)
        pool._connectors[:] = [
            (name, cloud if name == "connector.metrics" else member)
            for name, member in pool._connectors
        ]

    async def ready(self) -> CloudWorld:
        await super().ready()
        return self


async def test_b_1_04_reads_the_named_error_rate_from_the_clouds_monitoring(
    outside: Outside, cluster: str, monitoring: str
) -> None:
    w = await CloudWorld(outside, cluster, monitoring).ready()
    run = await w.start(await w.registered("B-1.04-error-rate.yaml"))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    worst = await w.result(run, "worst")
    assert worst["first"]["labels"] == {"function_name": "function_a"}
    assert worst["first"]["values"][0]["value"] == 0.25, "a NaN is left out, never read as zero"
    assert asked(monitoring) == [{"kind": "query", "query": ERROR_RATE}]


async def test_a_name_the_tenant_did_not_map_fails_the_read_and_guesses_nothing(
    outside: Outside, cluster: str, monitoring: str
) -> None:
    w = await CloudWorld(outside, cluster, monitoring).ready()
    run = await w.start(await w.registered("B-2.03-quotas.yaml"))
    assert run.state is RunState.ESCALATED, run.state
    reason = run.step_run("read-quotas").reason or ""
    assert "quotas.used_share is not mapped" in reason
    assert asked(monitoring) == [], "nothing reached the monitoring service"
