"""What `taktusd` is told about itself: every setting, read through the configuration port,
validated once at startup.

A setting that is wrong is a `ConfigurationError` naming the variable and what to do — the
daemon prints that one sentence and exits, never a stack trace. `Settings.effective()` is what
the daemon logs at startup: every setting with its value, every secret masked, and for each
secret where it came from. Nothing here reads the environment directly; the configuration port
does, and a test hands in a mapping.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from taktus.components.run.domain.service import budget as budgeting
from taktus.ports.configuration import Configuration, ConfigurationError, Secret
from taktus.ports.model import PriceTable


class Role(StrEnum):
    """The four roles of docs/architecture/project-structure.md §5. `TAKTUS_ROLES=all` runs
    every one of them in one process — the self-hosting shape."""

    API = "api"
    RUNNER = "runner"
    SCHEDULER = "scheduler"
    AUTOMATION = "automation"


ALL_ROLES: frozenset[Role] = frozenset(Role)
DEFAULT_TENANT = "default"


class ExecutionKind(StrEnum):
    """How the control plane reaches an execution unit for `worker` steps (ADR-0002)."""

    ENDPOINT = "endpoint"
    """A worker that is already running, at `TAKTUS_WORKER`. Its isolation is whoever runs it."""
    PROCESS = "process"
    """A unit started per job as a child process of this one. No isolation; refused from
    autonomy level 3 upwards."""
    CONTAINER = "container"
    """A unit started per job in a container with limits, a memory-backed credential store
    and a network that reaches the allowed hosts and nothing else."""
    CLUSTER = "cluster"
    """A unit started per job as a Job in a cluster's execution namespace, with limits,
    credentials from a Secret that lives as long as the job, and an egress proxy of its own
    (deploy/k8s/README.md §7). The control plane runs in the same cluster."""


@dataclass(frozen=True)
class ExecutionSettings:
    kind: ExecutionKind
    endpoint: str
    """`TAKTUS_WORKER`: the base URL of the worker for kind `endpoint`."""
    unit: str | None
    """`TAKTUS_EXECUTION_UNIT`: what a launched unit is — a command line for `process`, an
    image reference for `container`. Required for those two kinds."""
    unit_port: int
    unit_state_dir: str
    cpus: float
    memory_mb: int
    wall_seconds: int
    start_timeout_seconds: int
    network: str | None
    """`TAKTUS_EXECUTION_NETWORK` (container): the network this process shares with the job's
    egress container — a control plane that itself runs in a container names its own network
    here. Unset, the egress container publishes the unit's port on 127.0.0.1 of the machine
    the engine runs on, which is where a control plane on a developer's machine reaches it."""
    engine_socket: str
    """`TAKTUS_EXECUTION_ENGINE_SOCKET` (container): the container engine's socket."""
    egress_image: str
    """`TAKTUS_EXECUTION_EGRESS_IMAGE` (container): the image the per-job egress container runs
    from; any image with `python3` on the path."""
    memory_unenforced: bool = False
    """`TAKTUS_EXECUTION_MEMORY_UNENFORCED` (process): accept that the memory limit is not
    enforced where the system cannot enforce it (every system but Linux). Off, the process
    adapter refuses such a job. The operator's explicit choice, shown in the startup log."""
    namespace: str | None = None
    """`TAKTUS_EXECUTION_NAMESPACE` (cluster): the execution namespace. Required for `cluster`."""
    egress_enforced: bool = True
    """`TAKTUS_EXECUTION_EGRESS_ENFORCE` (cluster): the operator's statement that the cluster
    enforces network policies. False refuses every job whose frame names hosts, and every job
    at autonomy level 3 or above (deploy/k8s/README.md §6)."""
    service_account: str | None = None
    """`TAKTUS_EXECUTION_SERVICE_ACCOUNT` (cluster): the account a job runs as — never Taktus's
    own. Unset, the namespace's default; no token is mounted either way."""
    state_claim: str | None = None
    """`TAKTUS_EXECUTION_STATE_CLAIM` (cluster): an existing volume claim in the execution
    namespace for the unit's state. Unset, the state dies with each job."""

    def effective(self) -> list[tuple[str, str]]:
        return [
            ("TAKTUS_EXECUTION", self.kind.value),
            ("TAKTUS_WORKER", self.endpoint),
            ("TAKTUS_EXECUTION_UNIT", self.unit or ""),
            ("TAKTUS_EXECUTION_UNIT_PORT", str(self.unit_port)),
            ("TAKTUS_EXECUTION_UNIT_STATE_DIR", self.unit_state_dir),
            ("TAKTUS_EXECUTION_CPUS", str(self.cpus)),
            ("TAKTUS_EXECUTION_MEMORY_MB", str(self.memory_mb)),
            ("TAKTUS_EXECUTION_WALL_SECONDS", str(self.wall_seconds)),
            ("TAKTUS_EXECUTION_START_TIMEOUT_SECONDS", str(self.start_timeout_seconds)),
            ("TAKTUS_EXECUTION_NETWORK", self.network or ""),
            ("TAKTUS_EXECUTION_ENGINE_SOCKET", self.engine_socket),
            ("TAKTUS_EXECUTION_EGRESS_IMAGE", self.egress_image),
            ("TAKTUS_EXECUTION_MEMORY_UNENFORCED", str(self.memory_unenforced).lower()),
            ("TAKTUS_EXECUTION_NAMESPACE", self.namespace or ""),
            ("TAKTUS_EXECUTION_EGRESS_ENFORCE", str(self.egress_enforced).lower()),
            ("TAKTUS_EXECUTION_SERVICE_ACCOUNT", self.service_account or ""),
            ("TAKTUS_EXECUTION_STATE_CLAIM", self.state_claim or ""),
        ]


