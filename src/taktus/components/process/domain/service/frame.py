"""What a step may see, held at registration (ADR-0130, UC-7.7).

A step's work may carry `scope` — the case it serves — or `analytic` — the step analyses. This
rule refuses a version whose frame cannot hold, as far as the bundle alone tells:

- a scope whose subject is not one of the run's inputs, declared and required: a `$from`, a
  `$run` or an `$otherwise` would let a step's result, or a default, choose whose data is seen;
- a step that is both scoped and analytic;
- an analytic step that calls a capability other than its source — a mail capability among
  them — reaches a host, holds a credential, or reads what a step that is not analytic
  produced;
- a scoped worker step that reaches a host, which the frame cannot scope.

Whether the tenant declares an analytic step's source free of personal fields is asked by
registration through its port, and again by the run at every call: a declaration can be
withdrawn after a version was stored. Whether an operation leaves the system is its
connector's declaration, which the run reads at the call.

Pure: the version's steps, work and inputs in, findings out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from taktus.shared.v1 import Step

SCOPE = "scope"
ANALYTIC = "analytic"
INPUT = "$input"
SELECT = "$select"
FROM = "$from"
OPERATION = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$")
CAPABILITY = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*)+$")


def findings(
    steps: Sequence[Step],
    work: Mapping[str, Mapping[str, Any]],
    inputs: Mapping[str, Any],
) -> list[str]:
    """Why the version's frames cannot hold; empty when they can. `inputs` are the version's
    input declarations by name, each with `required`."""
    analytic = {step.id for step in steps if ANALYTIC in (work.get(step.id) or {})}
    found: list[str] = []
    for step in steps:
        given = work.get(step.id) or {}
        reasons: list[str] = []
        if SCOPE in given:
            reasons.extend(_scope(given[SCOPE], inputs))
            if ANALYTIC in given:
                reasons.append("a step serves a case or analyses, never both")
            if given.get("allowed_hosts") or _workspace(given):
                reasons.append(
                    "a scoped worker step reaches hosts itself, and the frame cannot scope what "
                    "it reads there"
                )
        if ANALYTIC in given:
            reasons.extend(_analytic(given, analytic))
        found.extend(f"step {step.id!r}: {reason}" for reason in reasons)
    return found


def sources(work: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """The source each analytic step names, by step: what the tenant must declare free of
    personal fields."""
    named: dict[str, str] = {}
    for step_id, given in work.items():
        analytic = (given or {}).get(ANALYTIC)
        if isinstance(analytic, Mapping) and isinstance(analytic.get("source"), str):
            named[str(step_id)] = analytic["source"]
    return named


def _scope(scope: Any, inputs: Mapping[str, Any]) -> list[str]:
    if not isinstance(scope, Mapping) or set(scope) != {"subject"}:
        return ["a scope names its subject, and nothing else: {subject: {$input: <name>}}"]
    subject = scope["subject"]
    if (
        not isinstance(subject, Mapping)
        or INPUT not in subject
        or not set(subject) <= {INPUT, SELECT}
    ):
        return [
            "the subject of a scope is one of the run's inputs, as its intake gave it — "
            "{$input: <name>} — never a step's result, the run's record or a default"
        ]
    name = str(subject[INPUT])
    declared = inputs.get(name)
    if declared is None:
        return [
            f"the subject of the scope is the input {name!r}, which the version does not declare"
        ]
    if getattr(declared, "required", True) is False:
        return [
            f"the subject of the scope is the input {name!r}, which a run may start without: "
            "a case without its subject has no scope"
        ]
    return []


def _analytic(given: Mapping[str, Any], analytic: set[str]) -> list[str]:
    declared = given[ANALYTIC]
    if declared is True:
        source = None
    elif isinstance(declared, Mapping) and set(declared) <= {"source"}:
        source = declared.get("source")
        if source is not None and (not isinstance(source, str) or not CAPABILITY.match(source)):
            return [f"an analytic step's source is a capability, not {source!r}"]
    else:
        return ["`analytic` is true, or names its source: {source: <capability>}"]
    reasons: list[str] = []
    for operation in _operations(given):
        capability = operation.rsplit(".", 1)[0]
        if capability != source:
            reasons.append(
                f"an analytic step reaches its source only, and {operation} is outside it"
            )
    if given.get("allowed_hosts"):
        reasons.append("an analytic step reaches no host")
    if _workspace(given):
        reasons.append("an analytic step reaches no host, and a workspace is fetched from one")
    if given.get("credentials") and not _operations(given):
        reasons.append("an analytic step holds no credential")
    dataset, model = given.get("dataset"), given.get("model")
    if isinstance(dataset, Mapping) and "uri" in dataset:
        reasons.append("an analytic step reaches no host, and its rows are behind a uri")
    if isinstance(model, Mapping) and "uri" in model:
        reasons.append("an analytic step reaches no host, and its model is behind a uri")
    for referenced in sorted(_from(given)):
        if referenced not in analytic:
            reasons.append(
                f"an analytic step reads only what analytic steps produced, and {referenced} "
                "is not analytic"
            )
    return reasons


def _operations(given: Mapping[str, Any]) -> list[str]:
    """The connector operations the work calls: its own, or the one its wait reads."""
    found = []
    if given.get("rule") == "connector" and isinstance(given.get("operation"), str):
        found.append(given["operation"])
    until = given.get("until")
    if isinstance(until, Mapping) and isinstance(until.get("operation"), str):
        found.append(until["operation"])
    return [operation for operation in found if OPERATION.match(operation)]


def _workspace(given: Mapping[str, Any]) -> bool:
    workspace = given.get("workspace")
    return isinstance(workspace, Mapping) and workspace.get("kind", "none") != "none"


def _from(node: Any) -> set[str]:
    if isinstance(node, Mapping):
        found = {str(node[FROM])} if FROM in node else set()
        for value in node.values():
            found |= _from(value)
        return found
    if isinstance(node, list | tuple):
        found = set()
        for item in node:
            found |= _from(item)
        return found
    return set()
