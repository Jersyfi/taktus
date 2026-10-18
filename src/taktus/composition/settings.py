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
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from taktus.components.reporting.domain.service import texts
from taktus.components.run.domain.service import budget as budgeting
from taktus.conformance.contracts import contracts_root
from taktus.ports.administration import NONE, Administration
from taktus.ports.configuration import Configuration, ConfigurationError, Secret
from taktus.ports.execution import variable_refusal
from taktus.ports.model import PriceTable, WeightingTable
from taktus.ports.worker import Host


class Role(StrEnum):
    """The four roles of docs/architecture/project-structure.md §5. `TAKTUS_ROLES=all` runs
    every one of them in one process — the self-hosting shape."""

    API = "api"
    RUNNER = "runner"
    SCHEDULER = "scheduler"
    AUTOMATION = "automation"


ALL_ROLES: frozenset[Role] = frozenset(Role)


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
    cpu_request_share: float = 0.25
    """`TAKTUS_EXECUTION_CPU_REQUEST_SHARE` (cluster): the share of its CPU limit a unit requests
    from the cluster's scheduler, between 0.01 and 1. A unit may still use its whole limit while
    the node has CPU to spare. 1 requests the whole limit. The memory request is always the
    memory limit, because the node has no swap (deploy/k8s/README.md §7, NTC-0190)."""
    service_hosts: tuple[str, ...] = ()
    """`TAKTUS_EXECUTION_SERVICE_HOSTS` (the launching kinds): the hosts the worker's own service
    needs — its agent's or its model's provider — as comma-separated host names, each as a
    frame names a host. A launched unit reaches them for an assignment and for the conformance
    suite, never for a probe; the step's frame is not changed by them (ADR-0089). Empty, a unit
    reaches the frame's hosts alone, as before."""
    unit_env: tuple[tuple[str, str], ...] = ()
    """`TAKTUS_EXECUTION_UNIT_ENV` (the launching kinds): the variables a launched unit's own
    program needs to start, as comma-separated `NAME=value` pairs — a coding worker's
    `CODING_AGENT_AUTH=api-key`. Every unit of the worker receives them: an assignment's, a
    probe's and the conformance suite's. Visible configuration, never a secret: a name that
    carries one is refused (ADR-0090). Empty, a unit receives the launch convention alone."""

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
            ("TAKTUS_EXECUTION_CPU_REQUEST_SHARE", str(self.cpu_request_share)),
            ("TAKTUS_EXECUTION_SERVICE_HOSTS", ",".join(self.service_hosts)),
            ("TAKTUS_EXECUTION_UNIT_ENV", ",".join(f"{n}={v}" for n, v in self.unit_env)),
        ]


WORKER_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
"""A configured worker's name: lowercase letters and digits, words joined by hyphens. It is the
last segment of the worker's adapter identifier, `worker.<name>`, and a DNS label."""

WORKER_NAME_LENGTH = 40

CREDENTIAL_PREFIX = "credential."
"""The configuration keys a worker's credentials are supplied under (CREDENTIALS.md)."""


def worker_segment(name: str) -> str:
    """The segment a worker's name takes in a configuration key: `coding-second` →
    `coding_second`, so that the environment adapter's variable is a valid name. A worker's
    name holds no underscore, so two names never share a segment."""
    return name.replace("-", "_")


