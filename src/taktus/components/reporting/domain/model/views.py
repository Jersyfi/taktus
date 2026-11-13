"""Views, their figures, report definitions and a person's own view (ADR-0241, ADR-0242,
ADR-0245).

`reporting` owns no figure (ADR-0029): a `Shown` is a figure its owner computed and the
composition handed in. What this module owns is who sees which figure, and when it is told.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

ROLE = r"^[a-z][a-z0-9-]*$"
FIGURE = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
OWNER = "owner"

type GroupBy = Literal["tenant", "process", "stream", "unit", "role"]
type Depth = Literal["short", "full"]
type Language = Literal["en", "de"]
type Cadence = Literal["day", "week"]


class Shown(Value):
    """A figure as its owner handed it in; nothing here is computed."""

    id: str = Field(pattern=FIGURE)
    component: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    scope: Literal[
        "tenant",
        "process",
        "stream",
        "unit",
        "role",
        "supplier",
        "domain",
        "chain",
        "assistant",
        "run",
        "step",
    ]
    subject: str = Field(min_length=1)
    since: datetime | None = None
    until: datetime | None = None
    value: float | None = None
    withheld: str | None = None
    assumption: bool = False
    simulation: bool = False
    method: str = Field(min_length=1)
    basis: dict[str, Any] = Field(default_factory=dict)


class ViewDefinition(Value):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    title: str = Field(min_length=1)
    figures: tuple[str, ...] = Field(min_length=1)
    roles: tuple[str, ...] = ()
    persons: tuple[str, ...] = ()
    """Identities the view is given to beyond their roles; it never widens an entitlement."""
    group_by: GroupBy = "process"


class ViewConfiguration(Value):
    """A tenant's views and who is entitled to which figure (ADR-0241 §2)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    configured_at: datetime
    views: tuple[ViewDefinition, ...]
    entitlements: dict[str, tuple[str, ...]]
    """Per figure identifier: the roles entitled to it."""
    depth: dict[str, Depth] = Field(default_factory=dict)
    language: dict[str, Language] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _no_person(cls, data: Any) -> Any:
        """A view that groups by person is refused, whatever the field is called."""
        for view in (data or {}).get("views", ()) if isinstance(data, dict) else ():
            if isinstance(view, dict) and str(view.get("group_by", "")).lower() in (
                "person",
                "identity",
                "people",
                "employee",
            ):
                raise ValueError("a view groups by role, team or department, never by person")
        return data

    @model_validator(mode="after")
    def _known(self) -> ViewConfiguration:
        ids = [v.id for v in self.views]
        if len(ids) != len(set(ids)):
            raise ValueError("a view is defined twice")
        return self


class ReportDefinition(Value):
    """A report: its reader, its trigger and the channel its reader chose (ADR-0242 §1)."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    tenant: str = Field(min_length=1)
    reader_role: str = Field(pattern=ROLE)
    """The role that reads it: a report without a reader is refused."""
    trigger: Literal["request", "schedule"]
    every: Cadence | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    weekday: int | None = Field(default=None, ge=0, le=6)
    """0 is Monday; for a weekly report only."""
    channel: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    address: str = Field(min_length=1)
    set_at: datetime
    last_slot: str | None = None
    """The slot delivered last: a slot is said once."""

    @model_validator(mode="after")
    def _scheduled(self) -> ReportDefinition:
        if self.trigger == "schedule":
            if self.every is None or self.hour is None:
                raise ValueError("a scheduled report needs `every` and `hour`")
            if self.every == "week" and self.weekday is None:
                raise ValueError("a weekly report needs its weekday")
        return self


class Goal(Value):
    title: str = Field(min_length=1)
    hours_per_week: float = Field(gt=0)


class OwnView(Value):
    """A person's own view: its settings, the person's alone (ADR-0245 §1). Its only person
    field is `reader`; nobody else reads it (`tests/components/reporting/test_own_view.py`)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    reader: str = Field(min_length=1)
    shared_with: tuple[str, ...] = ()
    """Roles the person shows it to; withdrawn by leaving them out."""
    goals: tuple[Goal, ...] = ()
    line: Literal["never", "day", "week"] = "never"
    channel: str | None = None
    address: str | None = None
    set_at: datetime
    last_slot: str | None = None