@dataclass(frozen=True)
class TelemetrySettings:
    """Where spans go. Absent endpoint: spans are real and exported nowhere — the no-op is the
    export, so that trace identifiers still join ledger entries and log lines."""

    endpoint: str | None
    protocol: str
    """`grpc` or `http` (OTLP over HTTP/protobuf)."""
    headers: Secret | None
    """Headers the endpoint needs, `name=value` pairs separated by commas — a secret, because
    that is where an authorisation token goes: `TAKTUS_OTLP_HEADERS_FILE`."""
    headers_source: str | None
    service_name: str

    def effective(self) -> list[tuple[str, str]]:
        headers = "" if self.headers is None else f"{self.headers} (from {self.headers_source})"
        return [
            ("TAKTUS_OTLP_ENDPOINT", self.endpoint or ""),
            ("TAKTUS_OTLP_PROTOCOL", self.protocol),
            ("TAKTUS_OTLP_HEADERS", headers),
            ("TAKTUS_OTLP_SERVICE_NAME", self.service_name),
        ]

    def parsed_headers(self) -> dict[str, str]:
        if self.headers is None:
            return {}
        pairs = (p.partition("=") for p in self.headers.reveal().split(",") if p.strip())
        return {name.strip(): value.strip() for name, _, value in pairs if name.strip()}


def load_telemetry(configuration: Configuration) -> TelemetrySettings:
    """The telemetry settings alone: `taktusctl` reads them too."""
    reader = _Reader(configuration)
    endpoint = reader.text("otlp.endpoint", "") or None
    if endpoint is not None and not (
        endpoint.startswith("http://") or endpoint.startswith("https://")
    ):
        raise ConfigurationError(
            configuration.name("otlp.endpoint"), f"{endpoint!r} is not an http(s) URL"
        )
    return TelemetrySettings(
        endpoint=endpoint,
        protocol=reader.choice("otlp.protocol", "grpc", ("grpc", "http")),
        headers=configuration.secret("otlp.headers"),
        headers_source=configuration.source("otlp.headers"),
        service_name=reader.text("otlp.service.name", "taktus"),
    )


