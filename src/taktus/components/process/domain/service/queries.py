"""Where a figure a query computed may go (ADR-0262 §4, UC-5.6 §2).

A **reading** here is a step that calls an operation of a querying capability (`QUERYING` in
the connector port): its result is what a statement in a query language computed. Data flows
from step to step through `$from` references in the steps' work. Two rules hold every version:

- A reading is **model-written** when its input refers, directly or through other steps, to the
  result of a step on a language model, a neural method or a worker. Neither the reading nor any
  step that refers to it, directly or through other steps, is of class `exact` or `sourced`: a
  query a language model writes may feed only a step of class `tolerant` or `free`.
- A reading is **fixed** when its `query` is literal text in the version. A step of class
  `exact` that refers to a reading, directly or through other steps, refers only to fixed ones:
  the query was reviewed when the version was registered.

Pure: the version's steps and work in, findings out.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from taktus.ports.connector import QUERYING
from taktus.shared.v1 import ExactnessClass, Method, Step

WRITING: frozenset[Method] = frozenset({Method.LLM, Method.NEURAL, Method.WORKER})
"""The methods whose result can write a query: none of them gives the same result again."""
ADMITTED: frozenset[ExactnessClass] = frozenset({ExactnessClass.TOLERANT, ExactnessClass.FREE})


def _references(node: Any) -> Iterator[str]:
    if isinstance(node, Mapping):
        source = node.get("$from")
        if isinstance(source, str):
            yield source
        for value in node.values():
            yield from _references(value)
    elif isinstance(node, list | tuple):
        for item in node:
            yield from _references(item)


def _reading(work: Mapping[str, Any]) -> bool:
    operation = work.get("operation")
    if work.get("rule") != "connector" or not isinstance(operation, str):
        return False
    return operation.rsplit(".", 1)[0] in QUERYING


def _closure(start: set[str], refers: Mapping[str, set[str]]) -> set[str]:
    """Every step that refers, directly or through other steps, to one of `start`, with them."""
    reached = set(start)
    changed = True
    while changed:
        changed = False
        for step, sources in refers.items():
            if step not in reached and sources & reached:
                reached.add(step)
                changed = True
    return reached


def findings(steps: Sequence[Step], work: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Why the version's figures from queries may not go where it sends them; empty when they
    may."""
    by_id = {step.id: step for step in steps}
    refers = {
        step.id: {r for r in _references(work.get(step.id) or {}) if r in by_id} for step in steps
    }
    readings = [s.id for s in steps if _reading(work.get(s.id) or {})]
    if not readings:
        return []
    written = _closure({s.id for s in steps if s.method in WRITING}, refers)
    found: list[str] = []
    for reading in readings:
        input = (work.get(reading) or {}).get("input")
        inputs = input if isinstance(input, Mapping) else {}
        model = bool(set(_references(inputs)) & written)
        fixed = isinstance(inputs.get("query"), str)
        fed = _closure({reading}, refers)
        for step_id in sorted(fed):
            step = by_id[step_id]
            if model and step.exactness is not None and step.exactness not in ADMITTED:
                what = (
                    "reads with a query"
                    if step_id == reading
                    else f"is fed by the reading {reading!r}, whose query"
                )
                found.append(
                    f"step {step_id!r} is classed {step.exactness} and {what} a model or a "
                    "worker wrote: such a figure may feed only a step of class tolerant or free "
                    "(UC-5.6, ADR-0262 §4). Class it tolerant or free, or fix the query in the "
                    "version"
                )
            elif not fixed and step.exactness is ExactnessClass.EXACT:
                found.append(
                    f"step {step_id!r} is classed exact and is fed by the reading {reading!r}, "
                    "whose query is not literal text in the version: a figure that feeds an "
                    "exact step comes from a query fixed in the version and reviewed when it "
                    "was registered (UC-5.6, ADR-0262 §4)"
                )
    return found