class WorkerConfiguration:
    """The configuration port as one named worker reads it (ADR-0078).

    Every key `k` is first read as `worker.<name>.k` — the variable
    `TAKTUS_WORKER_<NAME>_K` — and, where the worker sets nothing, as the instance's own `k`:
    the execution namespace, the egress image and the limits are shared unless a worker sets
    its own. Two keys have no such fallback. The endpoint (`worker`, read as
    `worker.<name>.endpoint`) is the worker's alone, because two workers at one endpoint are one
    worker. A credential (`credential.<name>`) is the worker's alone, because each launched
    worker receives only its own credentials: two workers that reference the same credential
    name receive the value configured for each of them, and neither sees the other's."""

    def __init__(self, configuration: Configuration, name: str) -> None:
        self._configuration = configuration
        self._name = name
        self._prefix = f"worker.{worker_segment(name)}."

    def _own(self, key: str) -> str:
        return self._prefix + ("endpoint" if key == "worker" else key)

    @staticmethod
    def _alone(key: str) -> bool:
        return key == "worker" or key.startswith(CREDENTIAL_PREFIX)

    def _where(self, key: str) -> str:
        """The key the value under `key` is read from for this worker: its own where it is set
        or where it has no fallback, the instance's otherwise."""
        own = self._own(key)
        if self._alone(key) or self._configuration.source(own) is not None:
            return own
        return key

    def get(self, key: str) -> str | None:
        return self._configuration.get(self._where(key))

    def secret(self, key: str) -> Secret | None:
        return self._configuration.secret(self._where(key))

    def source(self, key: str) -> str | None:
        return self._configuration.source(self._where(key))

    def name(self, key: str) -> str:
        """The variable the operator sets for this worker: its own, even where the value in
        effect is the instance's."""
        return self._configuration.name(self._own(key))