@dataclass(frozen=True)
class ModelSettings:
    """One model behind the chat-completions dialect, for every purpose it is configured for.
    Absent endpoint: no model, and an `llm` step fails naming the setting."""

    endpoint: str | None
    """`TAKTUS_MODEL_ENDPOINT`: the base URL that serves `/chat/completions`."""
    name: str
    """`TAKTUS_MODEL_NAME`: the model the endpoint is asked for; recorded as the adapter's
    version in the provenance of every answer."""
    purposes: tuple[str, ...]
    """`TAKTUS_MODEL_PURPOSES`: the purposes this model serves, `*` (the default) for all."""
    credential: Secret | None
    """`credential.model_api_key`: the bearer credential, from
    `TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE`; absent for an endpoint that needs none."""
    credential_source: str | None
    billing: str = "per_token"
    """`TAKTUS_MODEL_BILLING`: how the endpoint's provider bills — `per_token`, `per_window`
    (a share of a subscription's time window) or `per_hardware_time` (own hardware). It decides
    which budget can be enforced, and the run says so when its budget is set."""
    output_cap: str = "soft"
    """`TAKTUS_MODEL_OUTPUT_CAP`: whether the provider holds the output limit a call sets,
    reasoning included — `hard`, `soft` or `none`. `soft` unless the provider's terms say
    otherwise (docs/research/2026-09-30-what-providers-allow.md)."""
    provider_limit: str = "unknown"
    """`TAKTUS_MODEL_PROVIDER_LIMIT`: what the provider enforces itself over a month — `hard`,
    `alert`, `none`, `unknown`. Information only; Taktus never relies on it."""

    def effective(self) -> list[tuple[str, str]]:
        credential = "" if self.credential is None else f"*** (from {self.credential_source})"
        return [
            ("TAKTUS_MODEL_ENDPOINT", self.endpoint or ""),
            ("TAKTUS_MODEL_NAME", self.name),
            ("TAKTUS_MODEL_PURPOSES", ",".join(self.purposes)),
            ("TAKTUS_MODEL_BILLING", self.billing),
            ("TAKTUS_MODEL_OUTPUT_CAP", self.output_cap),
            ("TAKTUS_MODEL_PROVIDER_LIMIT", self.provider_limit),
            ("TAKTUS_CREDENTIAL_MODEL_API_KEY", credential),
        ]


@dataclass(frozen=True)
class BudgetSettings:
    """What a budget is held with: the price table money is computed at, and the named safety
    margin subtracted from every budget before the first step is admitted (ADR-0005)."""

    price_table: Path | None
    """`TAKTUS_PRICE_TABLE`: a file in the shape of `contracts/model/v1/Model.json#/$defs/
    PriceTable`. Absent: no model has a price, a currency budget cannot be converted, and the
    run says so when its budget is set."""
    margin: float
    """`TAKTUS_BUDGET_MARGIN`: the share of every limit held back from the first step on, 0 to
    0.9; nothing by default (DEC-0034: the margin belongs to a worker's estimate, not to the
    budget)."""
    uncalibrated_margin: float = 1.0
    """`TAKTUS_BUDGET_UNCALIBRATED_MARGIN`: what a worker with no calibration history reserves
    beyond its estimate — 1.0, twice the estimate, by default (DEC-0034). A value below the
    floor of 0.1 holds, and is said (`below_floor`, DEC-0047)."""

    def below_floor(self) -> str | None:
        """The warning the startup log carries when the uncalibrated margin is set below the
        floor; None at or above it (DEC-0047)."""
        return budgeting.below_floor(self.uncalibrated_margin)

    def table(self) -> PriceTable | None:
        """The price table the file holds, validated; None when none is configured."""
        if self.price_table is None:
            return None
        try:
            document = json.loads(self.price_table.read_text(encoding="utf-8"))
            return PriceTable.model_validate(document)
        except (OSError, ValueError) as error:
            raise ConfigurationError(
                "TAKTUS_PRICE_TABLE",
                f"{self.price_table} is not a price table (contracts/model/v1/Model.json#/$defs/"
                f"PriceTable): {str(error)[:200]}",
            ) from error

    def effective(self) -> list[tuple[str, str]]:
        return [
            ("TAKTUS_PRICE_TABLE", "" if self.price_table is None else str(self.price_table)),
            ("TAKTUS_BUDGET_MARGIN", f"{self.margin:g}"),
            ("TAKTUS_BUDGET_UNCALIBRATED_MARGIN", f"{self.uncalibrated_margin:g}"),
        ]


