"""A shared agent: one versioned core and role profiles versioned apart from it (ADR-0163,
UC-8.11).

The **core** is what every role shares: the agent's purpose, its instructions, the process it
runs (its flow), the model purpose it asks, its autonomy level, and the most it may ever do — its
grants. A **role profile** sets only what varies by role: the knowledge sources, connectors,
tools and output formats it uses, its approval limit, and its vocabulary and tone. A profile
narrows the core and never widens it.

A profile is a role, never a person (principle 14). It is keyed by the agent and the role.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1 import AutonomyLevel, Value

AGENT_NAME = r"^[a-z][a-z0-9-]*$"
AGENT_VERSION = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class AgentError(Exception):
    """An act on a shared agent its records refuse. `reason` is the ledger outcome."""

    def __init__(self, reason: str, message: str, findings: tuple[str, ...] = ()) -> None:
        super().__init__(message if not findings else f"{message}: {'; '.join(findings)}")
        self.reason = reason
        self.findings = findings


class Grants(Value):
    """What an agent may do: the most for a core, what a role uses for a profile. A tool is a
    capability or a connector operation, as a step names one; a source is a knowledge source; a
    connector is a connector's label."""

    sources: tuple[str, ...] = ()
    connectors: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    approval_limit: Decimal | None = Field(default=None, ge=0)
    """Up to which amount a result of the agent may be approved by the role without a further
    person; None approves nothing."""

    @property
    def size(self) -> int:
        """How many grants it holds: the measure of its rights when no subset decides."""
        return len(self.sources) + len(self.connectors) + len(self.tools) + len(self.formats)

    def within(self, other: Grants) -> bool:
        return not widening(self, other)


def widening(profile: Grants, core: Grants) -> list[str]:
    """What `profile` grants beyond `core`, each as a finding; empty when it only narrows."""
    findings: list[str] = []
    for field in ("sources", "connectors", "tools", "formats"):
        beyond = sorted(set(getattr(profile, field)) - set(getattr(core, field)))
        if beyond:
            findings.append(f"{field} beyond the core: {', '.join(beyond)}")
    if profile.approval_limit is not None and (
        core.approval_limit is None or profile.approval_limit > core.approval_limit
    ):
        findings.append(
            f"an approval limit of {profile.approval_limit} above the core's "
            f"{'none' if core.approval_limit is None else core.approval_limit}"
        )
    return findings


class CoreState(StrEnum):
    HELD = "held"
    """Proposed, and held until every profile's evaluation passed on it."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class AgentCore(Value):
    id: str = Field(min_length=1)
    """`<agent>@<version>`."""
    tenant: str = Field(min_length=1)
    agent: str = Field(pattern=AGENT_NAME)
    version: str = Field(pattern=AGENT_VERSION)
    purpose: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    flow: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    """The process the agent runs when it is called."""
    model: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    """The model purpose it asks, as a step names one."""
    autonomy_level: AutonomyLevel
    grants: Grants
    state: CoreState = CoreState.HELD
    verdicts: Mapping[str, str] = Field(default_factory=dict)
    """The verdict of each profile's evaluation on this core, by profile identifier."""
    proposed_at: datetime

    @model_validator(mode="after")
    def _named(self) -> AgentCore:
        if self.id != f"{self.agent}@{self.version}":
            raise ValueError("a core's identifier is `<agent>@<version>`")
        return self


class RoleProfile(Value):
    id: str = Field(min_length=1)
    """`<agent>:<role>@<version>`."""
    tenant: str = Field(min_length=1)
    agent: str = Field(pattern=AGENT_NAME)
    role: str = Field(min_length=1, pattern=r"^[^:@\s]+$")
    version: str = Field(pattern=AGENT_VERSION)
    grants: Grants
    vocabulary: tuple[str, ...] = ()
    tone: str | None = Field(default=None, min_length=1)
    active: bool = True
    """The role's profile in force; an earlier version of it is kept, inactive."""
    set_at: datetime

    @model_validator(mode="after")
    def _named(self) -> RoleProfile:
        if self.id != profile_id(self.agent, self.role, self.version):
            raise ValueError("a profile's identifier is `<agent>:<role>@<version>`")
        return self

    def brief(self, core: AgentCore) -> str:
        """What a step of the agent's flow is handed: the core's instructions, then what the
        role's profile sets (ADR-0163 §5)."""
        lines = [f"Agent {core.id}, for the role {self.role} (profile {self.id}).", ""]
        lines.append(core.instructions.strip())
        if self.tone:
            lines += ["", f"Tone: {self.tone}"]
        if self.vocabulary:
            lines += ["", f"Vocabulary: {', '.join(self.vocabulary)}"]
        if self.grants.formats:
            lines += ["", f"Output formats: {', '.join(self.grants.formats)}"]
        if self.grants.sources:
            lines += ["", f"Knowledge sources: {', '.join(self.grants.sources)}"]
        return "\n".join(lines)


def profile_id(agent: str, role: str, version: str) -> str:
    return f"{agent}:{role}@{version}"
