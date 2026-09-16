"""The rules that make a process graph valid, each as one function returning its findings.

The step rules restate what the shared kernel's `Step` already refuses in its constructor. They
are stated again here because this component owns them (ADR-0004, ADR-0014): a step that reaches
this component by another road than the constructor — deserialised without validation, built by
a later planner — meets the same rules. tests/exactness holds both roads to ADR-0014.

The graph rules concern what a single step cannot see: every dependency names a step of the same
process, no step depends on itself through any chain, and every step is connected to the rest.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence

from taktus.shared.v1 import (
    EXACT_ADMISSIBLE,
    NON_PRODUCING,
    PINNED,
    PRODUCING,
    VARIABLE,
    ExactnessClass,
    Step,
    StepId,
)

Findings = list[str]


def exactness_admits_method(step: Step) -> Findings:
    """ADR-0014: an exact result comes from rule or statistics only."""
    if step.exactness is ExactnessClass.EXACT and step.method not in EXACT_ADMISSIBLE:
        admissible = " or ".join(sorted(EXACT_ADMISSIBLE))
        return [
            f"step {step.id!r} is classed exact but its result would come from {step.method}; "
            f"an exact result comes from {admissible} only"
        ]
    return []


def producing_steps_carry_a_class(step: Step) -> Findings:
    """ADR-0018: a result-producing step carries an exactness class; wait and human carry none."""
    if step.method in PRODUCING and step.exactness is None:
        return [
            f"step {step.id!r} on {step.method} produces a result and carries no exactness class"
        ]
    if step.method in NON_PRODUCING and step.exactness is not None:
        return [
            f"step {step.id!r} on {step.method} produces no result and carries an exactness class"
        ]
    return []


def variable_methods_have_a_fallback(step: Step) -> Findings:
    """ADR-0004: a method that can vary names where the step goes when it is not good enough."""
    if step.method in VARIABLE and step.fallback is None:
        return [f"step {step.id!r} on {step.method} can vary and names no fallback"]
    return []


def pinned_methods_name_their_model(step: Step) -> Findings:
    """ADR-0004: ml and neural are reproducible only at a pinned model version."""
    if step.method in PINNED and step.model is None:
        return [f"step {step.id!r} on {step.method} pins no model version"]
    return []


def validate_step(step: Step) -> Findings:
    return (
        exactness_admits_method(step)
        + producing_steps_carry_a_class(step)
        + variable_methods_have_a_fallback(step)
        + pinned_methods_name_their_model(step)
    )


def steps_are_unique(steps: Sequence[Step]) -> Findings:
    seen: set[StepId] = set()
    findings: Findings = []
    for step in steps:
        if step.id in seen:
            findings.append(f"step {step.id!r} is defined twice")
        seen.add(step.id)
    return findings


def dependencies_exist(steps: Sequence[Step]) -> Findings:
    ids = {step.id for step in steps}
    return [
        f"step {step.id!r} depends on {dependency!r}, which is not a step of this process"
        for step in steps
        for dependency in step.dependencies
        if dependency not in ids
    ]


def graph_is_acyclic(steps: Sequence[Step]) -> Findings:
    """Kahn's algorithm: whatever cannot be ordered lies on a cycle."""
    remaining = _in_degrees(steps)
    dependants = _dependants(steps)
    ready = deque(step.id for step in steps if remaining[step.id] == 0)
    while ready:
        current = ready.popleft()
        for dependant in dependants[current]:
            remaining[dependant] -= 1
            if remaining[dependant] == 0:
                ready.append(dependant)
    on_cycle = [step_id for step_id, degree in remaining.items() if degree > 0]
    if on_cycle:
        return [f"the graph has a cycle through {', '.join(repr(s) for s in on_cycle)}"]
    return []


def every_step_is_reachable(steps: Sequence[Step]) -> Findings:
    """Every step is connected to the rest of the graph through its edges, in either direction.
    A step that nothing depends on and that depends on nothing, in a process of more than one
    step, cannot be reached from the process and belongs to another one."""
    if len(steps) <= 1:
        return []
    neighbours: dict[StepId, set[StepId]] = {step.id: set() for step in steps}
    for step in steps:
        for dependency in step.dependencies:
            if dependency in neighbours:
                neighbours[step.id].add(dependency)
                neighbours[dependency].add(step.id)
    reached: set[StepId] = set()
    frontier = [steps[0].id]
    while frontier:
        current = frontier.pop()
        if current in reached:
            continue
        reached.add(current)
        frontier.extend(neighbours[current] - reached)
    unreachable = [step.id for step in steps if step.id not in reached]
    if unreachable:
        return [
            f"{', '.join(repr(s) for s in unreachable)} cannot be reached from the rest of the "
            "graph: no edge connects them"
        ]
    return []


def validate_graph(steps: Sequence[Step]) -> Findings:
    findings: Findings = []
    for step in steps:
        findings.extend(validate_step(step))
    findings.extend(steps_are_unique(steps))
    if findings:
        return findings  # the graph rules assume distinct, valid steps
    findings.extend(dependencies_exist(steps))
    if findings:
        return findings  # the order and reachability rules assume every edge exists
    findings.extend(graph_is_acyclic(steps))
    findings.extend(every_step_is_reachable(steps))
    return findings


def topological_order(steps: Sequence[Step]) -> tuple[Step, ...]:
    """The steps in an order that respects every dependency; ties keep the declared order, so
    that the same graph always runs in the same order. Assumes a validated graph."""
    by_id = {step.id: step for step in steps}
    remaining = _in_degrees(steps)
    dependants = _dependants(steps)
    position = {step.id: index for index, step in enumerate(steps)}
    ready = sorted((step.id for step in steps if remaining[step.id] == 0), key=position.__getitem__)
    ordered: list[Step] = []
    while ready:
        current = ready.pop(0)
        ordered.append(by_id[current])
        released = []
        for dependant in dependants[current]:
            remaining[dependant] -= 1
            if remaining[dependant] == 0:
                released.append(dependant)
        ready = sorted([*ready, *released], key=position.__getitem__)
    return tuple(ordered)


def _in_degrees(steps: Iterable[Step]) -> dict[StepId, int]:
    return {step.id: len(step.dependencies) for step in steps}


def _dependants(steps: Sequence[Step]) -> dict[StepId, list[StepId]]:
    dependants: dict[StepId, list[StepId]] = {step.id: [] for step in steps}
    for step in steps:
        for dependency in step.dependencies:
            dependants[dependency].append(step.id)
    return dependants
