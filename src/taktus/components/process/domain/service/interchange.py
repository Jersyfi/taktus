"""A BPMN model read into a plan draft, and a process version written as one (UC-4.23,
ADR-0168 §3 to §5).

`drafts_of` reads a document into one draft per process of it; `draft_of` turns one neutral
model of `taktus.wire.bpmn` into a draft. No method is chosen by either: every step names the
kinds its task suggests, and the questions say what the person must answer (`open_questions`).
`bundle_of` turns a filled draft into a bundle document, and refuses while a question is open.

`model_of` is the other direction: a process version as a neutral model, with gateways derived
from the graph and the steps' `when`, a lane per role, and Taktus's extension on each task and on
the process. `export` writes it. Both are a projection: nothing of it is stored.

Each is a rule: the same model gives the same draft, the same version the same document.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from taktus.components.process.domain.model.draft import (
    Draft,
    DraftGateway,
    DraftStep,
    Question,
)
from taktus.components.process.domain.model.process import ProcessVersion
from taktus.shared.v1 import Method, Step
from taktus.wire import bpmn

ALL_METHODS = tuple(Method)
CANDIDATES: Mapping[str, tuple[Method, ...]] = {
    "userTask": (Method.HUMAN,),
    "manualTask": (Method.HUMAN,),
    "businessRuleTask": (Method.RULE, Method.STATISTICS, Method.ML),
    "scriptTask": (Method.RULE,),
    "serviceTask": (Method.WORKER, Method.RULE, Method.LLM),
    "sendTask": (Method.WORKER, Method.RULE, Method.LLM),
    "callActivity": (Method.WORKER, Method.RULE, Method.LLM),
    "receiveTask": (Method.WAIT,),
    "intermediateCatchEvent": (Method.WAIT,),
}
"""The method kinds each kind of task suggests (ADR-0168 §3). A task of no kind suggests all."""

ELEMENT_OF: Mapping[Method, str] = {
    Method.HUMAN: "userTask",
    Method.WAIT: "receiveTask",
    Method.RULE: "businessRuleTask",
    Method.STATISTICS: "businessRuleTask",
}
"""The task kind a method is written as; every other method is a service task (§5)."""

GATEWAY_KINDS: Mapping[str, str] = {
    "exclusiveGateway": "exclusive",
    "inclusiveGateway": "inclusive",
    "parallelGateway": "parallel",
    "eventBasedGateway": "event",
    "complexGateway": "complex",
}
BRANCHING = frozenset({"exclusiveGateway", "inclusiveGateway", "complexGateway"})
AUTOMATED_LANE = "lane_taktus"
START, END = "start_event", "end_event"
"""Identifiers of what is no step carry an underscore, which a step identifier never does."""
OTHERWISE = "otherwise: none of the other branches' conditions holds"


def slug(text: str, prefix: str) -> str:
    """A lowercase identifier with hyphens, starting with a letter."""
    found = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not found or not found[0].isalpha():
        found = f"{prefix}-{found}".rstrip("-")
    return found


def drafts_of(data: bytes) -> tuple[Draft, ...]:
    """One draft per process of the document that holds a task. Raises `bpmn.Unreadable`."""
    found = tuple(draft_of(m) for m in bpmn.read(data) if any(_is_step(n) for n in m.nodes))
    if not found:
        raise bpmn.Unreadable("the model holds no process with a task")
    return found


def _is_step(node: bpmn.Node) -> bool:
    return node.kind == "task" or node.element == "intermediateCatchEvent"


def draft_of(model: bpmn.Model) -> Draft:
    """The model as a plan draft: its tasks proposed as steps, no method chosen (§3)."""
    nodes = {n.id: n for n in model.nodes}
    ours = bool(model.extension)
    ids: dict[str, str] = {}
    for node in model.nodes:
        if not _is_step(node):
            continue
        if node.extension and re.fullmatch(r"[a-z][a-z0-9-]*", node.id):
            candidate = node.id
        else:
            candidate = slug(node.name or node.id, "step")
        unique, n = candidate, 2
        while unique in ids.values():
            unique, n = f"{candidate}-{n}", n + 1
        ids[node.id] = unique
    incoming: dict[str, list[bpmn.Flow]] = {n: [] for n in nodes}
    outgoing: dict[str, list[bpmn.Flow]] = {n: [] for n in nodes}
    for flow in model.flows:
        if flow.source in nodes and flow.target in nodes:
            incoming[flow.target].append(flow)
            outgoing[flow.source].append(flow)
    before: dict[str, list[str]] = {n: [f.source for f in incoming[n]] for n in nodes}
    after: dict[str, list[str]] = {n: [f.target for f in outgoing[n]] for n in nodes}
    for node in model.nodes:
        if node.element == "boundaryEvent" and node.attached_to in nodes:
            before[node.id].append(node.attached_to)
            after[node.attached_to].append(node.id)

    def nearest(start: str, links: Mapping[str, list[str]]) -> list[str]:
        found: list[str] = []
        seen = {start}
        frontier = list(links[start])
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if current in ids:
                found.append(ids[current])
            else:
                frontier.extend(links[current])
        return sorted(set(found), key=found.index)

    depends = {ids[n]: nearest(n, before) for n in ids}
    not_imported: list[str] = list(model.unread)
    for loop_from, loop_to in _back_edges(depends):
        depends[loop_to].remove(loop_from)
        not_imported.append(
            f"the flow from {loop_from!r} back to {loop_to!r}: it closes a loop, and a process of "
            "Taktus has none — a repetition is a new run"
        )
    lane_of: dict[str, str] = {}
    roles: dict[str, str] = {}
    for lane in model.lanes:
        if lane.extension.get("automated") == "true":
            continue
        role = lane.extension.get("role") or slug(lane.name or lane.id, "role")
        roles[lane.name or lane.id] = role
        for ref in lane.nodes:
            lane_of[ref] = role
    steps: list[DraftStep] = []
    for node_id, step_id in ids.items():
        node = nodes[node_id]
        condition: str | None = None
        when: tuple[Mapping[str, Any], ...] | None = None
        for flow in incoming[node_id]:
            source = nodes[flow.source]
            if flow.condition is not None:
                condition = flow.condition
                if flow.language == bpmn.WHEN:
                    when = _conditions(flow.condition)
            elif source.element in BRANCHING and source.default == flow.id:
                condition = OTHERWISE
        suggested = node.extension.get("method")
        steps.append(
            DraftStep(
                id=step_id,
                name=node.name or node.id,
                element=node.element,
                depends_on=tuple(depends[step_id]),
                role=lane_of.get(node_id),
                condition=condition,
                when=when,
                candidates=CANDIDATES.get(node.element, ALL_METHODS),
                suggested=Method(suggested) if suggested in set(Method) else None,
            )
        )
        if node.performers:
            not_imported.append(
                f"the performer of {step_id!r} ({', '.join(node.performers)}): a step names a "
                "role through its lane, never a person (principle 14)"
            )
    gateways = tuple(
        DraftGateway(
            id=node.id,
            kind=GATEWAY_KINDS[node.element],  # type: ignore[arg-type]
            before=tuple(nearest(node.id, before)),
            after=tuple(nearest(node.id, after)),
        )
        for node in model.nodes
        if node.element in GATEWAY_KINDS
    )
    for node in model.nodes:
        if node.element == "boundaryEvent":
            not_imported.append(
                f"the boundary event {node.id!r} on {ids.get(node.attached_to or '', '?')!r}: "
                "what happens when a step fails is its fallback, or a step on escalation"
            )
        if node.element == "startEvent" and node.definitions:
            not_imported.append(
                f"the start event {node.id!r} ({', '.join(node.definitions)}): a trigger is "
                "declared in the bundle"
            )
    level = model.extension.get("level")
    draft = Draft(
        source=f"bpmn:{model.id}",
        id=model.id
        if ours and re.fullmatch(r"[a-z][a-z0-9-]*", model.id)
        else slug(model.name or model.id, "process"),
        name=model.name or model.id,
        steps=tuple(steps),
        gateways=gateways,
        roles=roles,
        level=2 if level == "2" else 1,
        not_imported=tuple(not_imported),
    )
    return draft.model_copy(update={"questions": tuple(open_questions(draft))})


def _conditions(text: str) -> tuple[Mapping[str, Any], ...] | None:
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if isinstance(parsed, list) and parsed and all(isinstance(c, dict) for c in parsed):
        return tuple(parsed)
    return None


def _back_edges(depends: Mapping[str, list[str]]) -> list[tuple[str, str]]:
    """The dependencies that close a loop, as `(from, to)`: found by a depth-first walk forward
    from the steps that depend on nothing, in the model's order, so that the flow that leads
    back is the one dropped."""
    after: dict[str, list[str]] = {s: [] for s in depends}
    for step, dependencies in depends.items():
        for dependency in dependencies:
            after[dependency].append(step)
    state: dict[str, int] = {}
    found: list[tuple[str, str]] = []

    def visit(step: str) -> None:
        state[step] = 1
        for successor in after[step]:
            if state.get(successor) == 1:
                found.append((step, successor))
            elif successor not in state:
                visit(successor)
        state[step] = 2

    for step in sorted(depends, key=lambda s: bool(depends[s])):
        if step not in state:
            visit(step)
    return found


def open_questions(draft: Draft) -> list[Question]:
    """What must be answered before the draft can become a bundle, in the draft's order."""
    found: list[Question] = []
    for lane, role in draft.roles.items():
        if role not in draft.confirmed:
            found.append(
                Question(
                    about=role,
                    asks=f"confirm that the lane {lane!r} names a role and not a person: list "
                    f"{role!r} under `confirmed`, or change the role of its steps",
                )
            )
    for step in draft.steps:
        if step.method is None:
            kinds = ", ".join(step.candidates)
            hint = f"; the model suggests {step.suggested}" if step.suggested else ""
            found.append(
                Question(
                    about=step.id,
                    asks=f"choose the method of {step.name!r} — its kind of task suggests {kinds}"
                    f"{hint} — with the reason for it and the methods not chosen",
                )
            )
        elif step.reason is None or step.rejected is None:
            found.append(
                Question(
                    about=step.id,
                    asks=f"give the reason for {step.method} at {step.name!r}, and the methods "
                    "not chosen under `rejected`",
                )
            )
        if step.condition is not None and step.when is None and step.condition != OTHERWISE:
            found.append(
                Question(
                    about=step.id,
                    asks=f"state the condition {step.condition!r} as machine checks under `when`",
                )
            )
        if (
            step.role is not None
            and step.role not in draft.confirmed
            and step.role not in draft.roles.values()
        ):
            found.append(Question(about=step.id, asks=f"confirm the role {step.role!r}"))
    for gateway in draft.gateways:
        if gateway.kind in {"event", "complex"}:
            found.append(
                Question(
                    about=gateway.id,
                    asks=f"the {gateway.kind} gateway {gateway.id!r} decides by what happens "
                    "first: state each path after it as a step's `when`",
                )
            )
    return found


