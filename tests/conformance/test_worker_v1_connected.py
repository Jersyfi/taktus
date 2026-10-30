"""The instance runs the worker suite over the control plane's own binding (ADR-0156 §5, #625).

A worker configured as connected is run against through the relay every instance shares, not
through an endpoint and not through a host the suite serves itself. The whole suite passes over
it, W-21 is judged from what the relay recorded, the record names the binding, and nothing of
the suite's requests is left in the relay afterwards.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from adapters.workers.test_connected import NAME, connected, hosting
from fakes.ports import free_port

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryRelay
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.workers.connected import connected_worker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import RunConformance, RunConformanceHandler
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.ledger.application.service import ChainedLedger
from taktus.composition.conformance import InstanceSuites, worker_suites
from taktus.composition.pools import Pools
from taktus.composition.settings import load_workers

from .conftest import CREDENTIAL, HOST, TASK

ADAPTER = f"worker.{NAME}"


async def test_the_instance_runs_the_suite_over_its_binding_and_records_the_binding(
    tmp_path: Path,
) -> None:
    from taktus.adapters.driven.clock import SystemClock
    from taktus.adapters.driven.memory import (
        MemoryLedgerStore,
        MemoryObjectStore,
        MemoryPersistence,
        MemoryRepository,
    )

    relay = MemoryRelay()
    key_file = tmp_path / "connect.key"
    key_file.write_text("k-site")
    task = tmp_path / "task.json"
    task.write_text(json.dumps(TASK), encoding="utf-8")
    value = "conf-" + secrets.token_hex(12)
    environment = {
        "TAKTUS_WORKERS": NAME,
        f"TAKTUS_WORKER_{NAME.upper()}_EXECUTION": "connected",
        f"TAKTUS_WORKER_{NAME.upper()}_CONNECT_KEY_FILE": str(key_file),
        "TAKTUS_CONFORMANCE_WORKER_TASK": str(task),
        "TAKTUS_CONFORMANCE_WORKER_HOSTS": HOST,
        "TAKTUS_CONFORMANCE_WORKER_CREDENTIAL": CREDENTIAL,
        "TAKTUS_CREDENTIAL_" + CREDENTIAL.upper(): value,
        "TAKTUS_CONFORMANCE_TIMEOUT": "90",
        "TAKTUS_CONFORMANCE_IDLE_TIMEOUT": "30",
    }
    configuration = EnvironmentConfiguration(environment)
    configured = load_workers(configuration)
    async with hosting(relay, {NAME: "k-site"}, free_port()) as base:
        with connected(
            base, tmp_path, "k-site", "--step-seconds", "0.2", env={CREDENTIAL: value}
        ) as log:
            async with connected_worker(relay, ADAPTER) as worker:
                pools = Pools(
                    StaticWorkerPool([(ADAPTER, worker)], connected=frozenset({ADAPTER})),
                    StaticConnectorPool([]),
                    StaticModelPool(),
                )
                clock = SystemClock()
                persistence = MemoryPersistence()
                objects = MemoryObjectStore()
                handler = RunConformanceHandler(
                    InstanceSuites(
                        pools=pools,
                        settings=configuration,
                        workers=worker_suites(
                            configured, configuration, state_dir=tmp_path, relay=relay
                        ),
                        connectors={},
                        model_endpoint=None,
                    ),
                    MemoryRepository(persistence, AdapterMaturity),
                    persistence,
                    ChainedLedger(MemoryLedgerStore(persistence), clock),
                    objects,
                    clock,
                )
                _, entry = await handler.execute(RunConformance(ADAPTER, "t", actor="idn_test"))
                assert entry.content_digest is not None
                evidence = json.loads(await objects.get(entry.content_digest) or b"{}")
            assert value not in log.read_text()
    report = evidence["report"]
    statuses = {c["id"]: c["status"] for c in report["checks"]}
    assert [c for c in report["checks"] if c["status"] == "failed"] == [], report
    assert statuses["W-21"] == "passed", "judged from what the relay recorded"
    assert statuses["W-19"] == "passed" and statuses["W-01"] == "passed"
    assert "outbound binding" in report["endpoint"]
    assert evidence["configuration"]["binding"] == "outbound", "the record names the binding"
    assert value not in json.dumps(evidence)
    assert await relay.take(ADAPTER) is None, "nothing of the suite is left in the relay"
