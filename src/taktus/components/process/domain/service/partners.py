"""Whether a version's exchanges with partners hold to their data contracts (UC-15.3,
ADR-0273 §2). Pure: the version in, findings out.

A step that calls an operation of a capability carrying a partner's data must be named by a
contract. An `import` step carries a check of the shape of what it read whose columns hold every
field the contract requires; an `export` step depends on a step that carries one. A contract
follows an open standard or says why a proprietary format, and one that names a frequency
belongs to a version that expects its runs.

`breach` says which clause of its contract a failed exchange step broke, for the escalation
that brings a person in (ADR-0303).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from taktus.shared.v1 import CheckKind, Step

if TYPE_CHECKING:
    from taktus.components.process.domain.model.process import DataContract, ProcessVersion

PARTNER_CAPABILITIES = frozenset({"documents.invoices"})
"""The capabilities whose operations carry a partner's data in an exchange format: incoming
electronic invoices (ADR-0169). One that arrives with a connector is added here."""


def findings(version: ProcessVersion) -> list[str]:
    found: list[str] = []
    named: dict[str, str] = {}
    ids = {step.id for step in version.steps}
    for name, contract in version.contracts.items():
        if (contract.standard is None) == (contract.proprietary is None):
            found.append(
                f"the data contract {name!r} names the open standard it follows, or why a "
                "proprietary format under `proprietary`, and not both"
            )
        if contract.frequency is not None and not (
            version.expected_schedules or version.expect is not None
        ):
            found.append(
                f"the data contract {name!r} expects an exchange every "
                f"{contract.frequency}, and the version expects no run: a missing exchange "
                "would not be noticed (ADR-0107)"
            )
        for step_id in contract.steps:
            if step_id not in ids:
                found.append(f"the data contract {name!r} names {step_id!r}, no step of it")
                continue
            if step_id in named:
                found.append(
                    f"the step {step_id!r} is named by the data contracts {named[step_id]!r} "
                    f"and {name!r}; one exchange has one contract"
                )
            named[step_id] = name
            found.extend(_held(version, name, contract, version.step(step_id)))
    for step in version.steps:
        work = version.work.get(step.id) or {}
        operation = work.get("operation")
        if (
            isinstance(operation, str)
            and operation.rsplit(".", 1)[0] in PARTNER_CAPABILITIES
            and step.id not in named
        ):
            found.append(
                f"the step {step.id!r} exchanges data with a partner through {operation}, and "
                "no data contract under `contracts` names it (UC-15.3)"
            )
    return found


def _held(version: ProcessVersion, name: str, contract: DataContract, step: Step) -> list[str]:
    required = set(contract.required)
    if contract.direction == "import":
        if not _covers(step, required):
            return [
                f"the step {step.id!r} imports under the data contract {name!r} and carries no "
                "`source_shape` check whose columns hold every field it requires: "
                + ", ".join(sorted(required))
            ]
        return []
    if not any(_covers(version.step(d), required) for d in step.dependencies):
        return [
            f"the step {step.id!r} exports under the data contract {name!r}, and no step it "
            "depends on checks the document against the fields it requires: "
            + ", ".join(sorted(required))
        ]
    return []


def _covers(step: Step, required: set[str]) -> bool:
    return any(
        check.kind is CheckKind.SOURCE_SHAPE and required <= set(check.columns or ())
        for check in step.checks or ()
    )


def breach(version: ProcessVersion, step_id: str, lacking: Sequence[str]) -> str | None:
    """The clause of a data contract that a failed exchange step breaks, in words (UC-15.3,
    ADR-0303): the contract, its partner and standard, each required field the message lacks
    with the clause that requires it, and who answers for the contract on each side. None where
    no contract names the step, nor an export whose document the step checks. `lacking` is
    what the step's failed check found missing; a field the contract does not require is not
    its breach."""
    named = next(
        ((name, c) for name, c in version.contracts.items() if step_id in c.steps), None
    ) or next(
        (
            (name, c)
            for name, c in version.contracts.items()
            if c.direction == "export"
            and any(step_id in version.step(s).dependencies for s in c.steps)
        ),
        None,
    )
    if named is None:
        return None
    name, contract = named
    after = contract.standard or f"a proprietary format ({contract.proprietary})"
    fields = [f for f in lacking if f in contract.required]
    if fields:
        broken = "; ".join(
            f"the field {f!r} is missing, which the clause `fields.{f}: required` requires"
            for f in fields
        )
    else:
        required = ", ".join(contract.required)
        broken = f"the message does not have the shape the clause `fields` requires: {required}"
    return (
        f"The {contract.direction} breaks the data contract {name!r} with {contract.partner}, "
        f"after {after}: {broken}. Responsible: {contract.responsible.ours} on our side, "
        f"{contract.responsible.theirs} on theirs. Nothing of the message was mapped, "
        "completed or guessed."
    )
