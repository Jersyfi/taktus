"""The rules of a chain of processes (UC-15.4, ADR-0274). Pure.

`findings` holds a chain to the versions it links: every item from a step of the sending
version, every input the receiving version requires given by exactly one item, and nothing given
that it does not declare. `handover` builds what passes at one boundary from the sending run's
results: every declared item, or the items that are missing, in which case nothing passes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from taktus.components.process.domain.model.chain import Chain, Item
from taktus.components.process.domain.model.process import ProcessVersion

MISSING = object()
"""A result, or a part of one, that the sending run does not hold."""


@dataclass(frozen=True)
class Handed:
    """What passes at a boundary: each item's value by the input it fills, and every item that
    is missing. Where one is missing, nothing passes."""

    given: Mapping[str, Any]
    missing: tuple[Item, ...]


def findings(chain: Chain, versions: Sequence[ProcessVersion]) -> list[str]:
    by_ref = {v.ref: v for v in versions}
    found: list[str] = [
        f"the chain {chain.id!r} links {link.process_version}, which is not registered"
        for link in chain.links
        if link.process_version not in by_ref
    ]
    if found:
        return found
    for before, link in zip(chain.links, chain.links[1:], strict=False):
        sending = by_ref[before.process_version]
        receiving = by_ref[link.process_version]
        steps = {step.id for step in sending.steps}
        given = [item.input for item in link.handover]
        where = f"the handover to {receiving.ref}"
        found.extend(
            f"{where} takes {item.input!r} from {item.step!r}, no step of {sending.ref}"
            for item in link.handover
            if item.step not in steps
        )
        found.extend(
            f"{where} gives {name!r} twice"
            for name in sorted({n for n in given if given.count(n) > 1})
        )
        found.extend(
            f"{where} gives {name!r}, which {receiving.ref} does not declare under `inputs`"
            for name in sorted(set(given) - set(receiving.inputs))
        )
        found.extend(
            f"{where} gives no {name!r}, which {receiving.ref} requires"
            for name in receiving.required_inputs
            if name not in given
        )
    return found


def handover(items: Sequence[Item], results: Mapping[str, Any]) -> Handed:
    """What passes, from the sending run's results by step: every item's value, or the items
    the results do not hold."""
    given: dict[str, Any] = {}
    missing: list[Item] = []
    for item in items:
        value = _part(results.get(item.step, MISSING), item.select)
        if value is MISSING:
            missing.append(item)
        else:
            given[item.input] = value
    return Handed(given={} if missing else given, missing=tuple(missing))


def _part(value: Any, path: str | None) -> Any:
    if value is MISSING or path is None:
        return value
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return MISSING
        value = value[key]
    return value