@dataclass(frozen=True)
class WorkerSettings:
    """One worker the instance is configured with: its name and how it is reached."""

    name: str | None
    """Its name in `TAKTUS_WORKERS`; None for the one worker of an instance that names none,
    configured as before through `TAKTUS_EXECUTION` and `TAKTUS_WORKER`."""
    execution: ExecutionSettings

    @property
    def identifier(self) -> str:
        """The adapter identifier the ledger records: `worker.<name>`, or `worker.<kind>` for
        the one unnamed worker — never a product name (ADR-0003)."""
        return f"worker.{self.name or self.execution.kind.value}"

    def configuration(self, configuration: Configuration) -> Configuration:
        """The configuration port as this worker reads it: its own keys first, and only its
        own credentials. The unnamed worker reads the instance's, as before."""
        if self.name is None:
            return configuration
        return WorkerConfiguration(configuration, self.name)

    def effective(self) -> list[tuple[str, str]]:
        lines = self.execution.effective()
        if self.name is None:
            return lines
        prefix = f"TAKTUS_WORKER_{worker_segment(self.name).upper()}_"
        return [
            (prefix + ("ENDPOINT" if v == "TAKTUS_WORKER" else v.removeprefix("TAKTUS_")), value)
            for v, value in lines
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
    usage_kinds: tuple[str, ...] = ("input", "output")
    """`TAKTUS_MODEL_USAGE_KINDS`: the price kinds the endpoint reports per call, comma-separated
    — `input`, `output`, `cache_read`, `cache_write`. Money is recomputable exactly only from
    kinds that are reported; conformance check M-04 holds the endpoint to this declaration."""

    def effective(self) -> list[tuple[str, str]]:
        credential = "" if self.credential is None else f"*** (from {self.credential_source})"
        return [
            ("TAKTUS_MODEL_ENDPOINT", self.endpoint or ""),
            ("TAKTUS_MODEL_NAME", self.name),
            ("TAKTUS_MODEL_PURPOSES", ",".join(self.purposes)),
            ("TAKTUS_MODEL_BILLING", self.billing),
            ("TAKTUS_MODEL_OUTPUT_CAP", self.output_cap),
            ("TAKTUS_MODEL_PROVIDER_LIMIT", self.provider_limit),
            ("TAKTUS_MODEL_USAGE_KINDS", ",".join(self.usage_kinds)),
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
    seeds_file: Path | None = None
    """`TAKTUS_BUDGET_SEEDS`: a file of calibration seeds — observations measured elsewhere
    that a worker nothing has measured here yet is reserved by (`budgeting.seeds_of`). Absent,
    the default: no seed, and such a worker reserves the uncalibrated margin (DEC-0034). What
    was measured on one tenant's runs enters another instance only as data its operator chose
    to load here (ADR-0092 §2)."""
    model_classes: Mapping[str, str] = field(default_factory=dict)
    """`TAKTUS_TAKT_MODEL_CLASSES`: which class of the weighting table each model is in, as
    `model=class` pairs, comma-separated — `fake-model@1=medium`. A model in no class has its
    tokens named unweighed, never counted as zero (ADR-0010)."""

    def weights(self) -> WeightingTable:
        """The weighting table in force: the repository's (DEC-0131), never the operator's."""
        return weighting_table_in_force()

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

    def seeds(self) -> tuple[budgeting.Seed, ...]:
        """The seeds the file holds, validated; none when no file is configured."""
        if self.seeds_file is None:
            return ()
        try:
            document = yaml.safe_load(self.seeds_file.read_text(encoding="utf-8"))
            return budgeting.seeds_of(document)
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise ConfigurationError(
                "TAKTUS_BUDGET_SEEDS",
                f"{self.seeds_file} is not a file of calibration seeds: {str(error)[:200]}",
            ) from error

    def effective(self) -> list[tuple[str, str]]:
        return [
            ("TAKTUS_PRICE_TABLE", "" if self.price_table is None else str(self.price_table)),
            ("TAKTUS_BUDGET_MARGIN", f"{self.margin:g}"),
            ("TAKTUS_BUDGET_UNCALIBRATED_MARGIN", f"{self.uncalibrated_margin:g}"),
            ("TAKTUS_BUDGET_SEEDS", "" if self.seeds_file is None else str(self.seeds_file)),
            (
                "TAKTUS_TAKT_MODEL_CLASSES",
                ",".join(f"{m}={c}" for m, c in sorted(self.model_classes.items())),
            ),
        ]


WEIGHTING_TABLES = ("model", "v1", "weighting-tables")
"""Where the weighting tables are, under the contracts directory: in the repository, and in the
installed package beside the schemas (ADR-0010)."""


def weighting_table_in_force() -> WeightingTable:
    """The newest weighting table the repository publishes, by `valid_from`. A table is never
    changed once used; a new one is a new file (ADR-0010, DEC-0131)."""
    directory = contracts_root().joinpath(*WEIGHTING_TABLES)
    tables = [
        WeightingTable.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.json"))
    ]
    if not tables:
        raise FileNotFoundError(f"no weighting table under {directory}")
    return max(tables, key=lambda table: table.valid_from)


def _model_classes(name: str, pairs: tuple[str, ...]) -> dict[str, str]:
    classes: dict[str, str] = {}
    for pair in pairs:
        model, separator, model_class = pair.partition("=")
        if not separator or not model.strip() or not model_class.strip():
            raise ConfigurationError(name, f"{pair!r} is not model=class")
        classes[model.strip()] = model_class.strip()
    return classes


DEFAULT_MARGIN = 0.0
"""No share of the budget is held back by default: the safety margin is a worker's (DEC-0034)."""
DEFAULT_UNCALIBRATED_MARGIN = 1.0
"""100 % beyond the estimate for a worker nothing has measured yet (DEC-0034)."""


def load_budget(configuration: Configuration) -> BudgetSettings:
    reader = _Reader(configuration)
    table = reader.text("price.table", "") or None
    seeds = reader.text("budget.seeds", "") or None
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
        seeds_file=None if seeds is None else Path(seeds).expanduser(),
        model_classes=_model_classes(
            configuration.name("takt.model.classes"), reader.names("takt.model.classes", ())
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
        usage_kinds=_usage_kinds(reader, configuration),
    )


PRICE_KIND_NAMES = ("input", "output", "cache_read", "cache_write")


def _usage_kinds(reader: _Reader, configuration: Configuration) -> tuple[str, ...]:
    """The price kinds the operator declares the endpoint reports: known kinds, none twice."""
    kinds = reader.names("model.usage.kinds", ("input", "output"))
    unknown = [kind for kind in kinds if kind not in PRICE_KIND_NAMES]
    if unknown:
        raise ConfigurationError(
            configuration.name("model.usage.kinds"),
            f"{', '.join(unknown)} is not a price kind; one of {', '.join(PRICE_KIND_NAMES)}",
        )
    return kinds


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
        cpu_request_share=reader.number("execution.cpu.request.share", 0.25, low=0.01, high=1.0),
        service_hosts=reader.hosts("execution.service.hosts"),
        unit_env=reader.unit_env("execution.unit.env"),
    )


def load_workers(configuration: Configuration) -> tuple[WorkerSettings, ...]:
    """Every worker the instance is configured with, in the order a step is resolved in: the
    first whose declared capabilities cover what the step requires serves it (ADR-0078).

    `TAKTUS_WORKERS` unset: the one worker configured as before, by `TAKTUS_EXECUTION`,
    `TAKTUS_WORKER` and `TAKTUS_EXECUTION_*`. Set, it names the workers in order, and each reads
    its own settings under `TAKTUS_WORKER_<NAME>_…` with the instance's as the default — except
    its endpoint and its credentials, which are its own alone (`WorkerConfiguration`)."""
    reader = _Reader(configuration)
    names = reader.names("workers", ())
    if not names:
        return (WorkerSettings(name=None, execution=load_execution(configuration)),)
    setting = configuration.name("workers")
    workers: list[WorkerSettings] = []
    for name in names:
        if len(name) > WORKER_NAME_LENGTH or WORKER_NAME.fullmatch(name) is None:
            raise ConfigurationError(
                setting,
                f"{name!r} is not a worker name: lowercase letters and digits, words joined by "
                f"hyphens, at most {WORKER_NAME_LENGTH} characters",
            )
        scoped = WorkerConfiguration(configuration, name)
        execution = load_execution(scoped)
        if execution.kind is ExecutionKind.ENDPOINT and scoped.get("worker") is None:
            raise ConfigurationError(
                scoped.name("worker"),
                f"is not set; the worker {name} of {setting} is reached by endpoint and needs "
                "its base URL here",
            )
        workers.append(WorkerSettings(name=name, execution=execution))
    return tuple(workers)


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


def load_backup_expected_hours(configuration: Configuration) -> int | None:
    """`TAKTUS_BACKUP_EXPECTED_HOURS`: None when unset or 0. `taktusctl alerts` reads it too."""
    return _Reader(configuration).integer("backup.expected.hours", 0, low=0) or None


def load_administration(configuration: Configuration) -> Administration:
    """`TAKTUS_PLATFORM` and `TAKTUS_ADMINISTERS`: the platform this instance runs on and the
    platforms each credential administers (ADR-0052). `taktusctl` reads them too."""
    reader = _Reader(configuration)
    platform = reader.text("platform", "").strip() or None
    name, value = reader._raw("administers")
    declared: dict[str, tuple[str, ...]] = {}
    for entry in (value or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        credential, sep, platforms = entry.partition("=")
        credential, platforms = credential.strip(), platforms.strip()
        if not sep or not credential or not platforms:
            raise ConfigurationError(name, f"{entry!r} is not NAME=platform, NAME=a|b or NAME=none")
        if credential in declared:
            raise ConfigurationError(name, f"declares {credential!r} twice")
        listed = tuple(p.strip() for p in platforms.split("|"))
        if any(not p for p in listed):
            raise ConfigurationError(name, f"{entry!r} has an empty platform")
        if NONE in listed and len(listed) > 1:
            raise ConfigurationError(name, f"{entry!r}: `none` stands alone")
        declared[credential] = () if listed == (NONE,) else listed
    return Administration(platform=platform, declared=declared)


def load_knowledge_directory(configuration: Configuration) -> Path | None:
    """`TAKTUS_KNOWLEDGE_DIRECTORY`: the directory the capability `knowledge.pages` is served
    over, one Markdown file per page, for an organisation that keeps no wiki (UC-13.6,
    ADR-0065). None: the instance serves no directory, and a knowledge system is a connector of
    `TAKTUS_CONNECTORS` or none. `taktusctl` reads it too."""
    value = _Reader(configuration).text("knowledge.directory", "").strip()
    return Path(value).expanduser() if value else None


@dataclass(frozen=True)
class FindingsShape:
    """The shape of the issue a product finding opens (UC-6.12, ADR-0046): its operator's
    configuration, never one repository's form as the product's default (ADR-0092)."""

    form_file: Path | None = None
    """`TAKTUS_FINDINGS_FORM`: a file holding the body's form — text with the fields a finding
    fills, `$tried`, `$lacking`, `$cause`, `$area`, `$run` and `$step` (`texts.form`). Absent,
    the default: the product's plain shape."""
    labels: tuple[str, ...] = ()
    """`TAKTUS_FINDINGS_LABELS`: the labels a finding's issue is opened with, comma-separated;
    none by default."""

    def form(self) -> str | None:
        """The form the file holds, validated; None when no file is configured."""
        if self.form_file is None:
            return None
        try:
            return texts.form(self.form_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConfigurationError(
                "TAKTUS_FINDINGS_FORM",
                f"{self.form_file} is not a form of a finding: {str(error)[:200]}",
            ) from error

    def effective(self) -> list[tuple[str, str]]:
        return [
            ("TAKTUS_FINDINGS_FORM", "" if self.form_file is None else str(self.form_file)),
            ("TAKTUS_FINDINGS_LABELS", ",".join(self.labels)),
        ]


def load_findings(configuration: Configuration) -> FindingsShape:
    """The shape of a finding's issue; `taktusctl findings` reads it too."""
    reader = _Reader(configuration)
    form = reader.text("findings.form", "").strip()
    labels = (
        ()
        if not reader.text("findings.labels", "").strip()
        else reader.names("findings.labels", ())
    )
    return FindingsShape(form_file=Path(form).expanduser() if form else None, labels=labels)


def load_tenants(configuration: Configuration) -> tuple[str, ...] | None:
    """`TAKTUS_TENANTS`, deprecated (ADR-0104 §7): the tenants of the registry an instance is
    narrowed to. None, unset: every tenant of the registry. The command line reads it too."""
    reader = _Reader(configuration)
    if not reader.text("tenants", "").strip():
        return None
    return reader.names("tenants", ())


@dataclass(frozen=True)
class DatabaseTimeouts:
    """How long the database lets a transaction wait or idle before it fails it with a reason
    (issue #309). Set on every connection the persistence adapter opens."""

    lock_seconds: float
    """`TAKTUS_DATABASE_LOCK_TIMEOUT_SECONDS` (30): how long a statement waits for a lock —
    the ledger's claim on a tenant's chain among them — before it fails (`lock_timeout`).
    0 waits for good."""
    idle_in_transaction_seconds: float
    """`TAKTUS_DATABASE_IDLE_IN_TRANSACTION_SECONDS` (120): how long a transaction may sit
    between two statements before the server ends its session and releases its locks
    (`idle_in_transaction_session_timeout`). 0 lets it sit for good."""

    def effective(self) -> list[tuple[str, str]]:
        return [
            ("TAKTUS_DATABASE_LOCK_TIMEOUT_SECONDS", f"{self.lock_seconds:g}"),
            (
                "TAKTUS_DATABASE_IDLE_IN_TRANSACTION_SECONDS",
                f"{self.idle_in_transaction_seconds:g}",
            ),
        ]


def load_database_timeouts(configuration: Configuration) -> DatabaseTimeouts:
    """The database's timeouts alone: `taktusctl` opens the database with them too."""
    reader = _Reader(configuration)
    return DatabaseTimeouts(
        lock_seconds=reader.number("database.lock.timeout.seconds", 30.0, low=0.0),
        idle_in_transaction_seconds=reader.number(
            "database.idle.in.transaction.seconds", 120.0, low=0.0
        ),
    )


@dataclass(frozen=True)
class Settings:
    roles: frozenset[Role]
    database: Secret
    """The database URL; the whole of it is a secret (CREDENTIALS.md)."""
    database_timeouts: DatabaseTimeouts
    """How long a statement waits for a lock and a transaction idles before either fails."""
    database_source: str
    """Where the database URL came from, for the startup log: `environment` or `file <path>`."""
    migrate_on_start: bool
    """Bring the database to the current schema before serving. Off, the daemon refuses to
    start against a schema that is not at the revision it was built for."""
    http_host: str
    http_port: int
    path_prefix: str
    """Everything the HTTP surface serves lives under this prefix, `/` by default."""
    workers: tuple[WorkerSettings, ...]
    """The workers the runner resolves a worker step to, in order, and how each is reached."""
    telemetry: TelemetrySettings
    """Where spans are exported, if anywhere."""
    model: ModelSettings
    budget: BudgetSettings
    """The model `llm` steps ask, if one is configured."""
    capacity: CapacitySettings
    """What the capacity report is told: thresholds, the database's volume, the interval."""
    connectors: Mapping[str, str]
    """Channel capability → the MCP URL of the connector that serves its intake."""
    triage: Mapping[str, str]
    """Public channel → the process that triages an unknown sender's contribution there
    (`TAKTUS_TRIAGE`, UC-1.9, ADR-0088). A channel it does not name has no triage."""
    administration: Administration
    """The platform this instance runs on and what each credential administers (ADR-0052)."""
    knowledge_directory: Path | None
    """The directory the instance serves `knowledge.pages` over, where the organisation keeps
    no wiki (UC-13.6); None when it serves none."""
    findings_connector: str | None
    """The MCP URL of the connector through which product findings go to the repository its
    operator chose (UC-6.12, ADR-0046). None: the operator did not enable it, and findings are
    only recorded on the instance and shown to the operator."""
    findings: FindingsShape
    """The shape of the issue a finding opens: its form and its labels."""
    backup_expected_hours: int | None
    """`TAKTUS_BACKUP_EXPECTED_HOURS`: how old the last successful backup may be before the
    owner hears that it is missing (ADR-0106 §5). None, the default: a missing backup is not
    watched, and a failed one the backup recorded still is."""
    change_process: str | None
    """`TAKTUS_CHANGE_PROCESS`: the process that turns a change asked for in words into a
    proposal (UC-4.15, ADR-0091 §2), by its identifier. None, the default: no request in words
    is taken, and a person hands over the changed bundle. Which process does it is a tenant's
    bundle, never a default of the product (ADR-0092)."""
    state_dir: Path
    """Where artifact bytes are written."""
    object_cache_mb: int
    """How many MiB of artifact bytes the object store keeps in memory at most: the objects used
    most recently. Every object stays readable from `state_dir`. 0 keeps none (#311)."""
    tenants: tuple[str, ...] | None
    """`TAKTUS_TENANTS`, deprecated: the tenants of the registry this instance is narrowed to.
    None, the default: every tenant of the registry, read by every role on every round
    (ADR-0104)."""
    administration_key: Secret | None
    """`TAKTUS_ADMINISTRATION_KEY_FILE`: the key that admits a request to the administration of
    tenants on the HTTP surface (ADR-0104 §4). None: those routes answer 404."""
    administration_key_source: str | None
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
    live_streams: int
    """How many streams of changes one process of the `api` role holds open at most; one more
    is refused with `503` (ADR-0055 §7)."""
    offer_window_seconds: int
    """How long one offer to link an account answers every event of its person in its
    conversation (ADR-0040 §5); a later event may be offered again."""
    log_level: str

    def effective(self) -> list[tuple[str, str]]:
        """Every setting with the value in effect, as (variable, value) — secrets masked and
        their source named instead. This is the startup log."""
        return [
            ("TAKTUS_ROLES", ",".join(sorted(r.value for r in self.roles))),
            ("TAKTUS_DATABASE_URL", f"{self.database} (from {self.database_source})"),
            *self.database_timeouts.effective(),
            ("TAKTUS_MIGRATE_ON_START", str(self.migrate_on_start).lower()),
            ("TAKTUS_HTTP_HOST", self.http_host),
            ("TAKTUS_HTTP_PORT", str(self.http_port)),
            ("TAKTUS_PATH_PREFIX", self.path_prefix),
            *(
                [("TAKTUS_WORKERS", ",".join(w.name for w in self.workers if w.name))]
                if self.workers[0].name is not None
                else []
            ),
            *(line for worker in self.workers for line in worker.effective()),
            *self.telemetry.effective(),
            *self.model.effective(),
            *self.budget.effective(),
            *self.capacity.effective(),
            ("TAKTUS_CONNECTORS", ",".join(f"{c}={u}" for c, u in self.connectors.items())),
            ("TAKTUS_TRIAGE", ",".join(f"{c}={p}" for c, p in self.triage.items())),
            ("TAKTUS_KNOWLEDGE_DIRECTORY", str(self.knowledge_directory or "")),
            ("TAKTUS_FINDINGS_CONNECTOR", self.findings_connector or ""),
            *self.findings.effective(),
            ("TAKTUS_BACKUP_EXPECTED_HOURS", str(self.backup_expected_hours or "")),
            ("TAKTUS_CHANGE_PROCESS", self.change_process or ""),
            ("TAKTUS_PLATFORM", self.administration.platform or ""),
            (
                "TAKTUS_ADMINISTERS",
                ",".join(
                    f"{c}={'|'.join(p) or NONE}" for c, p in self.administration.declared.items()
                ),
            ),
            ("TAKTUS_STATE_DIR", str(self.state_dir)),
            ("TAKTUS_OBJECT_CACHE_MB", str(self.object_cache_mb)),
            ("TAKTUS_TENANTS", ",".join(self.tenants or ())),
            (
                "TAKTUS_ADMINISTRATION_KEY",
                ""
                if self.administration_key is None
                else f"{self.administration_key} (from {self.administration_key_source})",
            ),
            ("TAKTUS_INSTANCE", self.instance),
            ("TAKTUS_SHUTDOWN_CEILING_SECONDS", str(self.shutdown_ceiling_seconds)),
            ("TAKTUS_LEASE_SECONDS", str(self.lease_seconds)),
            ("TAKTUS_POLL_SECONDS", str(self.poll_seconds)),
            ("TAKTUS_RUNNER_CONCURRENCY", str(self.runner_concurrency)),
            ("TAKTUS_LIVE_STREAMS", str(self.live_streams)),
            ("TAKTUS_OFFER_WINDOW_SECONDS", str(self.offer_window_seconds)),
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
        database_timeouts=load_database_timeouts(configuration),
        database_source=configuration.source("database.url") or "environment",
        migrate_on_start=reader.flag("migrate.on.start", False),
        http_host=reader.text("http.host", "127.0.0.1"),
        http_port=reader.integer("http.port", 8080, low=1, high=65535),
        path_prefix=normalise_prefix(prefix, configuration.name("path.prefix")),
        workers=load_workers(configuration),
        telemetry=load_telemetry(configuration),
        model=load_model(configuration),
        budget=load_budget(configuration),
        capacity=load_capacity(configuration),
        connectors=reader.connectors(),
        triage=reader.triage(),
        administration=load_administration(configuration),
        knowledge_directory=load_knowledge_directory(configuration),
        findings_connector=reader.url("findings.connector", "") or None,
        findings=load_findings(configuration),
        backup_expected_hours=load_backup_expected_hours(configuration),
        change_process=reader.text("change.process", "").strip() or None,
        state_dir=Path(reader.text("state.dir", "~/.cache/taktus/taktusd")).expanduser(),
        object_cache_mb=reader.integer("object.cache.mb", 64, low=0),
        tenants=load_tenants(configuration),
        administration_key=configuration.secret("administration.key"),
        administration_key_source=configuration.source("administration.key"),
        instance=reader.text("instance", default_instance),
        shutdown_ceiling_seconds=reader.integer("shutdown.ceiling.seconds", 300, low=1),
        lease_seconds=reader.integer("lease.seconds", 60, low=5),
        poll_seconds=reader.number("poll.seconds", 1.0, low=0.05),
        runner_concurrency=reader.integer("runner.concurrency", 4, low=1),
        live_streams=reader.integer("live.streams", 500, low=1),
        offer_window_seconds=reader.integer("offer.window.seconds", 86400, low=1),
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


_HOST: TypeAdapter[str] = TypeAdapter(Host)


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

    def hosts(self, key: str) -> tuple[str, ...]:
        """A comma-separated list of hosts, each as a frame names one — a lowercase host name or
        an IPv4 address, optionally with a port, no wildcard — none twice. Unset or empty: no
        host."""
        name, value = self._raw(key)
        if value is None or not value.strip():
            return ()
        items = self.names(key, ())
        for item in items:
            try:
                _HOST.validate_python(item)
            except ValidationError:
                raise ConfigurationError(
                    name,
                    f"{item!r} is not a host: a lowercase host name or an IPv4 address, "
                    "optionally with a port, and no wildcard",
                ) from None
        return items

    def unit_env(self, key: str) -> tuple[tuple[str, str], ...]:
        """Comma-separated `NAME=value` pairs, a value holding no comma, no name twice (ADR-0090).
        A name that carries a secret is refused: one `variable_refusal` refuses, and one under
        which this configuration supplies a credential (`TAKTUS_CREDENTIAL_<NAME>_FILE`) —
        for a named worker, its own. Unset or empty: none."""
        name, value = self._raw(key)
        if value is None or not value.strip():
            return ()
        pairs: list[tuple[str, str]] = []
        for entry in value.split(","):
            variable, sep, setting = entry.partition("=")
            variable = variable.strip()
            if not sep or not variable:
                raise ConfigurationError(
                    name, f"{entry.strip()!r} is not NAME=value; pairs are comma separated"
                )
            refusal = variable_refusal(variable)
            if refusal is not None:
                raise ConfigurationError(name, f"{variable} {refusal}")
            credential = CREDENTIAL_PREFIX + variable.lower()
            if self._configuration.source(credential) is not None:
                raise ConfigurationError(
                    name,
                    f"{variable} is a credential this configuration supplies "
                    f"({self._configuration.name(credential)}_FILE); a secret reaches a unit as "
                    "a credential, never as configuration",
                )
            if any(variable == known for known, _ in pairs):
                raise ConfigurationError(name, f"{variable} is set twice")
            pairs.append((variable, setting))
        return tuple(pairs)

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

    def triage(self) -> Mapping[str, str]:
        """`channel.repo=triage`: a channel capability, an equals sign, the identifier of
        the process that triages an unknown sender's contribution on it (ADR-0088)."""
        name, value = self._raw("triage")
        if value is None:
            return {}
        mapping: dict[str, str] = {}
        for entry in (e.strip() for e in value.split(",") if e.strip()):
            capability, separator, process = (part.strip() for part in entry.partition("="))
            if not separator or not capability or not process:
                raise ConfigurationError(
                    name,
                    f"{entry!r} is not capability=process (for example channel.repo=triage)",
                )
            if "." not in capability or capability != capability.lower():
                raise ConfigurationError(
                    name, f"{capability!r} is not a capability (lowercase, dotted)"
                )
            if re.fullmatch(r"[a-z][a-z0-9-]*", process) is None:
                raise ConfigurationError(name, f"{process!r} is not a process identifier")
            if capability in mapping:
                raise ConfigurationError(name, f"{capability!r} is mapped twice")
            mapping[capability] = process
        return mapping

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