DEFAULT_MARGIN = 0.0
"""No share of the budget is held back by default: the safety margin is a worker's (DEC-0034)."""
DEFAULT_UNCALIBRATED_MARGIN = 1.0
"""100 % beyond the estimate for a worker nothing has measured yet (DEC-0034)."""


def load_budget(configuration: Configuration) -> BudgetSettings:
    reader = _Reader(configuration)
    table = reader.text("price.table", "") or None
    margin = reader.number("budget.margin", DEFAULT_MARGIN, low=0.0)
    if margin > 0.9:
        raise ConfigurationError(
            configuration.name("budget.margin"),
            f"{margin:g} holds back more than nine tenths of every budget; the most is 0.9",
        )
    return BudgetSettings(
        price_table=None if table is None else Path(table).expanduser(),
        margin=margin,
        uncalibrated_margin=reader.number(
            "budget.uncalibrated.margin", DEFAULT_UNCALIBRATED_MARGIN, low=0.0
        ),
    )


MODEL_CREDENTIAL = "credential.model_api_key"


def load_model(configuration: Configuration) -> ModelSettings:
    """The model settings alone: `taktusctl` reads them too."""
    reader = _Reader(configuration)
    endpoint = reader.text("model.endpoint", "") or None
    if endpoint is not None and not (
        endpoint.startswith("http://") or endpoint.startswith("https://")
    ):
        raise ConfigurationError(
            configuration.name("model.endpoint"), f"{endpoint!r} is not an http(s) URL"
        )
    name = reader.text("model.name", "")
    if endpoint is not None and not name:
        raise ConfigurationError(
            configuration.name("model.name"),
            f"is not set; {configuration.name('model.endpoint')} names an endpoint and needs "
            "the model to ask it for",
        )
    return ModelSettings(
        endpoint=endpoint,
        name=name,
        purposes=reader.names("model.purposes", ("*",)),
        credential=configuration.secret(MODEL_CREDENTIAL),
        credential_source=configuration.source(MODEL_CREDENTIAL),
        billing=reader.choice(
            "model.billing", "per_token", ("per_token", "per_window", "per_hardware_time")
        ),
        output_cap=reader.choice("model.output.cap", "soft", ("hard", "soft", "none")),
        provider_limit=reader.choice(
            "model.provider.limit", "unknown", ("hard", "alert", "none", "unknown")
        ),
    )


def load_connectors(configuration: Configuration) -> Mapping[str, str]:
    """The connectors alone (`TAKTUS_CONNECTORS`): `taktusctl` reads them too. Each entry is a
    label — the channel capability for intake — and the MCP URL of one connector, which
    serves its actions as well; the run resolves an action's connector by the capabilities
    the connector declares, not by the label."""
    return _Reader(configuration).connectors()


def load_execution(configuration: Configuration) -> ExecutionSettings:
    """The execution settings alone: `taktusctl` reads them too, without the daemon's."""
    reader = _Reader(configuration)
    kind = ExecutionKind(
        reader.choice("execution", "endpoint", tuple(k.value for k in ExecutionKind))
    )
    unit = reader.text("execution.unit", "") or None
    if kind is not ExecutionKind.ENDPOINT and unit is None:
        what = "a command line" if kind is ExecutionKind.PROCESS else "an image reference"
        raise ConfigurationError(
            configuration.name("execution.unit"),
            f"is not set; {configuration.name('execution')}={kind.value} starts a unit per job "
            f"and needs {what} here",
        )
    namespace = reader.text("execution.namespace", "") or None
    if kind is ExecutionKind.CLUSTER and namespace is None:
        raise ConfigurationError(
            configuration.name("execution.namespace"),
            f"is not set; {configuration.name('execution')}=cluster starts a Job per job in the "
            "execution namespace and needs its name here",
        )
    return ExecutionSettings(
        kind=kind,
        endpoint=reader.url("worker", "http://127.0.0.1:9000"),
        unit=unit,
        unit_port=reader.integer("execution.unit.port", 9000, low=1, high=65535),
        unit_state_dir=reader.text("execution.unit.state.dir", "/var/lib/taktus/unit"),
        cpus=reader.number("execution.cpus", 1.0, low=0.1),
        memory_mb=reader.integer("execution.memory.mb", 1024, low=16),
        wall_seconds=reader.integer("execution.wall.seconds", 3600, low=1),
        start_timeout_seconds=reader.integer("execution.start.timeout.seconds", 60, low=1),
        network=reader.text("execution.network", "") or None,
        engine_socket=reader.text("execution.engine.socket", "/var/run/docker.sock"),
        egress_image=reader.text("execution.egress.image", "python:3.13-slim"),
        memory_unenforced=reader.flag("execution.memory.unenforced", False),
        namespace=namespace,
        egress_enforced=reader.flag("execution.egress.enforce", True),
        service_account=reader.text("execution.service.account", "") or None,
        state_claim=reader.text("execution.state.claim", "") or None,
    )


