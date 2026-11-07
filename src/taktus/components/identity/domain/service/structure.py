"""The rules of the organisation's structure (ADR-0275, ADR-0276). Pure: units and placements in,
answers out.

- **Visibility.** A reader in a context sees what is placed in the context's unit and in every
  unit above it. A sibling's, and anything below, are not seen. A person's default context is
  every unit they belong to that is not private; a private project is seen only from inside it.
- **Sharing.** A shared agent, connector, model or skill placed in a unit is used by the
  processes of that unit and of every unit below it.
- **Cost.** A run's consumption is attributed to its unit and counted in every unit above it,
  up to the first private unit: a private unit's consumption is in no figure above it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from taktus.components.identity.domain.model.structure import (
    SHARED_KINDS,
    KnowledgeHome,
    Place,
    PlacedKind,
    PlaceKind,
    Placement,
    StructureUnit,
)


class StructureRefused(ValueError):
    """What the structure does not allow, in one sentence."""


type Units = Mapping[str, StructureUnit]


def path(units: Units, unit: str) -> tuple[str, ...]:
    """The unit's path from the root, the unit last. A unit the structure does not hold is
    refused."""
    chain: list[str] = []
    current: str | None = unit
    while current is not None:
        if current not in units or current in chain:
            raise StructureRefused(f"no unit {unit!r} in the structure")
        chain.append(current)
        current = units[current].parent
    return tuple(reversed(chain))


def above_or_self(units: Units, ancestor: str, unit: str) -> bool:
    return ancestor in path(units, unit)


def belongs(units: Units, identity: str, org_path: Sequence[str]) -> frozenset[str]:
    """The units an identity belongs to: those its organisational path names, and those that
    name it as a member or owner."""
    named = {u for u in org_path if u in units}
    named |= {u.id for u in units.values() if identity in u.members or identity == u.owner}
    return frozenset(named)


def context(units: Units, identity: str, org_path: Sequence[str]) -> frozenset[str]:
    """The default context: every unit the identity belongs to that is not private, never one
    inside a private unit."""
    return frozenset(u for u in belongs(units, identity, org_path) if not _inside_private(units, u))


def seen(units: Units, within: Iterable[str]) -> frozenset[str]:
    """The units a reader in the context `within` sees: each one and every unit above it."""
    return frozenset(u for one in within for u in path(units, one))


def unseen(
    units: Units, placements: Iterable[Placement], within: Iterable[str], kind: PlacedKind
) -> frozenset[str]:
    """The objects of `kind` placed where the context does not see. An object nobody placed is
    in the root, which every context sees."""
    visible = seen(units, within)
    return frozenset(p.object for p in placements if p.kind is kind and p.unit not in visible)


def unit_of(placements: Iterable[Placement], kind: PlacedKind, name: str, root: str) -> str:
    for placed in placements:
        if placed.kind is kind and placed.object == name:
            return placed.unit
    return root


def usable(units: Units, shared_unit: str, process_unit: str) -> bool:
    """Whether what is placed in `shared_unit` is used by a process placed in `process_unit`."""
    return above_or_self(units, shared_unit, process_unit)


def usable_by(
    units: Units, placements: Sequence[Placement], process: str, root: str
) -> dict[PlacedKind, frozenset[str]]:
    """Every shared object a process may use, by kind; shared objects nobody placed are in the
    root and used by every process."""
    unit = unit_of(placements, PlacedKind.PROCESS, process, root)
    found: dict[PlacedKind, set[str]] = defaultdict(set)
    for placed in placements:
        if placed.kind in SHARED_KINDS and usable(units, placed.unit, unit):
            found[placed.kind].add(placed.object)
    return {kind: frozenset(found[kind]) for kind in SHARED_KINDS}


def attributed(units: Units, unit: str) -> tuple[str, ...]:
    """Every unit whose figures count a run of `unit`: the unit and those above it, up to the
    first private one — a private unit's consumption is in no figure above it."""
    chain = path(units, unit)
    counted: list[str] = []
    for one in reversed(chain):
        counted.append(one)
        if units[one].private:
            break
    return tuple(reversed(counted))


def figures(
    units: Units, consumed: Iterable[tuple[str, Mapping[str, float]]]
) -> dict[str, dict[str, float]]:
    """The consumption of each unit, its own and that of the units below it that it counts:
    `consumed` is one `(unit, amounts)` per run."""
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for unit, amounts in consumed:
        for counted in attributed(units, unit):
            for currency, amount in amounts.items():
                totals[counted][currency] += amount
    return {u: dict(a) for u, a in sorted(totals.items())}


def _inside_private(units: Units, unit: str) -> bool:
    return any(units[u].private for u in path(units, unit))


def documented_at(
    units: Units,
    homes: Mapping[str, KnowledgeHome],
    unit: str,
    kind: PlacedKind,
    name: str,
    taktus_link: str,
) -> tuple[Place, ...]:
    """Where something filed in `unit` is documented: under the knowledge system configured for
    the unit or the nearest unit above it, and then there alone; inside Taktus only where no
    unit on its path configured one (UC-1.4 §2)."""
    for one in reversed(path(units, unit)):
        home = homes.get(one)
        if home is not None:
            return (Place(kind=PlaceKind.KNOWLEDGE, link=f"{home.base.rstrip('/')}/{kind}/{name}"),)
    return (Place(kind=PlaceKind.TAKTUS, link=taktus_link),)
