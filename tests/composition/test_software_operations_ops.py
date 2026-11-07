"""The stage-one remainders of the blueprint `software-operations`, each registered as shipped
and run against fakes of the systems behind its capabilities (UC-03 §4.1, §4.2, §4.5, §4.7;
ADR-0201 to ADR-0204).

The world of `test_software_operations_repository.py`, with four more connectors wired as the
daemon wires them: a log store, a secret store, an app store's signing credentials and a model
provider's catalogue. What is faked: every system behind a connector (`tests/fakes/`).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import app_store_service, cost_report_service, log_store_service, secret_store_service
from taktus_connectors.anthropic.operations import Config as CatalogueConfig
from taktus_connectors.anthropic.server import build_server as catalogue_server
from taktus_connectors.appstore.operations import Config as StoreConfig
from taktus_connectors.appstore.server import build_server as store_server
from taktus_connectors.expiry.operations import Config as ExpiryConfig
from taktus_connectors.expiry.server import build_server as expiry_server
from taktus_connectors.loki.operations import Config as LogsConfig
from taktus_connectors.loki.server import build_server as logs_server
from taktus_connectors.vault.operations import Config as SecretsConfig
from taktus_connectors.vault.server import build_server as secrets_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.domain.model import RunState

from .test_software_operations import REPOSITORY, TOKEN, Outside
from .test_software_operations import outside as outside
from .test_software_operations_repository import RepositoryWorld
from .test_software_operations_repository import cluster as cluster

ERRORS = '{app="shop", level="error"}'


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


class Systems:
    def __init__(self, store_key: str) -> None:
        self.servers = [
            log_store_service.make_server("127.0.0.1", 0, {TOKEN}),
            secret_store_service.make_server("127.0.0.1", 0, {TOKEN}),
            app_store_service.make_server("127.0.0.1", 0, {store_key}),
            cost_report_service.make_server("127.0.0.1", 0, {TOKEN}),
        ]
        self.logs, self.secrets, self.store, self.models = [_serving(s) for s in self.servers]

    def value_reads(self) -> int:
        """How often the secret store was asked for a value."""
        return int(httpx.get(f"{self.secrets}/_fake/state", timeout=5).json()["value_reads"])

    def stop(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()


@pytest.fixture
def systems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Systems]:
    store_key = app_store_service.test_value()
    for name, value in (
        ("LOGS_TOKEN", TOKEN),
        ("SECRETS_TOKEN", TOKEN),
        ("MODELS_TOKEN", TOKEN),
        ("STORE_API_KEY", store_key),
    ):
        path = tmp_path / name
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    running = Systems(store_key)
    yield running
    running.stop()


class OpsWorld(RepositoryWorld):
    """The repository world, with the log store, the secret store, the app store and the model
    provider's catalogue served as the daemon serves them."""

    def __init__(self, outside: Outside, cluster: str, systems: Systems) -> None:
        super().__init__(outside, cluster)
        pool = self.engine._connectors
        assert isinstance(pool, StaticConnectorPool)

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        pool._connectors.extend(
            [
                ("connector.logs", served(logs_server(LogsConfig(systems.logs, timeout=5.0)))),
                (
                    "connector.secrets",
                    served(secrets_server(SecretsConfig(systems.secrets, timeout=5.0))),
                ),
                ("connector.store", served(store_server(StoreConfig(systems.store, 5.0)))),
                (
                    "connector.expiry",
                    served(
                        expiry_server(
                            ExpiryConfig(
                                frozenset({("127.0.0.1", outside.tls.port)}),
                                outside.rdap,
                                outside.tls.ca_file,
                                timeout=5.0,
                            )
                        )
                    ),
                ),
                (
                    "connector.catalogue",
                    served(catalogue_server(CatalogueConfig(systems.models, timeout=5.0))),
                ),
            ]
        )

    async def ready(self) -> OpsWorld:
        await super().ready()
        return self


def rolled(cluster: str, ago: timedelta) -> None:
    """The cluster's deployments last rolled out `ago` before now."""
    moment = (datetime.now(UTC) - ago).strftime("%Y-%m-%dT%H:%M:%SZ")
    httpx.post(f"{cluster}/_fake/rollout", json={"rolled_at": moment}, timeout=5).raise_for_status()


