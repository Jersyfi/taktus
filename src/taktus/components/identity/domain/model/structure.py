"""The organisation's structure, and where what Taktus set up is filed (ADR-0275, ADR-0276).

The **structure** is a tree whose levels the organisation names: the tenant at its root, then,
for example, departments or groups, teams and projects. Each node is a **unit**. The root unit's
identifier is the tenant's; every other unit names its parent.

A **placement** puts one object — a process, a shared agent, a connector, a model, a skill or a
budget — in exactly one unit. An object nobody placed is in the root. A run is placed in its
process's unit when it is created, and keeps that unit (ADR-0275 §2).

An identity **belongs** to the units its organisational path names and to every unit that names
it as a member. A **project** is a unit at the structure's last level, with the circle it was
created for; a **private** project has its creator as its one owner, and nothing above it sees
into it (ADR-0276).

A **filing** says where something Taktus set up is documented: every place, each with the link
that opens it. Where the organisation configured a knowledge system for the unit, that system is
the record and the filing holds its link; Taktus's own page is used only where none is
configured.

Pure values: the rules over them are `domain/service/structure.py`.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
"""A unit's identifier, as a path element and a quota's key carry it."""

DEFAULT_LEVELS: tuple[str, ...] = ("tenant", "department", "team", "project")
"""The levels a tenant has until it names its own (UC-1.4 §2)."""


class PlacedKind(StrEnum):
    """What a unit holds. Every one of these belongs to exactly one unit (UC-1.4 §2)."""

    PROCESS = "process"
    AGENT = "agent"
    CONNECTOR = "connector"
    MODEL = "model"
    SKILL = "skill"
    BUDGET = "budget"


SHARED_KINDS = frozenset(
    {PlacedKind.AGENT, PlacedKind.CONNECTOR, PlacedKind.MODEL, PlacedKind.SKILL}
)
"""What a process uses and a unit shares: used where it is placed and in every unit below it."""


class Circle(StrEnum):
    """Whom a project is for (UC-1.6 §2)."""

    ALONE = "alone"
    TEAM = "team"
    PROJECT_TEAM = "project_team"
    COMPANY = "company"


class OrgStructure(Value):
    """A tenant's levels, named by the organisation. One record per tenant; its id is the
    tenant's."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    levels: tuple[str, ...] = Field(default=DEFAULT_LEVELS, min_length=2, max_length=8)
    """The names of the levels, the root's first: `tenant, department, team, project`, or
    `household, group, project` — whatever the organisation calls them."""

    @model_validator(mode="after")
    def _named_once(self) -> OrgStructure:
        if self.id != self.tenant:
            raise ValueError("a structure's identifier is its tenant's")
        if len(set(self.levels)) != len(self.levels) or any(not n.strip() for n in self.levels):
            raise ValueError("each level of the structure is named, each once")
        return self


class Reference(Value):
    """Something of the organisation's own that a project refers to: a ticket, a document, a
    board. The project holds the link, never a copy (UC-1.6 §2)."""

    kind: str = Field(min_length=1, max_length=40)
    """`ticket`, `document`, `repository`, ... — what the link opens."""
    link: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=200)


class StructureUnit(Value):
    id: str = Field(pattern=NAME.pattern)
    tenant: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    level: int = Field(ge=0)
    """The index of its level in `OrgStructure.levels`; the root's is 0."""
    parent: str | None = None
    """None for the root alone, whose identifier is the tenant's."""
    members: tuple[str, ...] = ()
    """Identities that belong to it beyond those whose organisational path names it: a
    project's team. Identities only — a unit never holds a figure about one."""
    private: bool = False
    """A private project: its owner's alone. Nothing above it sees into it, and its
    consumption is in no figure of a unit above it (UC-1.6 §2)."""
    owner: str | None = None
    """The identity a private project belongs to, and who alone shares it."""
    circle: Circle | None = None
    """For a project: whom it was created for."""
    references: tuple[Reference, ...] = ()
    created_by: str = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def _a_tree(self) -> StructureUnit:
        if (self.parent is None) != (self.level == 0):
            raise ValueError("the root alone has no parent, and it is at level 0")
        if self.parent is None and self.id != self.tenant:
            raise ValueError("the root unit's identifier is its tenant's")
        if self.private and self.owner is None:
            raise ValueError("a private unit names the identity it belongs to")
        if len(set(self.members)) != len(self.members):
            raise ValueError(f"the members of {self.id!r} are named each once")
        return self

    @property
    def project(self) -> bool:
        return self.circle is not None


class Placement(Value):
    """One object in one unit. Its id is `<kind>:<object>`, so an object has one placement."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    kind: PlacedKind
    object: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    placed_by: str = Field(min_length=1)
    placed_at: datetime

    @model_validator(mode="after")
    def _one_per_object(self) -> Placement:
        if self.id != placement_id(self.kind, self.object):
            raise ValueError("a placement's identifier is its kind and its object")
        return self


def placement_id(kind: PlacedKind, name: str) -> str:
    return f"{kind}:{name}"


class PlaceKind(StrEnum):
    KNOWLEDGE = "knowledge"
    """The organisation's own knowledge system: the record, where one is configured."""
    TAKTUS = "taktus"
    """Taktus's own page, readable on any device: only where no system is configured."""


class Place(Value):
    kind: PlaceKind
    link: str = Field(min_length=1, max_length=2000)
    """What opens it."""


class Filing(Value):
    """Where one thing Taktus set up is documented, and in which unit it is filed."""

    id: str = Field(min_length=1)
    """`<kind>:<object>`, as its placement."""
    tenant: str = Field(min_length=1)
    kind: PlacedKind
    object: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    places: tuple[Place, ...] = Field(min_length=1)
    set_up_by: str = Field(min_length=1)
    filed_at: datetime


class KnowledgeHome(Value):
    """A knowledge system the organisation configured for a unit and everything below it: the
    base link documentation is filed under. One record per unit that has one."""

    id: str = Field(min_length=1)
    """The unit's identifier."""
    tenant: str = Field(min_length=1)
    base: str = Field(min_length=1, max_length=2000)
    """The link below which the unit's documentation lives in that system."""
