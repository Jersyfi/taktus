"""A skill version as the catalogue keeps it beside its `SKILL.md` (ADR-0113 §1, ADR-0162 §1).

The file is the open format, unchanged: name, description, instructions and the other fields
of its front matter. What Taktus knows beyond it — the version, the origin, the owner, the
stage, its rounds and measurements — is kept here, never in the file, so that a skill exported
is the open format as it was written (UC-14.3).

A skill names no person (principle 14). Its origin names runs, processes and steps. A draft
drawn from one person's own use belongs to that person: it is private, only the owner sees it,
and only the owner's act shares it. Who owns it is kept in a record of its own,
`SkillOwnership`, apart from every score of the skill.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

SKILL_NAME = r"^[a-z0-9]+(-[a-z0-9]+)*$"
"""The open format's name: lowercase letters, digits and single hyphens inside, 1 to 64
characters (ADR-0113 §1)."""
SKILL_VERSION = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"

FLOOR = 11
"""The smallest n of passed rounds before a skill is approved automatically at level 4, for a
skill no `exact` step uses (DEC-0028, NTC-0246)."""
EXACT_FACTOR = 2
"""What the floor is multiplied by for a skill an `exact` step uses (NTC-0246)."""


class SkillError(Exception):
    """An act on a skill that its record or the policy refuses. `reason` is the outcome of
    `skill.refused`."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class InvalidSkill(Exception):
    """A `SKILL.md` that does not hold to the open format, with every finding."""

    def __init__(self, findings: tuple[str, ...]) -> None:
        super().__init__("; ".join(findings))
        self.findings = findings


class SkillStage(StrEnum):
    DRAFT = "draft"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    PRODUCTION = "production"
    RETIRED = "retired"


ORDER: tuple[SkillStage, ...] = (
    SkillStage.DRAFT,
    SkillStage.EVALUATED,
    SkillStage.APPROVED,
    SkillStage.PRODUCTION,
)
"""The stages a version passes, in order. `retired` is reached from any of them."""


class OriginKind(StrEnum):
    BUNDLE = "bundle"
    """Written by a bundle's author, registered from `skills/<name>/SKILL.md`."""
    RECURRING = "recurring"
    """Drafted by rule from corrections that recurred at one step of a process (UC-4.4)."""
    OWN_USE = "own_use"
    """Drawn from one person's own use; it belongs to that person (UC-14.2)."""


class SkillOrigin(Value):
    """What a version was drawn from: runs, processes and steps — never a person."""

    kind: OriginKind
    source: str | None = Field(default=None, min_length=1)
    """The bundle path a bundle's skill was read from; None otherwise."""
    processes: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    """`<process>/<step>`."""
    runs: tuple[str, ...] = ()
    corrections: int = Field(default=0, ge=0)
    """How many corrections it was drawn from."""


class SkillFile(Value):
    """The `SKILL.md` as the open format defines it."""

    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME)
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = ""
    fields: Mapping[str, Any] = Field(default_factory=dict)
    """The front matter's other fields, kept as they are. `allowed-tools` among them is never
    honoured: the frame of an assignment decides which tools a step may use."""
    files: tuple[str, ...] = ()
    """The directory's other files, by relative path."""
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    """Of the directory's whole content, `SKILL.md` and every other file."""


class StageChange(Value):
    """One change of stage, as `skill.<kind>` records it. Who acted is the entry's actor, never a
    field here (principle 14)."""

    stage: SkillStage
    at: datetime
    reason: str = Field(min_length=1)


class RoundState(StrEnum):
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class Round(Value):
    """One evaluation of the version on the cases of every process that uses it (ADR-0162 §3)."""

    id: str = Field(min_length=1)
    evaluations: tuple[str, ...] = Field(min_length=1)
    """The ADR-0134 evaluations, one per using process with cases."""
    state: RoundState = RoundState.RUNNING
    score: float | None = Field(default=None, ge=0, le=1)
    """The mean of the proposed sides' scores, once scored."""
    dry_run: bool | None = None
    """Whether every case run of the proposed sides finished; None while running."""
    started_at: datetime
    scored_at: datetime | None = None


class Measurement(Value):
    """A score of the version on its cases: from a round, or from a drift evaluation of a using
    process whose runs pinned it (ADR-0162 §7)."""

    source: Literal["round", "operation"]
    evaluation: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    at: datetime


class SkillVersion(Value):
    id: str = Field(min_length=1)
    """`<name>@<version>`."""
    tenant: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME)
    version: str = Field(pattern=SKILL_VERSION)
    file: SkillFile
    origin: SkillOrigin
    owned: bool = False
    """Drawn from one person's own use; who that is, is its `SkillOwnership`."""
    shared: bool = False
    """Whether its owner shared it. A version nobody owns is the tenant's from the start."""
    stage: SkillStage = SkillStage.DRAFT
    history: tuple[StageChange, ...] = ()
    rounds: tuple[Round, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    predecessor: str | None = None
    """The version that was in production when this one was registered."""
    registered_at: datetime

    @model_validator(mode="after")
    def _named(self) -> SkillVersion:
        if self.id != f"{self.name}@{self.version}":
            raise ValueError("a skill version's identifier is `<name>@<version>`")
        if self.file.name != self.name:
            raise ValueError(f"the file names {self.file.name!r}, the version {self.name!r}")
        if (self.origin.kind is OriginKind.OWN_USE) != self.owned:
            raise ValueError("a skill is owned exactly when it was drawn from a person's own use")
        return self

    @property
    def private(self) -> bool:
        """Only its owner sees it, and nothing but the owner's act takes it further."""
        return self.owned and not self.shared


class SkillOwnership(Value):
    """Whose own use a skill version was drawn from: the one person it belongs to (UC-14.2).
    Kept apart from the version, so that no record holds a person beside a score."""

    id: str = Field(min_length=1)
    """The skill version's identifier."""
    tenant: str = Field(min_length=1)
    owner: str = Field(min_length=1)


class SkillPolicy(Value):
    """A tenant's n for automatic approval at level 4 (ADR-0162 §4). The record is the tenant's
    only one, under the identifier `skills`."""

    id: Literal["skills"] = "skills"
    tenant: str = Field(min_length=1)
    floor: int = FLOOR
    exact_factor: int = EXACT_FACTOR
    n: int | None = None
    """The tenant's own n for a skill no `exact` step uses; None takes the floor. A skill an
    `exact` step uses needs n times the factor."""

    @model_validator(mode="after")
    def _not_below_the_floor(self) -> SkillPolicy:
        if self.floor < FLOOR:
            raise ValueError(f"the floor is never below {FLOOR} (DEC-0028, NTC-0246)")
        if self.exact_factor < EXACT_FACTOR:
            raise ValueError(f"the factor for an exact step is never below {EXACT_FACTOR}")
        if self.n is not None and self.n < self.floor:
            raise ValueError(f"n is never below the floor, {self.floor}")
        return self

    def required(self, *, exact: bool) -> int:
        """How many passed rounds in a row approve a skill automatically at level 4."""
        n = self.floor if self.n is None else self.n
        return n * self.exact_factor if exact else n