def fake(outside: Outside, path: str, body: dict[str, Any]) -> Any:
    answer = httpx.post(
        f"{outside.repository}{path}", json={"repository": REPOSITORY, **body}, timeout=5
    )
    answer.raise_for_status()
    return answer.json()


def failed(run: Any) -> list[tuple[str, Any]]:
    return [(s.step_id, s.reason) for s in run.step_runs if s.reason]


# --- B-1.04, B-5.02: errors from the log ---------------------------------------------------------


async def test_b_1_04_counts_the_errors_logged_since_the_last_deployment(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    version = await w.registered("B-1.04-error-rate.yaml")
    rolled(cluster, timedelta(hours=1))
    run = await w.start(version, query="up", deployment="web", error_filter=ERRORS)
    assert run.state is RunState.FINISHED, failed(run)
    deployment = await w.result(run, "read-deployment")
    assert deployment["output"]["changed_at"].endswith("Z")
    since = await w.result(run, "since-deployment")
    assert since["count"] == 2, "the fake logged two errors of the shop in its last minutes"
    assert {e["severity"] for e in since["items"]} == {"error"}

    rolled(cluster, timedelta(seconds=0))
    fresh = await w.start(version, query="up", deployment="web", error_filter=ERRORS)
    assert fresh.state is RunState.FINISHED, failed(fresh)
    assert (await w.result(fresh, "since-deployment"))["count"] == 0, "none since a release now"


async def test_b_1_04_without_a_deployment_skips_the_tie(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    run = await w.start(await w.registered("B-1.04-error-rate.yaml"), query="up")
    assert run.state is RunState.FINISHED, failed(run)
    for step in ("read-deployment", "read-errors-since", "since-deployment"):
        assert (await w.result(run, step))["skipped"] is True


async def test_b_5_02_reads_the_back_office_error_log(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    version = await w.registered("B-5.02-back-office-health.yaml")
    run = await w.start(version, path="/health", max_duration_ms=5000, log_filter=ERRORS)
    assert run.state is RunState.FINISHED, failed(run)
    assert (await w.result(run, "log-errors"))["count"] == 2
    assert (await w.result(run, "failures"))["count"] == 0


# --- B-1.13: a removal with its remaining calls ------------------------------------------------


async def test_b_1_13_files_the_removal_with_its_remaining_calls_once(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    version = await w.registered("B-1.13-superseded-code.yaml")
    inputs = {"endpoint": "/v1/orders", "calls_filter": '{app="shop"} |= "order"', "label": "ready"}
    before = len(outside.issues())
    run = await w.start(version, **inputs)
    assert run.state is RunState.WAITING_HUMAN, "at level 2 nothing starts before a person"
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, failed(run)
    assert (await w.result(run, "remaining"))["count"] == 5, "five lines of the shop name an order"
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert filed["title"] == "Remove the deprecated endpoint /v1/orders"
    assert "holds 5 calls" in filed["body"] and "removal:/v1/orders" in filed["body"]
    assert [label["name"] for label in filed["labels"]] == ["ready"]

    again = await w.confirmed(await w.start(version, **inputs))
    assert again.state is RunState.FINISHED, failed(again)
    assert (await w.result(again, "unfiled"))["count"] == 0, "filed once, never twice"
    assert len(outside.issues()) == before + 1


# --- B-1.10: a secret due for rotation -----------------------------------------------------------


async def test_b_1_10_prepares_the_rotation_of_the_oldest_secret_and_reads_no_value(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    version = await w.registered("B-1.10-rotation-watch.yaml")
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version))
    assert run.state is RunState.FINISHED, failed(run)
    selected = (await w.result(run, "select"))["first"]
    # The fake's current values: app/db 90 days old, ci/deploy/token 365, the others younger.
    assert selected["name"] == "ci/deploy/token" and selected["age_days"] in (364, 365)
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert filed["title"] == "ci/deploy/token"
    assert f"secret-rotation:ci/deploy/token:{selected['changed_at']}" in filed["body"]
    assert systems.value_reads() == 0, "no value is ever read (ADR-0203)"

    again = await w.confirmed(await w.start(version))
    assert (await w.result(again, "select"))["first"]["name"] == "app/db", "the next one due"


# --- B-1.09: signing credentials -----------------------------------------------------------------


async def test_b_1_09_takes_the_signing_credential_that_expires_first(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    version = await w.registered("B-1.09-expiry.yaml")
    run = await w.start(
        version,
        host="127.0.0.1",
        port=outside.tls.port,
        domain="example-product.test",
        signing="yes",
    )
    assert run.state is RunState.FINISHED, failed(run)
    first = (await w.result(run, "soonest-signing"))["first"]
    # The fake's certificate CERT0002 expired ten days ago; the invalid profile is left out.
    assert first["id"] == "CERT0002" and first["days_left"] < 0
    assert first["key"].startswith("credential:certificate:CERT0002:")


# --- B-1.11: an advisory as a goal ---------------------------------------------------------------


async def test_b_1_11_files_a_fixed_advisory_as_the_update_goal_once(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    fake(outside, "/_fake/alert", {"package": "requests", "patched": "2.32.0", "severity": "high"})
    fake(outside, "/_fake/alert", {"package": "leftpad", "severity": "critical"})
    version = await w.registered("B-1.11-advisories.yaml")
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version))
    assert run.state is RunState.FINISHED, failed(run)
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert filed["title"].startswith("Update requests to 2.32.0 (GHSA-")
    assert "version it is on" in filed["body"] and "update stays with a person" in filed["body"]
    assert [label["name"] for label in filed["labels"]] == ["ready"]
    again = await w.confirmed(await w.start(version))
    assert (await w.result(again, "select"))["count"] == 0, "an alert without a fix is not filed"


# --- B-1.12: a lost run restarted ----------------------------------------------------------------


async def test_b_1_12_cancels_and_reruns_a_lost_run_once_a_person_confirmed(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    lost = fake(
        outside, "/_fake/run", {"branch": "main", "status": "in_progress", "minutes_ago": 180}
    )
    fake(outside, "/_fake/runner", {"name": "build-1", "status": "offline"})
    version = await w.registered("B-1.12-pipeline-runs.yaml")
    run = await w.start(version)
    assert run.state is RunState.WAITING_HUMAN
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, failed(run)
    assert (await w.result(run, "running-too-long"))["first"]["id"] == str(lost["id"])
    assert (await w.result(run, "cancel-lost"))["output"]["cancelled"] is True
    rerun = (await w.result(run, "rerun-lost"))["output"]
    assert rerun["rerun"] is True and rerun["attempt"] == 2
    assert (await w.result(run, "runners-offline"))["count"] == 1


# --- B-2.03, B-7.10: the repository's own limits and branches -----------------------------------


async def test_b_2_03_takes_the_fullest_of_the_repository_services_limits(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    run = await w.start(await w.registered("B-2.03-quotas.yaml"), query="quota_used_ratio")
    assert run.state is RunState.FINISHED, failed(run)
    fullest = (await w.result(run, "fullest-repository-limit"))["first"]
    assert fullest["resource"] == "core" and fullest["used_share"].startswith("0.")


async def test_b_7_10_counts_a_branch_without_a_pull_request(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    head = outside.send("GET", f"/repos/{REPOSITORY}/git/ref/heads/main")["object"]["sha"]
    outside.send("POST", f"/repos/{REPOSITORY}/git/refs", {"ref": "refs/heads/left", "sha": head})
    run = await w.start(await w.registered("B-7.10-abandoned-work.yaml"))
    assert run.state is RunState.FINISHED, failed(run)
    branches = await w.result(run, "abandoned-branches")
    assert [b["name"] for b in branches["items"]] == ["left"], "main is no work"


# --- B-2.04: a retired model in use --------------------------------------------------------------


async def test_b_2_04_files_the_models_in_use_the_provider_retires_once(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await OpsWorld(outside, cluster, systems).ready()
    version = await w.registered("B-2.04-retired-models.yaml")
    models = [
        "claude-opus-5-5",
        "claude-example-deprecated",
        "claude-example-retired",
        "gone-model",
    ]
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version, models=models, label="ready"))
    assert run.state is RunState.FINISHED, failed(run)
    assert (await w.result(run, "retiring"))["extracted"] == [
        "claude-example-deprecated",
        "claude-example-retired",
        "gone-model",
    ]
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert filed["title"] == "Switch the models the provider retires"
    assert "claude-opus-5-5" not in filed["body"].split("current:")[0]
    again = await w.confirmed(await w.start(version, models=models, label="ready"))
    assert (await w.result(again, "unfiled"))["count"] == 0, "filed once, never twice"