def bundle_of(draft: Draft, version: str = "1") -> dict[str, Any]:
    """The filled draft as a bundle document; `ValueError` naming every open question."""
    questions = open_questions(draft)
    if questions:
        raise ValueError(tuple(f"{q.about}: {q.asks}" for q in questions))
    steps: list[dict[str, Any]] = []
    for step in draft.steps:
        role = step.role if step.role in draft.confirmed else None
        entry: dict[str, Any] = {
            "id": step.id,
            "method": str(step.method),
            "reason": step.reason,
            "rejected": [r.document() for r in step.rejected or ()],
        }
        if step.exactness is not None:
            entry["exactness"] = str(step.exactness)
        if step.checks is not None:
            entry["checks"] = [c.document() for c in step.checks]
        fallback = step.fallback
        if fallback is not None:
            document = fallback.document()
            if fallback.to is Method.HUMAN and fallback.role is None and role is not None:
                document["role"] = role
            entry["fallback"] = document
        if step.model is not None:
            entry["model"] = step.model
        if step.requires is not None:
            entry["requires"] = list(step.requires)
        if step.depends_on:
            entry["depends_on"] = list(step.depends_on)
        if step.method is Method.HUMAN and role is not None:
            entry["role"] = role
            if step.expertise is not None:
                entry["expertise"] = list(step.expertise)
        work = dict(step.work or {})
        if step.when is not None:
            work["when"] = [dict(c) for c in step.when]
        if work:
            entry["work"] = work
        steps.append(entry)
    acts = "a person confirms each step" if draft.level == 2 else "a person performs every act"
    return {
        "id": draft.id,
        "version": version,
        "name": draft.name,
        "autonomy": {
            "level": draft.level,
            "reason": f"a process taken from a model ({draft.source}): {acts} until its runs "
            "show the methods chosen hold",
            "toward_next": "runs of the process that nobody had to correct",
        },
        "reason": f"taken from the process model {draft.source} through a plan draft",
        "steps": steps,
    }


