"""The rules of shares (ADR-0246, ADR-0247). Pure.

- `visible` keeps of the shares those that admit a viewer.
- `withdrawal` decides whether a model or a connector may be withdrawn, from its removal verdict.
- `use` counts an entry's calls per organisational unit, and the viewer's own calls apart; it
  never returns another person's own count (principle 14, ADR-0015).
- `credentials` replaces each credential name a call names with the caller's own parameter, or
  says which name the caller has none for.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from taktus.components.catalog.domain.model.maturity import RemovalResult, Verdict
from taktus.components.catalog.domain.model.shares import CallerCredential, CatalogueShare


def visible(
    shares: Iterable[CatalogueShare], identity: str, org_path: Sequence[str]
) -> list[CatalogueShare]:
    """The shares the viewer is inside, in identifier order. Nothing says the others exist."""
    return sorted((s for s in shares if s.admits(identity, org_path)), key=lambda s: s.id)


@dataclass(frozen=True)
class Withdrawal:
    """Whether a withdrawal takes effect, and the outcome its ledger entry records."""

    allowed: bool
    outcome: str
    reason: str


def withdrawal(removal: RemovalResult | None, *, despite_broke: bool) -> Withdrawal:
    """A model or a connector is withdrawn only with its removal verdict known: none on record
    refuses it; *broke* refuses it unless the person confirms it in the same act (ADR-0246 §5)."""
    if removal is None:
        return Withdrawal(
            False,
            "no_verdict",
            "no removal test is on record for it; run one first, so that what the "
            "withdrawal breaks is known before it takes effect",
        )
    verdict = removal.verdict
    if verdict is Verdict.BROKE and not despite_broke:
        broken = ", ".join(sorted(p.process for p in removal.processes)) or "a process"
        return Withdrawal(
            False,
            "broke",
            f"its removal test of {removal.tested_at.isoformat()} says it breaks {broken}; "
            "withdraw it only by confirming that in the same act",
        )
    return Withdrawal(True, str(verdict), f"its removal verdict is {verdict}")


@dataclass(frozen=True)
class Call:
    """One call of an entry: the run that made it, its organisational unit, who started it."""

    run_id: str
    org_unit: str | None
    identity: str | None


@dataclass(frozen=True)
class Use:
    """An entry's use as a viewer may read it: per unit with no identity in it, and the
    viewer's own calls."""

    by_unit: Mapping[str, int]
    own: int
    total: int


UNPLACED = "(no unit)"


def use(calls: Iterable[Call], viewer: str) -> Use:
    by_unit: Counter[str] = Counter()
    own = 0
    total = 0
    for call in calls:
        total += 1
        by_unit[call.org_unit or UNPLACED] += 1
        if call.identity == viewer:
            own += 1
    return Use(by_unit=dict(sorted(by_unit.items())), own=own, total=total)


@dataclass(frozen=True)
class Resolved:
    """The parameters a call names for its caller; or the names the caller has none for."""

    names: tuple[str, ...]
    lacking: tuple[str, ...]


def credentials(names: Sequence[str], identity: str, bound: Iterable[CallerCredential]) -> Resolved:
    """Each name replaced by the caller's own parameter. A name with no binding of the caller
    is lacking; it never stays as it was (ADR-0247 §2)."""
    mine = {c.name: c for c in bound if c.identity == identity}
    resolved: list[str] = []
    lacking: list[str] = []
    for name in names:
        binding = mine.get(name)
        if binding is None:
            lacking.append(name)
        else:
            resolved.append(binding.parameter)
    return Resolved(names=tuple(resolved), lacking=tuple(lacking))
