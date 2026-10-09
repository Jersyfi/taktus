"""A tenant's anchors: the acts that stay with a person whatever the autonomy level (ADR-0008,
ADR-0022, ADR-0042).

An **anchor configuration** is one tenant's set, each anchor in the shape of
`contracts/shared/v1/Anchor.json`, together with the tenant's **risk classes**: a risk class is
a name for a set of tool actions, as capability patterns, so that an anchor can select by risk
class and the selection can be checked. The set can be reduced but never emptied: a
configuration without a legal or without a correction anchor is refused. The strategic class
may be reduced to nothing; a tenant that does so hands over direction on purpose (ADR-0008,
*Where this promise ends*).

A tenant that configured nothing holds the **shipped default** (`SHIPPED_DEFAULT`): one legal
and one correction anchor, decided by the role `owner`. Its legal anchor is the project's own
list and is not legally reviewed for any jurisdiction (DEC-0029); the catalogue per domain and
jurisdiction is UC-15.5.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pydantic import Field, model_validator

from taktus.shared.v1 import Anchor, AnchorClass, CapabilityPattern, Value

NEVER_EMPTIED: tuple[AnchorClass, ...] = (AnchorClass.LEGAL, AnchorClass.CORRECTION)
"""The classes a configuration may narrow but never leave empty (ADR-0008, ADR-0022 §3)."""

OWNER = "owner"
"""The role the shipped default addresses: the person who owns the tenant (anchors.md)."""


class AnchorConfiguration(Value):
    """One tenant's anchors, stored under the tenant's own identifier."""

    id: str = Field(min_length=1)
    """The tenant: a tenant has one configuration."""
    tenant: str = Field(min_length=1)
    anchors: tuple[Anchor, ...] = Field(min_length=1)
    risk_classes: Mapping[str, tuple[CapabilityPattern, ...]] = Field(default_factory=dict)
    """A risk class by name, as the tool actions it covers."""
    configured_at: datetime | None = None
    """When it was configured; None for the shipped default, which nobody configured."""
    configured_by: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _never_emptied(self) -> AnchorConfiguration:
        problems = refusals(self.tenant, self.anchors, self.risk_classes)
        if self.id != self.tenant:
            problems.insert(0, f"a configuration is stored under its tenant {self.tenant!r}")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def shipped(self) -> bool:
        return self.configured_at is None

    def of_class(self, kind: AnchorClass) -> tuple[Anchor, ...]:
        return tuple(a for a in self.anchors if a.class_ is kind)


def refusals(
    tenant: str,
    anchors: tuple[Anchor, ...],
    risk_classes: Mapping[str, tuple[str, ...]],
) -> list[str]:
    """Why a configuration is refused, in words; empty when it is not."""
    problems: list[str] = []
    for kind in NEVER_EMPTIED:
        if not any(a.class_ is kind for a in anchors):
            problems.append(
                f"the {kind} class is empty: it can be narrowed but never emptied "
                "(ADR-0008, ADR-0022)"
            )
    ids = [a.id for a in anchors]
    for repeated in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"anchor {repeated!r} is configured twice")
    for name, patterns in risk_classes.items():
        if not name or not patterns:
            problems.append(f"risk class {name!r} names no tool action")
    for anchor in anchors:
        if anchor.scope is not None and anchor.scope.tenant not in (None, tenant):
            problems.append(
                f"anchor {anchor.id!r} is scoped to tenant {anchor.scope.tenant!r}, not {tenant!r}"
            )
        for risk in anchor.applies_to.risk_classes or ():
            if risk not in risk_classes:
                problems.append(
                    f"anchor {anchor.id!r} selects the risk class {risk!r}, which the "
                    "configuration does not define: it would never apply"
                )
    return problems


SHIPPED_ANCHORS: tuple[Anchor, ...] = (
    Anchor.model_validate(
        {
            "id": "anc-legal",
            "class": AnchorClass.LEGAL,
            "act": "a legally binding act: a signature, a payment release, a filing, a "
            "termination, a notification or a contract (not legally reviewed for any "
            "jurisdiction, DEC-0029)",
            "applies_to": {"actions": ["legal.*", "payment.release"]},
            "decider": {"role": OWNER},
        }
    ),
    Anchor.model_validate(
        {
            "id": "anc-correction",
            "class": AnchorClass.CORRECTION,
            "act": "correct a result that has left the system (ADR-0022)",
            "applies_to": {"actions": ["correction.*"]},
            "decider": {"role": OWNER},
        }
    ),
)


def shipped_default(tenant: str) -> AnchorConfiguration:
    """What a tenant that configured nothing holds."""
    return AnchorConfiguration(id=tenant, tenant=tenant, anchors=SHIPPED_ANCHORS)