# Export -------------------------------------------------------------------------------------


def export(version: ProcessVersion) -> bytes:
    """The version as a BPMN document (§5)."""
    return bpmn.write(model_of(version))


def model_of(version: ProcessVersion) -> bpmn.Model:
    """The version as a neutral model: steps as tasks, gateways from the graph and the `when`."""
    steps = {s.id: s for s in version.steps}
    order = [s.id for s in version.steps]
    when = {
        s: tuple(version.work[s]["when"])
        for s in order
        if isinstance((version.work.get(s) or {}).get("when"), list | tuple)
        and (version.work[s]["when"])
    }
    nodes: list[bpmn.Node] = [bpmn.Node(id=START, element="startEvent")]
    flows: list[bpmn.Flow] = []

    def flow(source: str, target: str, conditions: Sequence[Any] | None = None) -> None:
        flows.append(
            bpmn.Flow(
                id=f"flow_{len(flows) + 1}",
                source=source,
                target=target,
                condition=None if conditions is None else bpmn.conditions_text(conditions),
                language=None if conditions is None else bpmn.WHEN,
            )
        )

    for step_id in order:
        step = steps[step_id]
        extension = {"method": str(step.method), "text": " ".join(step.reason.split())}
        if step.exactness is not None:
            extension["exactness"] = str(step.exactness)
        nodes.append(
            bpmn.Node(
                id=step_id,
                element=ELEMENT_OF.get(step.method, "serviceTask"),
                name=step_id.replace("-", " "),
                extension=extension,
            )
        )
    # Every target a source leads into: a step without a condition, or the exclusive gateway of
    # the steps with a condition that share their dependencies.
    groups: dict[tuple[str, ...], list[str]] = {}
    for step_id in order:
        if step_id in when:
            groups.setdefault(tuple(sorted(steps[step_id].dependencies)), []).append(step_id)
    entries: list[tuple[str, tuple[str, ...]]] = []
    for step_id in order:
        if step_id not in when:
            entries.append((step_id, tuple(sorted(steps[step_id].dependencies))))
    for index, (dependencies, members) in enumerate(groups.items(), 1):
        gateway = f"split_{index}"
        nodes.append(bpmn.Node(id=gateway, element="exclusiveGateway"))
        entries.append((gateway, dependencies))
        for member in members:
            flow(gateway, member, when[member])
    leads: dict[str, list[str]] = {}
    for target, dependencies in entries:
        sources = list(dependencies) or [START]
        if len(sources) > 1:
            join = f"join_{target}"
            kind = "exclusiveGateway" if all(s in when for s in sources) else "parallelGateway"
            nodes.append(bpmn.Node(id=join, element=kind))
            for source in sources:
                leads.setdefault(source, []).append(join)
            flow(join, target)
        else:
            leads.setdefault(sources[0], []).append(target)
    dependents = {d for s in version.steps for d in s.dependencies}
    last = [s for s in order if s not in dependents]
    nodes.append(bpmn.Node(id=END, element="endEvent"))
    if len(last) > 1:
        kind = "exclusiveGateway" if all(s in when for s in last) else "parallelGateway"
        nodes.append(bpmn.Node(id=f"join_{END}", element=kind))
        for source in last:
            leads.setdefault(source, []).append(f"join_{END}")
        flow(f"join_{END}", END)
    else:
        leads.setdefault(last[0], []).append(END)
    for source in [START, *order]:
        targets = leads.get(source, [])
        if len(targets) > 1:
            fork = f"fork_{source}"
            nodes.append(bpmn.Node(id=fork, element="parallelGateway"))
            flow(source, fork)
            for target in targets:
                flow(fork, target)
        elif targets:
            flow(source, targets[0])
    return bpmn.Model(
        id=version.process_id,
        name=version.name,
        nodes=tuple(nodes),
        flows=tuple(flows),
        lanes=_lanes(version.steps, [n.id for n in nodes]),
        extension={"version": version.version, "level": str(version.autonomy.level)},
    )


def _lanes(steps: Iterable[Step], every: Sequence[str]) -> tuple[bpmn.Lane, ...]:
    """A lane per role a step's performer names, in the order of first use, and the lane
    `Taktus` for everything else; none where no step names a role."""
    by_role: dict[str, list[str]] = {}
    for step in steps:
        if step.performer is not None:
            by_role.setdefault(step.performer, []).append(step.id)
    if not by_role:
        return ()
    placed = {s for members in by_role.values() for s in members}
    lanes = [
        bpmn.Lane(id=f"lane_{role}", name=role, nodes=tuple(members), extension={"role": role})
        for role, members in by_role.items()
    ]
    rest = tuple(n for n in every if n not in placed)
    lanes.append(
        bpmn.Lane(id=AUTOMATED_LANE, name="Taktus", nodes=rest, extension={"automated": "true"})
    )
    return tuple(lanes)
