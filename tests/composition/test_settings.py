"""The daemon's settings: every TAKTUS_* variable validated at startup with a message naming
the variable, and the effective configuration logged with every secret masked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.composition import logging as daemon_logging
from taktus.composition.settings import (
    ALL_ROLES,
    ExecutionKind,
    Role,
    Settings,
    WorkerConfiguration,
    load,
    normalise_prefix,
)
from taktus.ports.configuration import ConfigurationError, Secret

URL = "postgresql://taktus:hunter2-the-password@db.internal:5432/taktus"


def settings(**environment: str) -> Settings:
    return load(
        EnvironmentConfiguration({"TAKTUS_DATABASE_URL": URL, **environment}),
        default_instance="host-1",
    )


def test_defaults_are_the_self_hosting_shape() -> None:
    loaded = settings()
    assert loaded.roles == ALL_ROLES
    assert loaded.http_host == "127.0.0.1" and loaded.http_port == 8080
    assert loaded.path_prefix == "/"
    assert loaded.tenants == ("default",)
    assert loaded.instance == "host-1"
    assert loaded.migrate_on_start is False
    assert loaded.connectors == {}
    assert loaded.model.endpoint is None and loaded.model.purposes == ("*",)
    assert loaded.database.reveal() == URL
    assert loaded.database_source == "environment"


def test_every_setting_is_read_from_its_variable(tmp_path: Path) -> None:
    secret_file = tmp_path / "url"
    secret_file.write_text(URL + "\n", encoding="utf-8")
    loaded = load(
        EnvironmentConfiguration(
            {
                "TAKTUS_DATABASE_URL_FILE": str(secret_file),
                "TAKTUS_ROLES": "runner, api",
                "TAKTUS_MIGRATE_ON_START": "true",
                "TAKTUS_HTTP_HOST": "0.0.0.0",  # noqa: S104 — a value under test, not a bind
                "TAKTUS_HTTP_PORT": "9000",
                "TAKTUS_PATH_PREFIX": "/taktus/",
                "TAKTUS_WORKER": "http://worker:9000/",
                "TAKTUS_EXECUTION": "process",
                "TAKTUS_EXECUTION_UNIT": "python3 worker.py",
                "TAKTUS_EXECUTION_MEMORY_MB": "256",
                "TAKTUS_EXECUTION_WALL_SECONDS": "120",
                "TAKTUS_CONNECTORS": "channel.repo=http://connector:9100/mcp",
                "TAKTUS_MODEL_ENDPOINT": "http://models:8000/v1",
                "TAKTUS_MODEL_NAME": "local-model",
                "TAKTUS_MODEL_PURPOSES": "reasoning,triage",
                "TAKTUS_STATE_DIR": str(tmp_path / "state"),
                "TAKTUS_TENANTS": "default,acme",
                "TAKTUS_INSTANCE": "runner-7",
                "TAKTUS_SHUTDOWN_CEILING_SECONDS": "30",
                "TAKTUS_LEASE_SECONDS": "10",
                "TAKTUS_POLL_SECONDS": "0.2",
                "TAKTUS_RUNNER_CONCURRENCY": "2",
                "TAKTUS_LIVE_STREAMS": "7",
                "TAKTUS_LOG_LEVEL": "DEBUG",
            }
        ),
        default_instance="unused",
    )
    assert loaded.roles == {Role.RUNNER, Role.API}
    assert loaded.database_source == f"file {secret_file}"
    assert loaded.migrate_on_start is True
    assert (loaded.http_host, loaded.http_port) == ("0.0.0.0", 9000)  # noqa: S104
    assert loaded.path_prefix == "/taktus"
    (worker,) = loaded.workers
    assert worker.name is None and worker.identifier == "worker.process"
    assert worker.execution.endpoint == "http://worker:9000"
    assert worker.execution.kind is ExecutionKind.PROCESS
    assert worker.execution.unit == "python3 worker.py"
    assert (worker.execution.memory_mb, worker.execution.wall_seconds) == (256, 120)
    assert loaded.connectors == {"channel.repo": "http://connector:9100/mcp"}
    assert loaded.model.endpoint == "http://models:8000/v1" and loaded.model.name == "local-model"
    assert loaded.model.purposes == ("reasoning", "triage") and loaded.model.credential is None
    assert loaded.state_dir == tmp_path / "state"
    assert loaded.tenants == ("default", "acme")
    assert loaded.instance == "runner-7"
    assert loaded.shutdown_ceiling_seconds == 30 and loaded.lease_seconds == 10
    assert loaded.poll_seconds == 0.2 and loaded.runner_concurrency == 2
    assert loaded.live_streams == 7
    assert loaded.log_level == "debug"


@pytest.mark.parametrize(
    ("variable", "value", "words"),
    [
        ("TAKTUS_ROLES", "api,cook", "not a role"),
        ("TAKTUS_ROLES", "api,,runner", "empty entry"),
        ("TAKTUS_MIGRATE_ON_START", "maybe", "not true or false"),
        ("TAKTUS_HTTP_PORT", "http", "not a whole number"),
        ("TAKTUS_HTTP_PORT", "70000", "between 1 and 65535"),
        ("TAKTUS_PATH_PREFIX", "taktus", "must start with /"),
        ("TAKTUS_PATH_PREFIX", "/a//b", "empty segment"),
        ("TAKTUS_PATH_PREFIX", "/a/../b", "empty segment, or one that is . or .."),
        ("TAKTUS_PATH_PREFIX", "/a b", "no space"),
        ("TAKTUS_WORKER", "worker:9000", "not an http(s) URL"),
        ("TAKTUS_EXECUTION", "pod", "not one of endpoint, process, container"),
        ("TAKTUS_EXECUTION_MEMORY_MB", "8", "at least 16"),
        ("TAKTUS_EXECUTION_MEMORY_UNENFORCED", "perhaps", "not true or false"),
        ("TAKTUS_CAPACITY_STORAGE_WARN_PERCENT", "100", "between 0.1 and 99.0"),
        ("TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT", "12", "a person is told before work is refused"),
        ("TAKTUS_CAPACITY_STORAGE_EXPANDABLE", "sometimes", "not true or false"),
        ("TAKTUS_CAPACITY_INTERVAL_SECONDS", "5", "at least 60"),
        ("TAKTUS_CAPACITY_DATABASE_VOLUME_MB", "twenty", "not a whole number"),
        ("TAKTUS_CONNECTORS", "channel.repo", "capability=url"),
        ("TAKTUS_CONNECTORS", "Repo=http://x", "not a capability"),
        ("TAKTUS_CONNECTORS", "channel.repo=ftp://x", "not an http(s) URL"),
        ("TAKTUS_CONNECTORS", "channel.repo=http://x,channel.repo=http://y", "mapped twice"),
        ("TAKTUS_MODEL_ENDPOINT", "models:8000", "not an http(s) URL"),
        ("TAKTUS_TENANTS", "a,a", "names an entry twice"),
        ("TAKTUS_SHUTDOWN_CEILING_SECONDS", "0", "at least 1"),
        ("TAKTUS_LEASE_SECONDS", "1", "at least 5"),
        ("TAKTUS_POLL_SECONDS", "fast", "not a number"),
        ("TAKTUS_RUNNER_CONCURRENCY", "-1", "at least 1"),
        ("TAKTUS_LIVE_STREAMS", "0", "at least 1"),
        ("TAKTUS_LOG_LEVEL", "loud", "not one of"),
    ],
)
def test_a_wrong_setting_names_its_variable(variable: str, value: str, words: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        settings(**{variable: value})
    assert raised.value.setting == variable
    assert str(raised.value).startswith(variable + ": ")
    assert words in str(raised.value)


def test_the_database_is_required_and_the_message_says_how_to_supply_it() -> None:
    with pytest.raises(ConfigurationError) as raised:
        load(EnvironmentConfiguration({}), default_instance="h")
    assert raised.value.setting == "TAKTUS_DATABASE_URL"
    assert "TAKTUS_DATABASE_URL_FILE" in str(raised.value)
    with pytest.raises(ConfigurationError, match="TAKTUS_DATABASE_URL: must start with"):
        load(EnvironmentConfiguration({"TAKTUS_DATABASE_URL": "mysql://x"}), default_instance="h")


def test_a_launching_execution_kind_needs_its_unit() -> None:
    with pytest.raises(ConfigurationError, match="TAKTUS_EXECUTION_UNIT: is not set") as raised:
        settings(TAKTUS_EXECUTION="container")
    assert "an image reference" in str(raised.value)
    with pytest.raises(ConfigurationError, match="TAKTUS_MODEL_NAME: is not set"):
        settings(TAKTUS_MODEL_ENDPOINT="http://models:8000/v1")


def test_the_prefix_is_normalised() -> None:
    assert normalise_prefix("/", "X") == "/"
    assert normalise_prefix("/taktus/", "X") == "/taktus"
    assert normalise_prefix("/a/b", "X") == "/a/b"


def test_the_effective_configuration_masks_every_secret() -> None:
    loaded = settings(TAKTUS_ROLES="scheduler")
    effective = dict(loaded.effective())
    assert effective["TAKTUS_DATABASE_URL"] == "*** (from environment)"
    assert effective["TAKTUS_ROLES"] == "scheduler"
    assert "hunter2" not in json.dumps(effective)
    assert set(effective) == {name for name, _ in loaded.effective()}
    assert len(effective) == 61, "every setting is in the startup log"


def test_no_secret_value_reaches_a_log_line() -> None:
    """End to end: the settings are logged through the daemon's own processor chain — the
    renderer that writes the line — and the password is not in what comes out. A second line
    logs the secret object itself as a value, which is the mistake the type guards against."""
    loaded = settings()
    lines: list[str] = []
    structlog.configure(
        processors=daemon_logging.processors(),
        wrapper_class=structlog.make_filtering_bound_logger(0),
        logger_factory=lambda *_: _Capture(lines),
        cache_logger_on_first_use=False,
    )
    try:
        daemon_logging.log_effective_configuration(loaded)
        structlog.get_logger("test").info(
            "careless", database=loaded.database, url=[loaded.database]
        )
    finally:
        structlog.reset_defaults()
    assert len(lines) == 2
    for line in lines:
        assert "hunter2" not in line
        assert "***" in line
        json.loads(line)  # one JSON object per line
    assert '"TAKTUS_DATABASE_URL": "*** (from environment)"' in lines[0]


class _Capture:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def msg(self, message: str) -> None:
        self._lines.append(message)

    debug = info = warning = error = critical = msg


def test_the_budget_settings_are_validated_and_the_price_table_read(tmp_path: Path) -> None:
    from taktus.composition.settings import load_budget

    table = tmp_path / "prices.json"
    table.write_text(
        '{"version": "t-1", "valid_from": "2026-09-30T00:00:00Z", "currency": "usd", '
        '"unit_tokens": 1000000, "source": "a test", "prices": {"m@1": {"input": 1.0}}}',
        encoding="utf-8",
    )
    budget = load_budget(EnvironmentConfiguration({"TAKTUS_PRICE_TABLE": str(table)}))
    assert budget.margin == 0.0 and budget.uncalibrated_margin == 1.0, "DEC-0034"
    loaded = budget.table()
    assert loaded is not None and loaded.version == "t-1"
    with pytest.raises(ConfigurationError, match="TAKTUS_BUDGET_MARGIN"):
        load_budget(EnvironmentConfiguration({"TAKTUS_BUDGET_MARGIN": "0.95"}))
    table.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="is not a price table"):
        load_budget(EnvironmentConfiguration({"TAKTUS_PRICE_TABLE": str(table)})).table()
    with pytest.raises(ConfigurationError, match="TAKTUS_MODEL_BILLING"):
        settings(TAKTUS_MODEL_BILLING="per_mood")


@pytest.mark.parametrize(
    ("uncalibrated_margin", "below"), [("0", True), ("0.05", True), ("0.1", False)]
)
def test_a_margin_below_the_floor_is_a_warning_at_startup(
    uncalibrated_margin: str, below: bool
) -> None:
    """The value holds (DEC-0047), and the startup log says so: a warning naming the value and
    the floor. At or above the floor, nothing is said."""
    loaded = settings(TAKTUS_BUDGET_UNCALIBRATED_MARGIN=uncalibrated_margin)
    assert loaded.budget.uncalibrated_margin == float(uncalibrated_margin), "the value holds"
    lines: list[str] = []
    structlog.configure(
        processors=daemon_logging.processors(),
        wrapper_class=structlog.make_filtering_bound_logger(0),
        logger_factory=lambda *_: _Capture(lines),
        cache_logger_on_first_use=False,
    )
    try:
        daemon_logging.log_effective_configuration(loaded)
    finally:
        structlog.reset_defaults()
    warnings = [json.loads(line) for line in lines if json.loads(line)["level"] == "warning"]
    if not below:
        assert warnings == []
        return
    (warning,) = warnings
    assert warning["TAKTUS_BUDGET_UNCALIBRATED_MARGIN"] == f"{float(uncalibrated_margin):g}"
    assert warning["floor"] == "0.1"
    assert "below the floor" in warning["event"]


def test_the_capacity_thresholds_are_named_settings_with_defaults() -> None:
    capacity = settings().capacity
    assert (capacity.storage_warn_percent, capacity.storage_refuse_percent) == (10.0, 2.0)
    assert (capacity.act_within_days, capacity.window_days) == (30, 14)
    assert (capacity.memory_warn_percent, capacity.cpu_warn_percent) == (10.0, 10.0)
    assert capacity.memory_reserve_mb == 256 and capacity.interval_seconds == 3600
    assert capacity.database_volume_mb is None, "not visible from the instance: told, or unknown"
    assert capacity.storage_expandable is None, "nobody has said"
    unenforced = settings().workers[0].execution.memory_unenforced
    assert unenforced is False, "an unenforced limit is refused"


def test_every_capacity_setting_is_read_from_its_variable() -> None:
    loaded = settings(
        TAKTUS_CAPACITY_STORAGE_WARN_PERCENT="15",
        TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT="3.5",
        TAKTUS_CAPACITY_ACT_WITHIN_DAYS="45",
        TAKTUS_CAPACITY_MEMORY_WARN_PERCENT="20",
        TAKTUS_CAPACITY_CPU_WARN_PERCENT="5",
        TAKTUS_CAPACITY_MEMORY_RESERVE_MB="512",
        TAKTUS_CAPACITY_WINDOW_DAYS="7",
        TAKTUS_CAPACITY_DATABASE_VOLUME_MB="20480",
        TAKTUS_CAPACITY_STORAGE_EXPANDABLE="false",
        TAKTUS_CAPACITY_INTERVAL_SECONDS="600",
        TAKTUS_EXECUTION_MEMORY_UNENFORCED="true",
    )
    capacity = loaded.capacity
    assert (capacity.storage_warn_percent, capacity.storage_refuse_percent) == (15.0, 3.5)
    assert (capacity.act_within_days, capacity.window_days) == (45, 7)
    assert (capacity.memory_warn_percent, capacity.cpu_warn_percent) == (20.0, 5.0)
    assert capacity.memory_reserve_mb == 512 and capacity.interval_seconds == 600
    assert capacity.database_volume_mb == 20480 and capacity.storage_expandable is False
    assert loaded.workers[0].execution.memory_unenforced is True
    effective = dict(loaded.effective())
    assert effective["TAKTUS_CAPACITY_STORAGE_EXPANDABLE"] == "false"
    assert effective["TAKTUS_EXECUTION_MEMORY_UNENFORCED"] == "true"


def test_the_cluster_kind_needs_its_namespace_and_reads_its_settings() -> None:
    with pytest.raises(ConfigurationError, match="TAKTUS_EXECUTION_NAMESPACE"):
        settings(TAKTUS_EXECUTION="cluster", TAKTUS_EXECUTION_UNIT="worker:1")
    execution = (
        settings(
            TAKTUS_EXECUTION="cluster",
            TAKTUS_EXECUTION_UNIT="worker:1",
            TAKTUS_EXECUTION_NAMESPACE="jobs",
            TAKTUS_EXECUTION_STATE_CLAIM="unit-state",
        )
        .workers[0]
        .execution
    )
    assert execution.kind is ExecutionKind.CLUSTER and execution.namespace == "jobs"
    assert execution.egress_enforced is True, "network policies are enforced unless told not"
    assert execution.state_claim == "unit-state" and execution.service_account is None
    off = (
        settings(
            TAKTUS_EXECUTION="cluster",
            TAKTUS_EXECUTION_UNIT="worker:1",
            TAKTUS_EXECUTION_NAMESPACE="jobs",
            TAKTUS_EXECUTION_EGRESS_ENFORCE="false",
        )
        .workers[0]
        .execution
    )
    assert off.egress_enforced is False


def test_findings_are_sent_only_where_the_operator_names_a_connector() -> None:
    """UC-6.12: an instance sends findings only where its operator enabled it."""
    assert settings().findings_connector is None
    enabled = settings(TAKTUS_FINDINGS_CONNECTOR="http://findings:9100/mcp/")
    assert enabled.findings_connector == "http://findings:9100/mcp"
    with pytest.raises(ConfigurationError, match="TAKTUS_FINDINGS_CONNECTOR"):
        settings(TAKTUS_FINDINGS_CONNECTOR="findings:9100")


def test_the_platform_and_what_each_credential_administers_are_read() -> None:
    """ADR-0052: one setting for the platform, one for every credential's declaration."""
    loaded = settings(
        TAKTUS_PLATFORM="integration",
        TAKTUS_ADMINISTERS="REPOSITORY_TOKEN=none, DEPLOY_KUBECONFIG=integration|other",
    ).administration
    assert loaded.platform == "integration"
    assert dict(loaded.declared) == {
        "REPOSITORY_TOKEN": (),
        "DEPLOY_KUBECONFIG": ("integration", "other"),
    }
    assert not settings().administration.checked


