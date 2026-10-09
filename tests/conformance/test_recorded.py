"""The conformance half of maturity, recorded by the instance that ran the suite (ADR-0044).

For each family the instance runs the suite against the endpoint its configuration resolves
for the adapter identifier, and records what it found: the reference worker, the reference
connector with its scenario against a fake of its service, and the model adapter against the
fake endpoint. A passing adapter is recorded as passed, under the configuration it declares.
The faults of the worker and the connector are recorded as not passed in
`test_worker_v1_faults.py` and `test_connector_v1_faults.py`; the model's are below.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import model_service

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models import OpenAiCompatibleModel, StaticModelPool
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import CONFORMANCE_TESTED
from taktus.components.catalog.domain.model import Maturity
from taktus.components.catalog.ports import NotConfigured, NotRunnable
from taktus.composition.pools import Pools

from .conftest import (
    Recorded,
    StartConnector,
    StartWorker,
    record,
    record_connector,
    record_worker,
)

LONG_ANSWER = " ".join(str(n) for n in range(1, 400))


def assert_passed(recorded: Recorded, contract: str, pending: set[str]) -> None:
    conformance = recorded.maturity.conformance
    assert conformance is not None, "the run is recorded"
    assert conformance.outcome == "passed", recorded.report["checks"]
    assert conformance.contract == contract and conformance.taktus_version
    assert conformance.failed == () and conformance.inconclusive == ()
    assert conformance.configuration == recorded.current, "the pass names what declared now"
    assert recorded.entry.kind == CONFORMANCE_TESTED and recorded.entry.outcome == "passed"
    assert recorded.entry.refs.actor == "idn_test"
    assert recorded.evidence["configuration"] == conformance.configuration.document()
    statuses = {c["id"]: c["status"] for c in recorded.report["checks"]}
    assert {c for c, s in statuses.items() if s == "pending"} == pending
    # The conformance half holds; *verified* waits for the removal half (#90).
    assert recorded.maturity.maturity(recorded.current) is Maturity.EXPERIMENTAL
    assert recorded.maturity.missing(recorded.current) == ("the removal test has not run",)


async def test_the_reference_worker_is_recorded_as_passed(
    start_worker: StartWorker, tmp_path: Path
) -> None:
    recorded = await record_worker(start_worker(), tmp_path)
    assert_passed(recorded, "worker/v1", {"W-12"})
    assert recorded.current is not None and "shell.script" in recorded.current.serves


async def test_the_reference_connector_is_recorded_as_passed(
    start_connector: StartConnector, tmp_path: Path
) -> None:
    recorded = await record_connector(start_connector(), tmp_path)
    assert_passed(recorded, "connector/v1", {"C-10"})
    assert recorded.current is not None and recorded.current.operations


async def test_a_connector_without_a_scenario_runs_nothing(
    start_connector: StartConnector, tmp_path: Path
) -> None:
    connector = start_connector()
    adapter = "connector.channel.repo"
    pools = Pools(
        StaticWorkerPool([]),
        StaticConnectorPool([(adapter, McpActionConnector(connector.endpoint))]),
        StaticModelPool(),
    )
    with pytest.raises(NotRunnable, match=r"SCENARIO.*sandbox"):
        await record(
            adapter,
            pools,
            {},
            connectors={"channel.repo": connector.endpoint},
            state_dir=tmp_path,
        )


async def test_what_has_no_suite_or_is_not_configured_runs_nothing(tmp_path: Path) -> None:
    empty = Pools(StaticWorkerPool([]), StaticConnectorPool([]), StaticModelPool())
    with pytest.raises(NotRunnable, match="no contract suite"):
        await record("persistence.database", empty, {}, state_dir=tmp_path)
    with pytest.raises(NotConfigured):
        await record("model.endpoint", empty, {}, state_dir=tmp_path)


# --- the model contract, against the fake endpoint ---------------------------------------------


@pytest.fixture
def endpoint() -> Iterator[tuple[str, model_service.Script]]:
    server, script = model_service.make_server("127.0.0.1", 0, answer=LONG_ANSWER)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}", script
    server.shutdown()


async def record_model(url: str, tmp_path: Path, *, name: str = "fake-model") -> Recorded:
    """The instance runs the model suite against `model.endpoint`, with the declaration its
    adapter makes: an upper-bound count, a hard output limit, billing per token."""
    model = OpenAiCompatibleModel(url, name, output_cap="hard")
    pools = Pools(
        StaticWorkerPool([]),
        StaticConnectorPool([]),
        StaticModelPool([("model.endpoint", ("*",), model, name)]),
    )
    return await record("model.endpoint", pools, {}, model_endpoint=url, state_dir=tmp_path)


async def test_the_model_adapter_is_recorded_as_passed(
    endpoint: tuple[str, model_service.Script], tmp_path: Path
) -> None:
    url, _ = endpoint
    recorded = await record_model(url, tmp_path)
    assert_passed(recorded, "model/v1", set())
    assert recorded.current is not None and recorded.current.version == "fake-model"


async def test_an_endpoint_that_ignores_the_limit_is_recorded_as_failing_m03(
    endpoint: tuple[str, model_service.Script], tmp_path: Path
) -> None:
    url, script = endpoint
    script.ignore_limit = True
    recorded = await record_model(url, tmp_path)
    conformance = recorded.maturity.conformance
    assert conformance is not None and conformance.outcome == "failed"
    assert conformance.failed == ("M-03",)
    assert "failed: M-03" in recorded.maturity.missing(recorded.current)[0]


async def test_an_endpoint_that_does_not_answer_is_recorded_as_not_passed(
    endpoint: tuple[str, model_service.Script], tmp_path: Path
) -> None:
    url, script = endpoint
    script.status = 500
    recorded = await record_model(url, tmp_path)
    conformance = recorded.maturity.conformance
    assert conformance is not None and not conformance.passed
    assert conformance.failed or conformance.inconclusive
    assert recorded.entry.outcome == conformance.outcome
