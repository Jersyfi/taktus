"""A share of a catalogue entry with circles of the organisation's structure, and a caller's
own credential (ADR-0246, ADR-0247; UC-8.6, UC-8.7, UC-8.8, UC-14.3).

A **share** is kept under `<kind>:<subject>`: a model or a connector by its adapter identifier,
an agent or a skill by its name. It names its owner, its purpose and one or more circles. A
model's share names where the model processes data, its cost model and, for a model the
organisation trained, its version and the evaluations that admitted it. The maturity of an
entry is never stated here: it is read where it is kept.

A **circle** is a path of the structure (`acme/sales`), admitting every identity whose own path
starts with it, or one identity (`identity:<id>`), admitting that identity alone.

A **caller credential** binds one identity and one credential name to the parameter that
identity's value is provided under: `<NAME>_<SUFFIX>`. It holds no value.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

IDENTITY_CIRCLE = "identity:"
CREDENTIAL_NAME = r"^[A-Z][A-Z0-9_]*$"
SUFFIX = r"^[A-Z0-9][A-Z0-9_]*$"

type Location = Literal["own", "eu", "elsewhere"]
type CostModel = Literal["per_token", "per_window", "per_hardware_time"]


class ShareError(Exception):
    """An act on a share its records refuse. `reason` is the ledger outcome."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ShareKind(StrEnum):
    MODEL = "model"
    AGENT = "agent"
    CONNECTOR = "connector"
    SKILL = "skill"


class Origin(StrEnum):
    PROVIDED = "provided"
    """Served by a provider or a server the organisation runs, as configured."""
    TRAINED = "trained"
    """Trained by the organisation: it names its version and its evaluation history."""


class ShareState(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


def share_id(kind: ShareKind, subject: str) -> str:
    return f"{kind}:{subject}"


def path_of(circle: str) -> tuple[str, ...] | None:
    """The path a circle names; None for a circle of one identity."""
    if circle.startswith(IDENTITY_CIRCLE):
        return None
    return tuple(circle.split("/"))


def admits(circle: str, identity: str, org_path: Sequence[str]) -> bool:
    """Whether the circle holds the identity: it is that identity, or the identity's path
    starts with the circle's."""
    path = path_of(circle)
    if path is None:
        return circle[len(IDENTITY_CIRCLE) :] == identity
    return tuple(org_path[: len(path)]) == path


class CatalogueShare(Value):
    id: str = Field(min_length=1)
    """`<kind>:<subject>`."""
    tenant: str = Field(min_length=1)
    kind: ShareKind
    subject: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    """The identity answerable for the entry."""
    purpose: str = Field(min_length=1)
    circles: tuple[str, ...] = Field(min_length=1)
    state: ShareState = ShareState.ACTIVE
    location: Location | None = None
    """For a model: where it processes data (UC-11.1)."""
    cost_model: CostModel | None = None
    """For a model: how its provider bills (`contracts/model/v1`)."""
    origin: Origin | None = None
    """For a model: provided, or trained by the organisation."""
    version: str | None = Field(default=None, min_length=1)
    """For a trained model: the digest of its file."""
    evaluations: tuple[str, ...] = ()
    """For a trained model: the evaluations that admitted it, oldest first (ADR-0114 §4)."""
    shared_at: datetime
    shared_by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _whole(self) -> CatalogueShare:
        findings = missing(self)
        if findings:
            raise ValueError("; ".join(findings))
        if self.id != share_id(self.kind, self.subject):
            raise ValueError("a share's identifier is `<kind>:<subject>`")
        return self

    def admits(self, identity: str, org_path: Sequence[str]) -> bool:
        """Whether the identity may see and use the entry: the share is active and one of its
        circles holds the identity."""
        return self.state is ShareState.ACTIVE and any(
            admits(c, identity, org_path) for c in self.circles
        )


def missing(share: CatalogueShare) -> list[str]:
    """Every field the share's kind requires that it lacks, in words (ADR-0246 §1)."""
    findings: list[str] = []
    for circle in share.circles:
        path = path_of(circle)
        if path is None:
            if not circle[len(IDENTITY_CIRCLE) :]:
                findings.append("a circle of one identity names the identity")
        elif any(not part for part in path) or path[0] != share.tenant:
            findings.append(f"the circle {circle!r} is a path that starts at the tenant")
    if share.kind is ShareKind.MODEL:
        if share.location is None:
            findings.append("a model names where it processes data (own, eu or elsewhere)")
        if share.cost_model is None:
            findings.append("a model names its cost model")
        if share.origin is None:
            findings.append("a model names whether it is provided or trained")
        if share.origin is Origin.TRAINED:
            if share.version is None:
                findings.append("a trained model names its version")
            if not share.evaluations:
                findings.append("a trained model names its evaluation history")
    else:
        extra = [
            name
            for name, value in (
                ("location", share.location),
                ("cost_model", share.cost_model),
                ("origin", share.origin),
                ("version", share.version),
            )
            if value is not None
        ]
        if extra or share.evaluations:
            findings.append(f"only a model names {', '.join(extra or ['evaluations'])}")
    return findings


class CallerCredential(Value):
    """Which parameter holds one identity's value of one credential (ADR-0247 §1)."""

    id: str = Field(min_length=1)
    """`<identity>:<NAME>`."""
    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    name: str = Field(pattern=CREDENTIAL_NAME)
    suffix: str = Field(pattern=SUFFIX)
    bound_at: datetime

    @model_validator(mode="after")
    def _named(self) -> CallerCredential:
        if self.id != credential_id(self.identity, self.name):
            raise ValueError("a caller credential's identifier is `<identity>:<NAME>`")
        return self

    @property
    def parameter(self) -> str:
        """The parameter the value is provided under: `TAKTUS_CREDENTIAL_<parameter>_FILE`."""
        return f"{self.name}_{self.suffix}"


def credential_id(identity: str, name: str) -> str:
    return f"{identity}:{name}"