@pytest.mark.parametrize(
    "value",
    ["TOKEN", "TOKEN=", "=here", "TOKEN=a,TOKEN=b", "TOKEN=none|here", "TOKEN=a||b"],
)
def test_a_declaration_that_cannot_be_read_names_the_variable(value: str) -> None:
    with pytest.raises(ConfigurationError, match="TAKTUS_ADMINISTERS"):
        settings(TAKTUS_ADMINISTERS=value)


def test_one_worker_configured_as_before_is_the_only_one_and_keeps_its_identifier() -> None:
    """Issue #209: an instance that names no workers reads its one worker as it always has."""
    loaded = settings(TAKTUS_WORKER="http://worker:9000")
    (worker,) = loaded.workers
    assert worker.name is None and worker.identifier == "worker.endpoint"
    assert worker.execution.endpoint == "http://worker:9000"
    effective = dict(loaded.effective())
    assert "TAKTUS_WORKERS" not in effective
    assert effective["TAKTUS_WORKER"] == "http://worker:9000"


def test_several_workers_are_read_in_order_each_with_its_kind_and_what_it_needs() -> None:
    """Issue #209: each named worker reads its own settings first and the instance's otherwise;
    the order is the order a step is resolved in (ADR-0078)."""
    loaded = settings(
        TAKTUS_WORKERS="coding, coding-second, shell",
        TAKTUS_EXECUTION="cluster",
        TAKTUS_EXECUTION_NAMESPACE="jobs",
        TAKTUS_EXECUTION_MEMORY_MB="1024",
        TAKTUS_WORKER_CODING_EXECUTION_UNIT="coding:1",
        TAKTUS_WORKER_CODING_SECOND_EXECUTION_UNIT="coding-second:1",
        TAKTUS_WORKER_CODING_SECOND_EXECUTION_MEMORY_MB="2048",
        TAKTUS_WORKER_SHELL_EXECUTION="endpoint",
        TAKTUS_WORKER_SHELL_ENDPOINT="http://shell:9000/",
    )
    coding, second, shell = loaded.workers
    assert [w.identifier for w in loaded.workers] == [
        "worker.coding",
        "worker.coding-second",
        "worker.shell",
    ]
    assert coding.execution.kind is ExecutionKind.CLUSTER and coding.execution.unit == "coding:1"
    assert second.execution.unit == "coding-second:1"
    assert second.execution.namespace == "jobs", "the instance's setting is the default"
    assert (coding.execution.memory_mb, second.execution.memory_mb) == (1024, 2048)
    assert shell.execution.kind is ExecutionKind.ENDPOINT
    assert shell.execution.endpoint == "http://shell:9000"
    effective = dict(loaded.effective())
    assert effective["TAKTUS_WORKERS"] == "coding,coding-second,shell"
    assert effective["TAKTUS_WORKER_CODING_SECOND_EXECUTION_UNIT"] == "coding-second:1"
    assert effective["TAKTUS_WORKER_CODING_SECOND_EXECUTION_NAMESPACE"] == "jobs"
    assert effective["TAKTUS_WORKER_SHELL_ENDPOINT"] == "http://shell:9000"
    assert "TAKTUS_EXECUTION_UNIT" not in effective, "no worker is configured unnamed"


