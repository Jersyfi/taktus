"""What `taktusd` is told about itself: every setting, read through the configuration port,
validated once at startup.

A setting that is wrong is a `ConfigurationError` naming the variable and what to do — the
daemon prints that one sentence and exits, never a stack trace. `Settings.effective()` is what
the daemon logs at startup: every setting with its value, every secret masked, and for each
secret where it came from. Nothing here reads the environment directly; the configuration port
does, and a test hands in a mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from taktus.ports.configuration import Configuration, ConfigurationError, Secret


class Role(StrEnum):
    """The four roles of docs/architecture/project-structure.md §5. `TAKTUS_ROLES=all` runs
    every one of them in one process — the self-hosting shape."""

    API = "api"
    RUNNER = "runner"
    SCHEDULER = "scheduler"
    AUTOMATION = "automation"


ALL_ROLES: frozenset[Role] = frozenset(Role)
DEFAULT_TENANT = "default"


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
    worker: str
    """The base URL of the one worker endpoint the runner delegates worker steps to."""
    connectors: Mapping[str, str]
    """Channel capability → the MCP URL of the connector that serves its intake."""
    state_dir: Path
    """Where artifact bytes are written."""
    tenants: tuple[str, ...]
    """The tenants this instance serves. Until the identity component exists, an instance is
    told its tenants; the runner claims work for each of them in turn."""
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
            ("TAKTUS_WORKER", self.worker),
            ("TAKTUS_CONNECTORS", ",".join(f"{c}={u}" for c, u in self.connectors.items())),
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
        worker=reader.url("worker", "http://127.0.0.1:9000"),
        connectors=reader.connectors(),
        state_dir=Path(reader.text("state.dir", "~/.cache/taktus/taktusd")).expanduser(),
        tenants=reader.names("tenants", (DEFAULT_TENANT,)),
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

    def number(self, key: str, default: float, *, low: float) -> float:
        name, value = self._raw(key)
        if value is None:
            return default
        try:
            number = float(value)
        except ValueError:
            raise ConfigurationError(name, f"{value!r} is not a number") from None
        return self._within(name, number, low, None)

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
