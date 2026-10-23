"""What a step may see: its case scope and the frame of an analytic step (ADR-0130, UC-7.7).

A step that serves a case declares the case's **scope**: the subject the case is about, named
by one of the run's inputs. A step that analyses declares itself **analytic**: its frame holds
its one source, read only, and nothing else. Both are enforced here and in the engine, never
asked of a model.

What can be told from the process alone is told before a run starts (`findings`): an analytic
step that calls a capability other than its source, reaches a host, or reads what a step that
is not analytic produced; a scoped worker step that reaches a host, which the frame cannot
scope. What depends on the connector and the tenant is told at the call (`refusal`): an
outward operation in an analytic step, a source the tenant does not declare free of personal
fields, a scoped call to personal data whose connector does not honour a scope.

A step that is neither scoped nor analytic and calls a capability that serves personal data
is an export outside a specific case. It is anchored at every level (`personal_data`): the
step waits for a person before it reads anything.

Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Any

from taktus.components.run.domain.model.work import (
    ConnectorRule,
    Control,
    MlWork,
    WaitWork,
    Work,
    WorkerWork,
    references,
)
from taktus.shared.v1 import Anchor, StepId

REFUSED = "frame.refused"
"""The ledger entry of a call the frame refused, or a connector refused as out of scope; its
outcome is one of the tokens below."""

OUT_OF_SCOPE = "out_of_scope"
"""The connector refused a scoped call that asked for another subject's data."""
NOT_HONOURED = "scope_not_honoured"
"""A scoped call to personal data whose connector does not declare that it honours a scope."""
OUTWARD = "outward"
"""An analytic step called an operation whose effect leaves the system."""
OUTSIDE_SOURCE = "outside_source"
"""An analytic step called a capability other than its source."""
NOT_DECLARED_FREE = "not_declared_free"
"""An analytic step's source is not declared free of personal fields by the tenant."""
PERSONAL_SOURCE = "personal_source"
"""An analytic step's source serves personal data."""


def personal_data(capability: str) -> Anchor:
    """The frame's own anchor on a step that reads `capability` outside a specific case. No
    tenant configuration names it, and none removes it: it holds at every level."""
    return Anchor.model_validate(
        {
            "id": "anc-personal-data",
            "class": "legal",
            "act": "read personal data outside a specific case: the step has no case scope, "
            f"and {capability} serves personal data (UC-7.7, ADR-0130)",
            "applies_to": {"actions": [capability]},
            "decider": {"role": "owner"},
        }
    )


def anchored(control: Control, capability: str | None, *, personal: bool) -> bool:
    """Whether the step reads personal data outside a specific case: it calls a capability that
    serves personal data, and is neither scoped nor analytic. An analytic step is refused at
    the call instead."""
    return (
        capability is not None and personal and control.scope is None and control.analytic is None
    )


def refusal(
    control: Control,
    capability: str,
    *,
    outward: bool,
    personal: bool,
    honours_scope: bool,
    free: bool,
) -> tuple[str, str] | None:
    """Why the frame refuses the call before it is made, as a token and a reason, or None.
    `personal` says that the capability serves personal data, by its connector's declaration
    or the tenant's; `honours_scope` that its connector answers a scoped call with the subject's
    data only; `free` that the tenant declares it free of personal fields."""
    if control.analytic is not None:
        source = control.analytic.source
        if outward:
            return OUTWARD, (
                f"an analytic step speaks to nobody outside, and {capability} has an effect "
                "that leaves the system"
            )
        if capability != source:
            return OUTSIDE_SOURCE, f"an analytic step reads its source only, not {capability}"
        if personal:
            return PERSONAL_SOURCE, (
                f"an analytic step reads a source free of personal fields, and {capability} "
                "serves personal data"
            )
        if not free:
            return NOT_DECLARED_FREE, (
                f"an analytic step reads a source the tenant declares free of personal "
                f"fields, and the tenant does not declare {capability} so "
                "(taktusctl sources declare --free)"
            )
    if control.scope is not None and personal and not honours_scope:
        return NOT_HONOURED, (
            f"{capability} serves personal data, and its connector does not declare that it "
            "answers a scoped call with the subject's data only"
        )
    return None


def findings(
    work: Work,
    control: Control,
    referenced: list[Any],
    analytic: Set[StepId],
) -> list[str]:
    """Why the step's frame cannot hold, as far as the process alone tells, or nothing.
    `referenced` are the untyped values of its work and control; `analytic` the steps of the
    run that are analytic."""
    found: list[str] = []
    if control.analytic is not None:
        found.extend(_analytic(work, control.analytic.source, referenced, analytic))
    if control.scope is not None and isinstance(work, WorkerWork):
        if work.allowed_hosts or work.workspace.kind != "none":
            found.append(
                "a scoped worker step reaches hosts itself, and the frame cannot scope what it "
                "reads there: give it no host and no workspace, and read the case's data in a "
                "connector step before it"
            )
    return found


def _analytic(
    work: Work, source: str | None, referenced: list[Any], analytic: Set[StepId]
) -> list[str]:
    found: list[str] = []
    for capability in capabilities_of(work):
        if capability != source:
            found.append(
                f"an analytic step reaches its source only, and {capability} is not "
                f"{'its source' if source is not None else 'one: it names no source'}"
            )
    if isinstance(work, WorkerWork):
        if work.allowed_hosts:
            found.append("an analytic step reaches no host")
        if work.workspace.kind != "none":
            found.append("an analytic step reaches no host, and a workspace is fetched from one")
        if work.credentials:
            found.append("an analytic step holds no credential")
    if isinstance(work, MlWork):
        if "uri" in work.dataset:
            found.append("an analytic step reaches no host, and its rows are behind a uri")
        if work.model.uri is not None:
            found.append("an analytic step reaches no host, and its model is behind a uri")
    for value in referenced:
        for step in sorted(references(value)):
            if step not in analytic:
                found.append(
                    f"an analytic step reads only what analytic steps produced, and {step} is "
                    "not analytic"
                )
    return found


def capabilities_of(work: Work) -> tuple[str, ...]:
    """The connector capabilities a step's work calls: its operation's, or its wait's."""
    if isinstance(work, ConnectorRule):
        return (work.capability,)
    if isinstance(work, WaitWork) and work.until is not None:
        return (work.until.capability,)
    return ()


def analytic_steps(controls: Mapping[StepId, Control]) -> frozenset[StepId]:
    return frozenset(step for step, control in controls.items() if control.analytic is not None)