def test_a_named_worker_s_endpoint_and_unit_are_named_for_it() -> None:
    """Two workers at one endpoint are one worker: `TAKTUS_WORKER` is not a named worker's.
    A missing setting is reported under the worker's own variable."""
    with pytest.raises(ConfigurationError, match="TAKTUS_WORKER_SHELL_ENDPOINT"):
        settings(TAKTUS_WORKERS="shell", TAKTUS_WORKER="http://worker:9000")
    with pytest.raises(ConfigurationError, match="TAKTUS_WORKER_CODING_EXECUTION_UNIT"):
        settings(TAKTUS_WORKERS="coding", TAKTUS_EXECUTION="process")


@pytest.mark.parametrize("names", ["Coding", "coding_second", "coding-", "-a", "a,a", "a,,b"])
def test_a_worker_name_that_cannot_be_an_identifier_is_refused(names: str) -> None:
    with pytest.raises(ConfigurationError, match="TAKTUS_WORKERS"):
        settings(TAKTUS_WORKERS=names, TAKTUS_WORKER_A_ENDPOINT="http://a:1")


def test_a_named_worker_reads_only_its_own_credentials(tmp_path: Path) -> None:
    """Issue #209: two workers that reference the same credential name each receive the value
    configured for that worker; neither sees the other's, nor the instance's."""
    first, second, shared = tmp_path / "first", tmp_path / "second", tmp_path / "shared"
    first.write_text("first-value\n", encoding="utf-8")
    second.write_text("second-value\n", encoding="utf-8")
    shared.write_text("shared-value\n", encoding="utf-8")
    base = EnvironmentConfiguration(
        {
            "TAKTUS_WORKER_CODING_CREDENTIAL_AGENT_KEY_FILE": str(first),
            "TAKTUS_WORKER_CODING_SECOND_CREDENTIAL_AGENT_KEY_FILE": str(second),
            "TAKTUS_CREDENTIAL_VCS_TOKEN_FILE": str(shared),
            "TAKTUS_CONFORMANCE_WORKER_TASK": "/tasks/default.json",
            "TAKTUS_WORKER_CODING_SECOND_CONFORMANCE_WORKER_TASK": "/tasks/second.json",
        }
    )
    coding = WorkerConfiguration(base, "coding")
    other = WorkerConfiguration(base, "coding-second")
    assert _revealed(coding.secret("credential.agent_key")) == "first-value"
    assert _revealed(other.secret("credential.agent_key")) == "second-value"
    assert coding.secret("credential.vcs_token") is None, "the instance's is not the worker's"
    assert coding.name("credential.vcs_token") == "TAKTUS_WORKER_CODING_CREDENTIAL_VCS_TOKEN"
    assert coding.get("conformance.worker.task") == "/tasks/default.json"
    assert other.get("conformance.worker.task") == "/tasks/second.json"


def _revealed(secret: Secret | None) -> str | None:
    return None if secret is None else secret.reveal()
