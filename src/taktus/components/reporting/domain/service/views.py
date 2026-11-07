"""Who sees which figure (UC-6.4, UC-5.7, ADR-0241). Pure: the configuration, the reader and
the figures their owners computed in; the views and the export out. Both are selected from the
same figures, so a figure shown is exported with the same definition and value.

- A reader holds the views whose roles they hold, and the views given to them by name.
- A view shows only the figures the reader's roles are entitled to: giving a view never widens
  an entitlement. A figure the reader is not entitled to is absent, not greyed out.
- A figure of what Taktus took off people (UC-13.5) is withheld where no role that would do
  the work by hand is held by two identities or more: it would be one person's (ADR-0015).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from taktus.components.reporting.domain.model.views import (
    OWNER,
    Shown,
    ViewConfiguration,
    ViewDefinition,
)

TOO_FEW = 2
RELIEF = frozenset({"value.time_saved_hours", "value.personnel_equivalent"})
"""Figures of what Taktus took off people (UC-13.5 §2): the owner names them."""

COCKPIT = (
    "value.cycle_seconds",
    "value.quality",
    "value.cost_money",
    "value.automation",
    "value.escalation_rate",
)
DEFAULT_VIEWS: tuple[dict[str, Any], ...] = (
    {
        "id": "day",
        "title": "What Taktus did today and what waits",
        "figures": ("run.working", "run.waiting", "value.runs_ended"),
        "group_by": "process",
    },
    {
        "id": "team",
        "title": "Throughput, waiting and escalations",
        "figures": (
            "value.runs_ended",
            "value.cycle_seconds",
            "value.escalation_rate",
            "run.waiting",
        ),
        "group_by": "process",
    },
    {
        "id": "management",
        "title": "Cost, predictability, quality and risk",
        "figures": (
            *COCKPIT,
            "value.cost_takt",
            "value.balance",
            "value.revert_hours_month",
            "value.simulated_unasked",
            "value.simulated_wrong",
        ),
        "group_by": "process",
    },
    {
        "id": "executive",
        "title": "The contribution and the progress of the transformation",
        "figures": ("value.maturity", "value.plan_progress", "value.time_saved_change"),
        "group_by": "unit",
    },
    {
        "id": "investor",
        "title": "The demonstrable value",
        "figures": (
            "value.time_saved_hours",
            "value.personnel_equivalent",
            "value.cost_money",
            "value.balance",
            "value.errors_avoided",
            "value.payback_months",
            "value.cost_per_case",
            "value.cost_per_case_by_hand",
            "value.bus_factor.without_taktus",
        ),
        "group_by": "tenant",
    },
)


def default(tenant: str, known: Iterable[str], at: datetime) -> ViewConfiguration:
    """The shipped default: five example views held by `owner`, every figure entitled to it."""
    return ViewConfiguration(
        id=tenant,
        tenant=tenant,
        configured_at=at,
        views=tuple(ViewDefinition(**v, roles=(OWNER,)) for v in DEFAULT_VIEWS),
        entitlements={figure: (OWNER,) for figure in sorted(set(known))},
    )


def refused(configuration: ViewConfiguration, known: Collection[str]) -> list[str]:
    """Why the configuration cannot be stored: a view naming a figure no owner hands in, or an
    entitlement for one."""
    found = []
    for view in configuration.views:
        for figure in view.figures:
            if figure not in known:
                found.append(f"view {view.id} names {figure}, which no component computes")
    for figure in configuration.entitlements:
        if figure not in known:
            found.append(f"an entitlement names {figure}, which no component computes")
    return found


def views_of(identity: str, roles: Collection[str], c: ViewConfiguration) -> list[ViewDefinition]:
    return [v for v in c.views if identity in v.persons or any(r in roles for r in v.roles)]


def entitled(roles: Collection[str], c: ViewConfiguration, figure: str) -> bool:
    return any(role in roles for role in c.entitlements.get(figure, ()))


def _small(figure: Shown, holders: Mapping[str, int]) -> Shown:
    if figure.id not in RELIEF:
        return figure
    by_hand = [str(r) for r in figure.basis.get("roles_by_hand") or ()]
    if not by_hand or any(holders.get(r, 0) >= TOO_FEW for r in by_hand):
        return figure
    return figure.model_copy(
        update={
            "value": None,
            "withheld": f"withheld: fewer than {TOO_FEW} identities hold the roles that would do "
            "it by hand, so the figure would be one person's (ADR-0015)",
        }
    )


def exported(
    roles: Collection[str],
    c: ViewConfiguration,
    figures: Sequence[Shown],
    holders: Mapping[str, int],
) -> list[Shown]:
    """Every figure the reader is entitled to: the export (UC-5.7)."""
    return [_small(f, holders) for f in figures if entitled(roles, c, f.id)]


def _fits(view: ViewDefinition, figure: Shown) -> bool:
    return figure.id in view.figures and figure.scope == view.group_by


def shown(
    identity: str,
    roles: Collection[str],
    c: ViewConfiguration,
    figures: Sequence[Shown],
    holders: Mapping[str, int],
) -> list[dict[str, Any]]:
    """The reader's views, each with the figures it shows them."""
    allowed = exported(roles, c, figures, holders)
    return [
        {
            "id": v.id,
            "title": v.title,
            "group_by": v.group_by,
            "figures": [f.model_dump(mode="json") for f in allowed if _fits(v, f)],
        }
        for v in views_of(identity, roles, c)
    ]


def depth(roles: Collection[str], c: ViewConfiguration) -> str:
    """The deepest explanation any of the reader's roles is configured for; `full` for the
    owner and wherever nothing is configured for a role."""
    held = [c.depth.get(r, "full" if r == OWNER else "short") for r in roles] or ["short"]
    return "full" if "full" in held else "short"


def language(roles: Collection[str], c: ViewConfiguration) -> str:
    for role in sorted(roles):
        if role in c.language:
            return c.language[role]
    return "en"


COLUMNS = (
    "id",
    "component",
    "scope",
    "subject",
    "value",
    "unit",
    "withheld",
    "since",
    "until",
    "assumption",
    "simulation",
    "definition",
    "method",
)


def as_csv(figures: Iterable[Shown]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for f in figures:
        doc = f.model_dump(mode="json")
        writer.writerow(["" if doc.get(c) is None else doc[c] for c in COLUMNS])
    return out.getvalue()