@dataclass(frozen=True)
class CapacitySettings:
    """What the capacity report and admission against the platform are told
    (docs/architecture/platform.md). Every threshold is a named setting with a default."""

    storage_warn_percent: float
    """`TAKTUS_CAPACITY_STORAGE_WARN_PERCENT` (10): below this share of a volume free, a
    person must act."""
    storage_refuse_percent: float
    """`TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT` (2): below this share free, a run is refused."""
    act_within_days: int
    """`TAKTUS_CAPACITY_ACT_WITHIN_DAYS` (30): a person is told this many days before the
    storage threshold is crossed at the observed growth."""
    memory_warn_percent: float
    """`TAKTUS_CAPACITY_MEMORY_WARN_PERCENT` (10)."""
    cpu_warn_percent: float
    """`TAKTUS_CAPACITY_CPU_WARN_PERCENT` (10)."""
    memory_reserve_mb: int
    """`TAKTUS_CAPACITY_MEMORY_RESERVE_MB` (256): what stays free beside a job at admission."""
    window_days: int
    """`TAKTUS_CAPACITY_WINDOW_DAYS` (14): runs per day are counted over this many days."""
    database_volume_mb: int | None
    """`TAKTUS_CAPACITY_DATABASE_VOLUME_MB`: the size of the volume the database lives on,
    which is not visible from the instance. Unset, the database's free space is reported as
    not observed."""
    storage_expandable: bool | None
    """`TAKTUS_CAPACITY_STORAGE_EXPANDABLE`: whether the state's volumes can be grown in place.
    Unset, the report says it does not know."""
    interval_seconds: int
    """`TAKTUS_CAPACITY_INTERVAL_SECONDS` (3600): how often the daemon's scheduler reports."""

    def effective(self) -> list[tuple[str, str]]:
        return [
            ("TAKTUS_CAPACITY_STORAGE_WARN_PERCENT", f"{self.storage_warn_percent:g}"),
            ("TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT", f"{self.storage_refuse_percent:g}"),
            ("TAKTUS_CAPACITY_ACT_WITHIN_DAYS", str(self.act_within_days)),
            ("TAKTUS_CAPACITY_MEMORY_WARN_PERCENT", f"{self.memory_warn_percent:g}"),
            ("TAKTUS_CAPACITY_CPU_WARN_PERCENT", f"{self.cpu_warn_percent:g}"),
            ("TAKTUS_CAPACITY_MEMORY_RESERVE_MB", str(self.memory_reserve_mb)),
            ("TAKTUS_CAPACITY_WINDOW_DAYS", str(self.window_days)),
            (
                "TAKTUS_CAPACITY_DATABASE_VOLUME_MB",
                "" if self.database_volume_mb is None else str(self.database_volume_mb),
            ),
            (
                "TAKTUS_CAPACITY_STORAGE_EXPANDABLE",
                "" if self.storage_expandable is None else str(self.storage_expandable).lower(),
            ),
            ("TAKTUS_CAPACITY_INTERVAL_SECONDS", str(self.interval_seconds)),
        ]


