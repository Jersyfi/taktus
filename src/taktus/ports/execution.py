"""Execution: how an execution unit comes to exist for one job, and with what isolation.

The worker port says how the core talks to an execution unit. This port says how one is
started for a job (ADR-0002): as a process on this machine, as a container with limits and a
network allowlist, or — next — as a pod in a cluster. An adapter starts the unit, injects the
credentials the job names at runtime, makes the unit reachable at an endpoint that speaks the
worker contract, and tears everything down when the job ends. A job's workspace does not
outlive the job; the unit's *state* — its checkpoints — does, so that a later job can resume.

**The rule of ADR-0002 is enforced here, not documented:** an adapter without isolation is
refused from autonomy level 3 upwards. The check fails closed — a job whose level is unknown
is refused too. `refusal()` is the rule; every adapter without isolation calls it before it
starts anything.

The launch convention, the one thing a unit must know when an adapter starts it: it reads
`TAKTUS_UNIT_PORT` for the port to serve the contract on and `TAKTUS_UNIT_STATE_DIR` for the
directory that outlives the job. Both are environment variables, so that any worker — a
script, a foreign binary behind a shell wrapper — can be launched without knowing more.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import Field

from taktus.ports.worker import CredentialReference, Host
from taktus.shared.v1 import AutonomyLevel, Value

UNIT_PORT_VARIABLE = "TAKTUS_UNIT_PORT"
UNIT_STATE_DIR_VARIABLE = "TAKTUS_UNIT_STATE_DIR"
ISOLATION_REQUIRED_FROM: AutonomyLevel = 3
"""From this autonomy level upwards an unisolated unit is refused (ADR-0002)."""


class Isolation(StrEnum):
    """What stands between the unit and the machine that runs the control plane."""

    NONE = "none"
    """The `process` adapter: nothing. Local development and a single user only."""
    CONTAINER = "container"
    """Process, filesystem and network isolation; the default in operation."""
    CLUSTER = "cluster"
    """A pod with quota and network policy; arrives with the cluster adapter."""


class ResourceLimits(Value):
    """What one job may use of the machine. The adapter kills a job that exceeds them; the
    `process` adapter can enforce the wall clock only and says so."""

    cpus: float = Field(gt=0)
    memory_bytes: int = Field(gt=0)
    wall_seconds: int = Field(gt=0)


class ExecutionUnit(Value):
    """What to start, as configuration names it — never a product name.

    `program` is what the adapter starts: a command line for the `process` adapter, an image
    reference for the `container` adapter. `port` is where the unit serves the worker contract
    inside its isolation, `state_dir` where it keeps its checkpoints inside its isolation.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    program: str = Field(min_length=1)
    port: int = Field(default=9000, ge=1, le=65535)
    state_dir: str = Field(default="/var/lib/taktus/unit", min_length=1)
    limits: ResourceLimits
    start_timeout_seconds: int = Field(default=60, ge=1)
    """How long the unit may take until its health answers."""


class JobRequest(Value):
    """One job: the unit to start, for whom, with what reach and what credentials."""

    job_id: str = Field(min_length=1)
    unit: ExecutionUnit
    autonomy_level: AutonomyLevel | None
    """The level the run carries. None means unknown, and unknown is refused wherever isolation
    is required."""
    allowed_hosts: tuple[Host, ...] = ()
    """The hosts the unit may reach; nothing else. Empty means no outbound access at all — the
    `container` adapter enforces it at the network, the `process` adapter cannot."""
    credentials: tuple[CredentialReference, ...] = ()
    """By name. The adapter reads each value at launch through the configuration port and
    injects it into the unit; the value is never written to a volume, an image or a log."""
    wall_seconds: int | None = Field(default=None, ge=1)
    """A ceiling below the unit's own, for a job with a deadline."""


type KillCause = Literal["memory", "cpu", "wall", "stop"]


class JobExit(Value):
    """How a job ended: its exit code where there is one, and — when the adapter killed it —
    why, as a token and a sentence."""

    code: int | None = None
    killed: KillCause | None = None
    reason: str = Field(min_length=1)


class Job(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def endpoint(self) -> str:
        """Where the unit answers the worker contract, as the control plane reaches it."""
        ...

    async def exit(self) -> JobExit | None:
        """None while the unit runs; how it ended once it has."""
        ...


class ExecutionRefused(Exception):
    """The job may not be started as requested: the adapter's isolation does not suffice for
    the job's autonomy level, or the request names what the adapter cannot honour. Nothing was
    started. The message says why and never a secret."""


class ExecutionError(Exception):
    """The unit could not be started or did not become ready. The message names what happened
    and never a secret."""


class Execution(Protocol):
    """One way of starting execution units."""

    @property
    def isolation(self) -> Isolation: ...

    def launch(self, request: JobRequest) -> AbstractAsyncContextManager[Job]:
        """Start the unit for the job; the context is entered once the unit answers health and
        yields the job; leaving it ends the unit and removes its workspace. Raises
        `ExecutionRefused` before starting anything when the request may not be honoured, and
        `ExecutionError` when the unit does not come up."""
        ...


def refusal(isolation: Isolation, autonomy_level: AutonomyLevel | None) -> str | None:
    """The rule of ADR-0002, fail-closed: why a job at this level may not run with this
    isolation, or None when it may. An unisolated unit is refused from level 3 upwards, and
    when the level is not known at all — an unsupervised worker without isolation is an open
    door, and a door whose supervision is unknown is treated as unsupervised."""
    if isolation is not Isolation.NONE:
        return None
    if autonomy_level is None:
        return (
            "the autonomy level of this job is unknown, and an execution unit without "
            "isolation runs only at a level below 3 that is known (ADR-0002)"
        )
    if autonomy_level >= ISOLATION_REQUIRED_FROM:
        return (
            f"autonomy level {autonomy_level} needs an isolated execution unit; the process "
            f"adapter isolates nothing and is refused from level {ISOLATION_REQUIRED_FROM} "
            "upwards (ADR-0002)"
        )
    return None
