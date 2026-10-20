"""The route of a step on a model through its purpose's chain (ADR-0116 §4). A pure function, no
I/O.

The chain is every model configured for the step's purpose, in order. The route is its first
member that fits the step: the tenant's residency rule admits where it processes, it may produce
the step's exactness class, and it is not cooling down. Every member passed over is named with
its reason, so that the route can be read back from the provenance record and computed again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from taktus.ports.model import Permitted, ResolvedModel, admits
from taktus.shared.v1 import ExactnessClass, ProvenanceRoute, RouteSkip


@dataclass(frozen=True)
class Needs:
    """What a step declares that its route must fit."""

    purpose: str
    exactness: ExactnessClass | None
    permitted: Permitted
    data_class: str | None = None


@dataclass(frozen=True)
class Route:
    """The member a step is routed to, or None; every member passed over with its reason; and
    the member the step would take if nothing were cooling down."""

    needs: Needs
    chosen: ResolvedModel | None
    skipped: tuple[RouteSkip, ...]
    fitting: ResolvedModel | None
    """The first member that fits but for its cool-down: what a step admits on while every
    member that fits is cooling down (ADR-0116 §6). The chosen one where one is."""

    @property
    def cooling(self) -> bool:
        """No member was chosen only because every one that fits is cooling down."""
        return self.chosen is None and self.fitting is not None

    def record(self) -> ProvenanceRoute | None:
        """The route as the provenance record carries it; None without a chosen member."""
        if self.chosen is None:
            return None
        return ProvenanceRoute(
            purpose=self.needs.purpose,
            adapter=self.chosen.adapter,
            permitted=self.needs.permitted,
            data_class=self.needs.data_class,
            skipped=self.skipped,
        )

    def why_none(self) -> str:
        """Why no member of the chain fits, in words, naming each member and its reason."""
        if not self.skipped:
            return f"no model is configured for the purpose {self.needs.purpose!r}"
        reasons = "; ".join(f"{s.adapter}: {_said(s.reason, self.needs)}" for s in self.skipped)
        return (
            f"no model configured for the purpose {self.needs.purpose!r} fits the step: {reasons}"
        )


def route(
    chain: Sequence[ResolvedModel],
    needs: Needs,
    cooling: Mapping[str, datetime],
    now: datetime,
) -> Route:
    """The first member of the chain that fits, with every member before it that did not. A
    member whose cool-down ends at or before `now` is not cooling down."""
    skipped: list[RouteSkip] = []
    fitting: ResolvedModel | None = None
    for member in chain:
        if not admits(needs.permitted, member.location):
            skipped.append(RouteSkip(adapter=member.adapter, reason="residency"))
            continue
        if needs.exactness is not None and needs.exactness.value not in member.classes:
            skipped.append(RouteSkip(adapter=member.adapter, reason="exactness"))
            continue
        fitting = fitting or member
        until = cooling.get(member.adapter)
        if until is not None and until > now:
            skipped.append(RouteSkip(adapter=member.adapter, reason="cooling_down"))
            continue
        return Route(needs=needs, chosen=member, skipped=tuple(skipped), fitting=fitting)
    return Route(needs=needs, chosen=None, skipped=tuple(skipped), fitting=fitting)


def _said(reason: str, needs: Needs) -> str:
    if reason == "residency":
        scope = f"data class {needs.data_class!r}" if needs.data_class else "the tenant"
        return f"processes outside what the residency rule permits for {scope} ({needs.permitted})"
    if reason == "exactness":
        return f"may not produce a {needs.exactness} result"
    return "cooling down after a rate limit or a failure"