def load_capacity(configuration: Configuration) -> CapacitySettings:
    """The capacity settings alone: `taktusctl capacity` reads them too."""
    reader = _Reader(configuration)
    warn = reader.number("capacity.storage.warn.percent", 10.0, low=0.1, high=99.0)
    refuse = reader.number("capacity.storage.refuse.percent", 2.0, low=0.0, high=99.0)
    if refuse >= warn:
        raise ConfigurationError(
            configuration.name("capacity.storage.refuse.percent"),
            f"{refuse:g} is not below {configuration.name('capacity.storage.warn.percent')} "
            f"({warn:g}): a person is told before work is refused, never after",
        )
    volume = reader.integer("capacity.database.volume.mb", 0, low=0) or None
    return CapacitySettings(
        storage_warn_percent=warn,
        storage_refuse_percent=refuse,
        act_within_days=reader.integer("capacity.act.within.days", 30, low=1),
        memory_warn_percent=reader.number("capacity.memory.warn.percent", 10.0, low=0.1, high=99.0),
        cpu_warn_percent=reader.number("capacity.cpu.warn.percent", 10.0, low=0.1, high=99.0),
        memory_reserve_mb=reader.integer("capacity.memory.reserve.mb", 256, low=0),
        window_days=reader.integer("capacity.window.days", 14, low=1),
        database_volume_mb=volume,
        storage_expandable=reader.optional_flag("capacity.storage.expandable"),
        interval_seconds=reader.integer("capacity.interval.seconds", 3600, low=60),
    )


def load_tenants(configuration: Configuration) -> tuple[str, ...]:
    """`TAKTUS_TENANTS`: the tenants an instance serves; `taktusctl capacity` reads it too."""
    return _Reader(configuration).names("tenants", (DEFAULT_TENANT,))


@dataclass(frozen=True)
class Settings:
    roles: frozenset[Role]
    database: Secret
    """The database URL; the whole of it is a secret (CREDENTIALS.md)."""
    database_source: str
    """Where the database URL came from, for the startup log: `environment` or `file <path>`."""
    migrate_on_start: bool
    """Bring the database to the current schema before serving. Off, the daemon refuses to
    start against a schema that is not at the revision it was built for."""
    http_host: str
    http_port: int
    path_prefix: str
    """Everything the HTTP surface serves lives under this prefix, `/` by default."""
    execution: ExecutionSettings
    """How the runner reaches an execution unit for worker steps."""
    telemetry: TelemetrySettings
    """Where spans are exported, if anywhere."""
    model: ModelSettings
    budget: BudgetSettings
    """The model `llm` steps ask, if one is configured."""
    capacity: CapacitySettings
    """What the capacity report is told: thresholds, the database's volume, the interval."""
    connectors: Mapping[str, str]
    """Channel capability → the MCP URL of the connector that serves its intake."""
    findings_connector: str | None
    """The MCP URL of the connector through which product findings go to the Taktus repository
    (UC-6.12, ADR-0046). None: the operator did not enable it, and findings are only recorded
    on the instance and shown to the operator."""
    state_dir: Path
    """Where artifact bytes are written."""
    tenants: tuple[str, ...]
    """The tenants this instance serves: the runner claims work for each of them in turn, and
    the identity component places senders in them and nowhere else."""
    instance: str
    """How this process names itself when it claims work; unique among the instances that
    share a database."""
    shutdown_ceiling_seconds: int
    """How long a running step may take to reach its boundary after SIGTERM before the
    process gives up on it and exits (ADR-0005: the hard ceiling)."""
    lease_seconds: int
    """How long a claimed job stays claimed without a heartbeat before another runner may
    take it: the time a dead runner's work is stuck."""
    poll_seconds: float
    """How often an idle runner or scheduler looks again."""
    runner_concurrency: int
    """How many runs one runner process executes at a time."""
    log_level: str

    def effective(self) -> list[tuple[str, str]]:
        """Every setting with the value in effect, as (variable, value) — secrets masked and
        their source named instead. This is the startup log."""
        return [
            ("TAKTUS_ROLES", ",".join(sorted(r.value for r in self.roles))),
            ("TAKTUS_DATABASE_URL", f"{self.database} (from {self.database_source})"),
            ("TAKTUS_MIGRATE_ON_START", str(self.migrate_on_start).lower()),
            ("TAKTUS_HTTP_HOST", self.http_host),
            ("TAKTUS_HTTP_PORT", str(self.http_port)),
            ("TAKTUS_PATH_PREFIX", self.path_prefix),
            *self.execution.effective(),
            *self.telemetry.effective(),
            *self.model.effective(),
            *self.budget.effective(),
            *self.capacity.effective(),
            ("TAKTUS_CONNECTORS", ",".join(f"{c}={u}" for c, u in self.connectors.items())),
            ("TAKTUS_FINDINGS_CONNECTOR", self.findings_connector or ""),
            ("TAKTUS_STATE_DIR", str(self.state_dir)),
            ("TAKTUS_TENANTS", ",".join(self.tenants)),
            ("TAKTUS_INSTANCE", self.instance),
            ("TAKTUS_SHUTDOWN_CEILING_SECONDS", str(self.shutdown_ceiling_seconds)),
            ("TAKTUS_LEASE_SECONDS", str(self.lease_seconds)),
            ("TAKTUS_POLL_SECONDS", str(self.poll_seconds)),
            ("TAKTUS_RUNNER_CONCURRENCY", str(self.runner_concurrency)),
            ("TAKTUS_LOG_LEVEL", self.log_level),
        ]


def load(configuration: Configuration, *, default_instance: str) -> Settings:
    """Read and validate every setting. `default_instance` is what the process calls itself
    when `TAKTUS_INSTANCE` is not set (the composition root passes host name and pid)."""
    reader = _Reader(configuration)
    database = configuration.secret("database.url")
    if database is None:
        raise ConfigurationError(
            configuration.name("database.url"),
            "is not set; taktusd runs against PostgreSQL only. Set "
            f"{configuration.name('database.url')}_FILE to a file that holds the URL (or the "
            "variable itself for a URL that carries no password)",
        )
    url = database.reveal()
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        raise ConfigurationError(
            configuration.name("database.url"), "must start with postgresql://"
        )
    prefix = reader.text("path.prefix", "/")
    return Settings(
        roles=reader.roles(),
        database=database,
        database_source=configuration.source("database.url") or "environment",
        migrate_on_start=reader.flag("migrate.on.start", False),
        http_host=reader.text("http.host", "127.0.0.1"),
        http_port=reader.integer("http.port", 8080, low=1, high=65535),
        path_prefix=normalise_prefix(prefix, configuration.name("path.prefix")),
        execution=load_execution(configuration),
        telemetry=load_telemetry(configuration),
        model=load_model(configuration),
        budget=load_budget(configuration),
        capacity=load_capacity(configuration),
        connectors=reader.connectors(),
        findings_connector=reader.url("findings.connector", "") or None,
        state_dir=Path(reader.text("state.dir", "~/.cache/taktus/taktusd")).expanduser(),
        tenants=load_tenants(configuration),
        instance=reader.text("instance", default_instance),
        shutdown_ceiling_seconds=reader.integer("shutdown.ceiling.seconds", 300, low=1),
        lease_seconds=reader.integer("lease.seconds", 60, low=5),
        poll_seconds=reader.number("poll.seconds", 1.0, low=0.05),
        runner_concurrency=reader.integer("runner.concurrency", 4, low=1),
        log_level=reader.choice("log.level", "info", ("debug", "info", "warning", "error")),
    )


def normalise_prefix(prefix: str, setting: str) -> str:
    """`/`, `/taktus`, `/a/b`: a leading slash, no trailing one, and nothing that changes the
    meaning of a path. The root is `/`."""
    if not prefix.startswith("/"):
        raise ConfigurationError(setting, f"{prefix!r} must start with /")
    if any(part in ("", ".", "..") for part in prefix.strip("/").split("/")) and prefix != "/":
        raise ConfigurationError(
            setting, f"{prefix!r} has an empty segment, or one that is . or .."
        )
    if any(c.isspace() or c in "?#" for c in prefix):
        raise ConfigurationError(setting, f"{prefix!r} must be a path: no space, ? or #")
    return "/" if prefix == "/" else "/" + prefix.strip("/")


class _Reader:
    """Typed reads over the port, each failing with the variable's name."""

    def __init__(self, configuration: Configuration) -> None:
        self._configuration = configuration

    def _raw(self, key: str) -> tuple[str, str | None]:
        return self._configuration.name(key), self._configuration.get(key)

    def text(self, key: str, default: str) -> str:
        _, value = self._raw(key)
        return default if value is None else value

    def flag(self, key: str, default: bool) -> bool:
        name, value = self._raw(key)
        if value is None:
            return default
        lowered = value.lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ConfigurationError(name, f"{value!r} is not true or false")

    def integer(self, key: str, default: int, *, low: int, high: int | None = None) -> int:
        name, value = self._raw(key)
        if value is None:
            return default
        try:
            number = int(value)
        except ValueError:
            raise ConfigurationError(name, f"{value!r} is not a whole number") from None
        return self._within(name, number, low, high)

    def number(self, key: str, default: float, *, low: float, high: float | None = None) -> float:
        name, value = self._raw(key)
        if value is None:
            return default
        try:
            number = float(value)
        except ValueError:
            raise ConfigurationError(name, f"{value!r} is not a number") from None
        return self._within(name, number, low, high)

    def optional_flag(self, key: str) -> bool | None:
        """True, false, or None when the variable is not set: a fact nobody has stated."""
        _, value = self._raw(key)
        return None if value is None else self.flag(key, False)

    def _within[N: (int, float)](self, name: str, number: N, low: N, high: N | None) -> N:
        if number < low or (high is not None and number > high):
            bound = f"at least {low}" if high is None else f"between {low} and {high}"
            raise ConfigurationError(name, f"{number} is out of range; {bound}")
        return number

    def choice(self, key: str, default: str, allowed: tuple[str, ...]) -> str:
        name, value = self._raw(key)
        if value is None:
            return default
        if value.lower() not in allowed:
            raise ConfigurationError(name, f"{value!r} is not one of {', '.join(allowed)}")
        return value.lower()

    def url(self, key: str, default: str) -> str:
        name, value = self._raw(key)
        if value is None:
            return default
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ConfigurationError(name, f"{value!r} is not an http(s) URL")
        return value.rstrip("/")

    def names(self, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        """A comma-separated list of identifiers, each non-empty, none twice."""
        name, value = self._raw(key)
        if value is None:
            return default
        items = tuple(item.strip() for item in value.split(","))
        if any(not item for item in items):
            raise ConfigurationError(name, f"{value!r} has an empty entry")
        if len(set(items)) != len(items):
            raise ConfigurationError(name, f"{value!r} names an entry twice")
        return items

    def roles(self) -> frozenset[Role]:
        name, value = self._raw("roles")
        if value is None or value.strip().lower() == "all":
            return ALL_ROLES
        chosen: set[Role] = set()
        for item in self.names("roles", ()):
            try:
                chosen.add(Role(item.lower()))
            except ValueError:
                raise ConfigurationError(
                    name,
                    f"{item!r} is not a role; roles are {', '.join(r.value for r in Role)}, or all",
                ) from None
        return frozenset(chosen)

    def connectors(self) -> Mapping[str, str]:
        """`channel.repo=http://connector:9100/mcp,channel.chat=…`: a capability, an equals
        sign, the MCP URL of the connector that serves it."""
        name, value = self._raw("connectors")
        if value is None:
            return {}
        mapping: dict[str, str] = {}
        for entry in (e.strip() for e in value.split(",") if e.strip()):
            capability, separator, url = entry.partition("=")
            if not separator or not capability.strip() or not url.strip():
                raise ConfigurationError(
                    name, f"{entry!r} is not capability=url (for example channel.repo=http://…)"
                )
            capability = capability.strip()
            if "." not in capability or capability != capability.lower():
                raise ConfigurationError(
                    name, f"{capability!r} is not a capability (lowercase, dotted)"
                )
            if not (url.strip().startswith("http://") or url.strip().startswith("https://")):
                raise ConfigurationError(name, f"{url.strip()!r} is not an http(s) URL")
            if capability in mapping:
                raise ConfigurationError(name, f"{capability!r} is mapped twice")
            mapping[capability] = url.strip()
        return mapping
